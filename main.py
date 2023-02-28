import os
import time

from kivy.clock import Clock, mainthread
from kivy.config import Config
from kivy.lang import Builder
from kivy.properties import BooleanProperty, StringProperty
from kivymd.app import MDApp
from kivymd.toast import toast
from kivymd.uix.button import MDTextButton
from kivymd.uix.filemanager import MDFileManager
from kivymd.uix.list import OneLineListItem, TwoLineListItem
from kivymd.uix.screenmanager import MDScreenManager

from able import GATT_SUCCESS, BluetoothDispatcher

Config.set('kivy', 'log_level', 'debug')
Config.set('kivy', 'log_enable', '1')


KV1 = '''
MDScreen:
    name: 'first'

    MDTopAppBar:
        id: toolbar
        title: app.state
        elevation: 4
        pos_hint: {'top': 1}
        size_hint_y: .10


    MDScrollView:
        orientation: "vertical"
        padding: "0dp"
        adaptive_height: True
        pos_hint: {"top": .9}
        id: list
                
        MDList:
            id: container

    MDFloatingActionButton:
        icon: "magnify"
        icon_color: '#FFFFFF'
        theme_icon_color: "Custom"
        on_press: app.start_scan_button()
        pos_hint: {'top': .11, 'right': .97}
'''

KV2 = '''
MDScreen:
    name: 'two'

    MDTopAppBar:
        title: app.device_name
        pos_hint: {'top': 1}
        size_hint_y: .10

    MDScrollView:
        orientation: "vertical"
        padding: "0dp"
        adaptive_height: True
        pos_hint: {"top": .9}
        id: list
                
        MDList:
            id: result
    
    MDFloatingActionButton:
        icon: "arrow-left"
        icon_color: '#FFFFFF'
        theme_icon_color: "Custom"
        on_press: app.backpase_button()
        pos_hint: {'top': .11, 'right': .97}

    MDFloatingActionButton:
        icon: "content-save"
        pos_hint: {'top': .11, 'x': .03}
        on_release: app.file_manager_open()
'''


class TwoLineListItemCustom(TwoLineListItem):
    device_object = None 

    def __init__(self, device_object, **kwargs):
        super().__init__(**kwargs)
        self.device_object = device_object


class MainApp(MDApp):
    ble = BluetoothDispatcher()
    state = StringProperty('')
    queue_timeout_enabled = BooleanProperty(True)
    queue_timeout = StringProperty('1000')
    device_name = StringProperty('')
    devices_address_list = []
    value_list = []

    # value_list = ['1.906m\r\n\x00', '1.861m\r\n\x00',]
    buttom_list = []
    count = 0
    froze = 1
    clean_buttom = None

    uids = {
        'string': 'ffb2',
    }

    def on_pause(self):
        return True

    def on_resume(self):
        pass

    def init(self):
        self.set_queue_settings()
        self.ble.bind(on_device=self.on_device)
        self.ble.bind(on_scan_started=self.on_scan_started)
        self.ble.bind(on_scan_completed=self.on_scan_completed)
        self.ble.bind(on_connection_state_change=self.on_connection_state_change)
        self.ble.bind(on_services=self.on_services)
        self.ble.bind(on_characteristic_changed=self.on_characteristic_changed)

    def build(self):
        self.kv1 =  Builder.load_string(KV1)
        self.kv2 =  Builder.load_string(KV2)

        self.sm = MDScreenManager()
        self.sm.add_widget(self.kv1)
        self.sm.add_widget(self.kv2)

        self.clean_buttom = MDTextButton(
                text='Очистить',
                pos_hint={'top': .97, 'right': .98},
                on_press=self.clean_list_bottom

            )
        self.manager_open = False
        self.file_manager = MDFileManager(
            exit_manager=self.exit_manager, 
            select_path=self.select_path,
            selector='folder'
        )

        self.clean_buttom.color = 'white'

        Clock.schedule_once(self.start_scan, 1)
        return self.sm
    
    def clean_list_bottom(self, *args):
        self.kv2.remove_widget(self.clean_buttom)
        for item in self.buttom_list:
            self.kv2.ids.result.remove_widget(item)
        self.froze = 1

    def start_scan_button(self):
        self.count = 0
        Clock.schedule_once(self.start_scan, 1)

    def start_scan(self, dt):
        if not self.state:
            self.init()
        self.state = 'scan_start'
        self.ble.close_gatt()
        self.ble.start_scan()

    def on_scan_started(self, ble, success):
        self.state = 'Поиск' if success else ''
 
    def on_device(self, ble, device, rssi, advertisement):
        if self.state != 'Поиск':
            return
        
        if not device.getAddress() in self.devices_address_list:
            self.list_devices(device)

        if self.count < 20:
            self.count += 1
            self.ble.close_gatt()
            self.ble.start_scan()
        else:
            self.state = 'found'
            self.ble.stop_scan()

    @mainthread
    def list_devices(self, device):
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
        self.devices_address_list.append(devices_address)

    @mainthread
    def list_result(self, result):
        if self.froze == 1:
            self.kv2.add_widget(self.clean_buttom)
        bl = OneLineListItem(
                    text=f'Замер {self.froze}: {result}',
                )
        self.buttom_list.append(bl)
        self.kv2.ids.result.add_widget(bl)
        self.froze += 1

    def on_scan_completed(self, ble):
        self.count = 0

    def connect_device(self, instance):
        self.ble.close_gatt()
        self.ble.stop_scan()
        self.device = instance.device_object
        self.device_name = 'Соединение'
        self.sm.current = 'two'
        self.ble.connect_gatt(instance.device_object)

    def backpase_button(self):
        self.ble.close_gatt()
        self.ble.stop_scan()
        self.clean_list_bottom()
        self.sm.current = 'first'

    def on_connection_state_change(self, ble, status, state):
        if status == GATT_SUCCESS:
            if state:
                self.ble.discover_services()
            else:
                self.state = 'disconnected'
        else:
            self.state = 'connection_error'

    def on_services(self, ble, status, services):
        if status != GATT_SUCCESS:
            self.state = 'services_error'
            return
        self.state = 'Соединен: ' + self.device.getName()
        self.device_name = self.device.getName()
        self.services = services
        self.enable_notifications()

    def enable_notifications(self, enable=True):
        characteristic = self.services.search(self.uids['string'])
        if characteristic:
            self.ble.enable_notifications(characteristic, enable)

    def on_characteristic_changed(self, ble, characteristic):
        uuid = characteristic.getUuid().toString()
        if self.uids['string'] in uuid:
            value = characteristic.getStringValue(0)
            self.value_list.append(value)
            print(self.value_list)
            self.list_result(value)

    def set_queue_settings(self):
        self.ble.set_queue_timeout(None if not self.queue_timeout_enabled
                                   else int(self.queue_timeout) * .001)
        
    def file_manager_open(self):
        self.file_manager.show(os.path.expanduser("~"))  # output manager to the screen
        self.manager_open = True
        # self.file_manager.show_disks()

    def select_path(self, path: str):
        self.exit_manager()
        toast(path)

    def exit_manager(self, *args):
        self.manager_open = False
        self.file_manager.close()


MainApp().run()
