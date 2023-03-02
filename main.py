import datetime

import xlsxwriter
from kivy.clock import Clock, mainthread
from kivy.config import Config
from kivy.lang import Builder
from kivy.properties import BooleanProperty, StringProperty
from kivy.storage.jsonstore import JsonStore
from kivymd.app import MDApp
from kivymd.toast import toast
from kivymd.uix.button import MDRectangleFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.filemanager import MDFileManager
from kivymd.uix.list import (IconRightWidget, OneLineAvatarIconListItem,
                             TwoLineListItem)
from kivymd.uix.screenmanager import MDScreenManager

from able import GATT_SUCCESS, BluetoothDispatcher

Config.set('kivy', 'log_level', 'debug')
Config.set('kivy', 'log_enable', '1')


class TwoLineListItemCustom(TwoLineListItem):
    '''Кастомный класс для списка найденых дейвайсов.
    '''
    def __init__(self, device_object, **kwargs):
        super().__init__(**kwargs)
        self.device_object = device_object


class CustomIconRightWidget(IconRightWidget):
    '''Кастомный класс для списка историй вычислений.
    '''
    def __init__(self, key, **kwargs):
        super().__init__(**kwargs)
        self.key = key


class MainApp(MDApp):
    '''Основной класс для приложения.
    '''
    ble = BluetoothDispatcher()
    state = StringProperty('')
    queue_timeout_enabled = BooleanProperty(True)
    queue_timeout = StringProperty('1000')
    device_name = StringProperty('')
    result = StringProperty('')
    result_time = StringProperty('')
    metric = StringProperty('mm')
    L = StringProperty('')
    H = StringProperty('')
    store = JsonStore('store.json')
    devices_address_list = []
    result_list = []
    count = 0

    uids = {
        'string': 'ffb2',
    }

    def on_pause(self):
        return True

    def on_resume(self):
        pass

    def init(self):
        # Биндит события класса ble
        self.set_queue_settings()
        self.ble.bind(on_device=self.on_device)
        self.ble.bind(on_scan_started=self.on_scan_started)
        self.ble.bind(on_scan_completed=self.on_scan_completed)
        self.ble.bind(on_connection_state_change=self.on_connection_state_change)
        self.ble.bind(on_services=self.on_services)
        self.ble.bind(on_characteristic_changed=self.on_characteristic_changed)

    def build(self):
        # загружает фронтэнд
        self.kv1 =  Builder.load_file('kv1.kv')
        self.kv2 =  Builder.load_file('kv2.kv')
        self.kv3 =  Builder.load_file('kv3.kv')

        # менеджер экранов
        self.sm = MDScreenManager()
        self.sm.add_widget(self.kv1)
        self.sm.add_widget(self.kv2)
        self.sm.add_widget(self.kv3)

        # диалоговое окно в истории
        self.dialog = MDDialog(
                text="Удалить историю измерений?",
                buttons=[
                    MDRectangleFlatButton(
                        text="ДА",
                        theme_text_color="Custom",
                        text_color=self.theme_cls.primary_color,
                        on_press=self.clean_result_all,
                        
                    ),
                    MDRectangleFlatButton(
                        text="НЕТ",
                        theme_text_color="Custom",
                        text_color=self.theme_cls.primary_color,
                        on_press=self.close_dialog
                    ),
                ],
            )

        # файловый менеджер
        self.manager_open = False
        self.file_manager = MDFileManager(
            exit_manager=self.exit_manager, 
            select_path=self.select_path,
            selector='folder'
        )

        Clock.schedule_once(self.start_scan, 1) # запускает поиск устройств
        return self.sm
    
    def on_checkbox_active(self, checkbox, value):
        # меняет единцы измерения и пересчитывает результат
        if value:
            self.metric = 'm'
            toast('Метр')
        else:
            self.metric = 'mm'
            toast('Миллиметр')
        if self.H: self.H = self.format_metric(self.H, self.metric)
        if self.L: self.L = self.format_metric(self.L, self.metric)

        if self.H and self.L:
            self.result_calculation()

    def format_metric(self, value, metric):
        # проверяет еденицы измерения и отдает обработанную строку
        try:
            if metric == 'mm':
                return str(int(float(value)*1000))
            else:
                if '.' in value:
                    return value
                else:
                    return str(int(value)/1000)
        except Exception as e:
            toast(f'Что-то пошло не так: {e}')
            return ''

    def clean_l(self):
        # оичщает хорду L
        self.L = ''
        self.result = ''
        self.result_time = ''
        toast('Очищено')

    def clean_h(self):
        # очищает высоту сегмента H
        self.H = ''
        self.result = ''
        self.result_time = ''
        toast('Очищено')

    def clean_all(self):
        # очищает все измерения
        self.L = ''
        self.H = ''
        self.result = ''
        self.result_time = ''
        toast('Очищено')

    def show_alert_dialog_del(self):
        # открывает диологовое окно в истории при попытке оичистить историю 
        if self.result_list:
            self.dialog.open()

    def clean_result_all(self, *args):
        # очищает историю
        self.store.clear()
        self.clean_result_list()
        self.dialog.dismiss()
        toast('История очищена')

    def close_dialog(self, *args):
        # закрывает диологовое окно в истории
        self.dialog.dismiss()

    def clean_result_list(self):
        # удаляет виджеты из истории чтобы не было дублей, вызывается всегда при заходе в историю
        for item in self.result_list:
            self.kv3.ids.results.remove_widget(item)

    def append_result_list(self):
        # добавляет резултат в store на старнце резултатов
        if not self.result:
            toast('Прежде чем добавить результат в историю произведите вычисления')
        else:
            self.store.put(self.result_time, result_time=self.result_time, H=self.H,  L=self.L, result=self.result,  metric=self.metric)
            toast('Результат добавлен в историю')

    def start_scan_button(self):
        # кнопка сканирования, запускает сканирование принудительно и обновляет счетчик
        self.count = 0
        Clock.schedule_once(self.start_scan, 1)

    def start_scan(self, dt):
        # инициализирует события для ble и закрывает старые соедениения перед новым сканированием
        if not self.state:
            self.init()
        self.state = 'Поиск'
        self.ble.close_gatt()
        self.ble.start_scan()

    def on_scan_started(self, ble, success):
        # обновляет state когда запущено новое сканирование
        self.state = 'Поиск' if success else ''
 
    def on_device(self, ble, device, rssi, advertisement):
        # вызывается когда находит устройство
        if self.state != 'Поиск':
            return
        
        # добавляет новое устройство на экран если ранее не было добавлено
        if not device.getAddress() in self.devices_address_list:
            self.list_devices(device)

        if self.count < 10:
            self.count += 1
            self.ble.close_gatt()
            self.ble.start_scan()
        else:
            self.state = 'found'
            self.ble.stop_scan()

    @mainthread
    def list_devices(self, device):
        # добавляет новое устройство на экран
        devices_address = device.getAddress()
        devices_name = device.getName()
        self.kv1.ids.container.add_widget(
                TwoLineListItemCustom(
                    device_object=device,
                    text=devices_name,
                    secondary_text=devices_address,
                    on_press=self.connect_device,
                )
            )
        # добавляет новое устройствов список чтобы не было дублей
        self.devices_address_list.append(devices_address)

    def on_scan_completed(self, ble):
        # по завершению поиска 
        self.count = 0

    def connect_device(self, instance):
        # заакрывает прошлые соеденение и остнавливаает поиск
        self.ble.close_gatt()
        self.ble.stop_scan()
        self.device = instance.device_object
        self.device_name = 'Соединение'
        # переходит на страницу вычесления
        self.sm.current = 'calculations'
        # выполняет соедениние с устройством
        self.ble.connect_gatt(instance.device_object)

    def show_main(self):
        # пероход на страницу поиска
        self.sm.current = 'first'

    def show_history(self):
        # пероход на страницу истории
        self.sm.current = 'history'
        self.clean_result_list()
        # добовлдяет виджеты резултатов из store
        for key in self.store:
            item = self.store.get(key)
            w = OneLineAvatarIconListItem(
                    CustomIconRightWidget(
                        icon='delete-circle',
                        theme_icon_color='Custom',
                        icon_color=self.theme_cls.primary_color,
                        on_press=self.clean_item_result,
                        key=key,
                        ),
                    text=f"{item['result_time']} | {item['H']}{item['metric']} | {item['L']}{item['metric']} | {item['result']}{item['metric']}",
            )
            self.kv3.ids.results.add_widget(w)
            # добавляет виджет в список чтобы избежать дублей
            self.result_list.append(w)

    def clean_item_result(self, instanse):
        # удаляет резултут из истрии
        self.store.delete(instanse.key)
        # открывает страницу истории чтобы отреднерить страницу занова
        self.show_history()

    def show_calculations(self):
        # открывает страницу вычеслений
        if not self.device_name:
            toast('Выполните соединение с устройством')
        self.sm.current = 'calculations'

    def on_connection_state_change(self, ble, status, state):
        # следит за соединением с устройством
        if status == GATT_SUCCESS:
            if state:
                self.ble.discover_services()
            else:
                self.state = 'disconnected'
        else:
            self.state = 'connection_error'
            self.device_name = 'connection_error'

    def on_services(self, ble, status, services):
        # запускает сервисы
        if status != GATT_SUCCESS:
            self.state = 'services_error'
            return
        self.state = 'Соединен: ' + self.device.getName()
        self.device_name = self.device.getName()
        self.services = services
        # запускас слежку за уведомлением с подключенного устрйсва
        self.enable_notifications()

    def enable_notifications(self, enable=True):
        # ищет характерситику и запускает получение уведомлений
        characteristic = self.services.search(self.uids['string'])
        if characteristic:
            self.ble.enable_notifications(characteristic, enable)

    def on_characteristic_changed(self, ble, characteristic):
        # вызывается кода уведомление с устройства получено 
        uuid = characteristic.getUuid().toString()
        if self.uids['string'] in uuid:
            value = characteristic.getStringValue(0)
            if not self.H and not self.L:
                self.H = self.format_metric(self.frormat_value(value), self.metric)
            elif self.H and not self.L:
                self.L = self.format_metric(self.frormat_value(value), self.metric)
            elif not self.H and self.L:
                self.H = self.format_metric(self.frormat_value(value), self.metric)

            # если все данные полуцчены запускам вычесление радиуса
            if self.H and self.L:
                now = datetime.datetime.now()
                self.result_time = now.strftime('%Y.%m.%d:%H.%M.%S')
                self.result_calculation()
                
    def result_calculation(self):
        # вычесление радиуса в зависимости от еденицы измерения
        if self.metric == 'mm':
            h = int(self.H)
            L = int(self.L)
            f = 2
        else:
            h = float(self.H)
            L = float(self.L)
            f = 3
        result = round((((L**2)/(4*h))+h)/2, f)
        self.result = str(result)

    def frormat_value(self, value):
        # отрезает правую часть после m 0.232m\n\x00x00
        if 'm' in value:
            return value.split('m')[0]
        else:
            return ''
            
    def set_queue_settings(self):
        # устанавливает таймаут очереди
        self.ble.set_queue_timeout(None if not self.queue_timeout_enabled
                                   else int(self.queue_timeout) * .001)
        
    def file_manager_open(self):
        # открывает файловый менеджер на странице истории
        if not self.result_list:
            toast('Сначала выполните и сохраните вычисления')
        else:
            self.file_manager.show('/storage/emulated/0/')  # output manager to the screen
            self.manager_open = True
            # self.file_manager.show_disks()

    def select_path(self, path: str):
        # закрывает файловый менеджер прит получаении выбранного пути
        self.exit_manager()

        # создает список для записи резултатов в таблицу
        new_list = [['Дата/время', 'Хорда L', 'Высота сегмента h', 'Радиус'],]
        now = datetime.datetime.now()
        time_string = now.strftime('%Y.%m.%d:%H.%M.%S')
        for key in self.store:
            new_list.append([
                self.store[key]['result_time'],
                self.store[key]['H']+self.store[key]['metric'],
                self.store[key]['L']+self.store[key]['metric'],
                self.store[key]['result']+self.store[key]['metric'],
                ])
        path = f'{path}/results-{time_string}.xlsx'

        # записывает в таблицу
        with xlsxwriter.Workbook(path) as workbook:
            worksheet = workbook.add_worksheet()

            for row_num, data in enumerate(new_list):
                worksheet.write_row(row_num, 0, data)
        toast(f'Сохранено в: {path}')

    def exit_manager(self, *args):
        # закрывает файловый менеджер
        self.manager_open = False
        self.file_manager.close()


MainApp().run()
