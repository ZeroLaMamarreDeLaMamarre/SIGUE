import bluetooth
import time

class Bluetooth:
    def __init__(self, device_name="ESP32_Config"):
        self.device_name = device_name
        self.ssid = None
        self.password = None
        self.mqtt_id = None
        self.mqtt_ip = None
        self.mqtt_port = None
        self.mqtt_user = None
        self.mqtt_pass = None
        self.nuevo_nombre = None
        self.config_terminada = False
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._ble_irq)
        self._register_services()
        self._start_advertising()

    def _ble_irq(self, event, data):
        if event == 1:
            pass
        elif event == 2:
            if not self.config_terminada:
                self._start_advertising()
            else:
                pass
        elif event == 3:
            conn_handle, value_handle = data
            if value_handle == self.rx_wifi_handle:
                buffer = self.ble.gatts_read(self.rx_wifi_handle)
                try:
                    texto = buffer.decode('utf-8').strip()
                    if "," in texto:
                        temp_ssid, temp_password = texto.split(",", 1)
                        if temp_ssid and temp_password:
                            self.ssid = temp_ssid
                            self.password = temp_password
                except Exception as e:
                    pass
            elif value_handle == self.rx_mqtt_handle:
                buffer = self.ble.gatts_read(self.rx_mqtt_handle)
                try:
                    texto = buffer.decode('utf-8').strip()
                    partes = texto.split(",")
                    if len(partes) == 5:
                        self.mqtt_id = partes[0]
                        self.mqtt_ip = partes[1]
                        self.mqtt_port = int(partes[2])
                        self.mqtt_user = partes[3]
                        self.mqtt_pass = partes[4]
                except Exception as e:
                    pass
            elif value_handle == self.rx_name_handle:
                buffer = self.ble.gatts_read(self.rx_name_handle)
                try:
                    texto = buffer.decode('utf-8').strip()
                    if texto:
                        self.nuevo_nombre = texto
                except Exception as e:
                    pass

    def _register_services(self):
        UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
        RX_WIFI_UUID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
        RX_MQTT_UUID = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
        RX_NAME_UUID = bluetooth.UUID("6E400004-B5A3-F393-E0A9-E50E24DCCA9E")
        SERVICES = (
            (
                UART_UUID,
                (
                    (RX_WIFI_UUID, bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE),
                    (RX_MQTT_UUID, bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE),
                    (RX_NAME_UUID, bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE),
                ),
            ),
        )
        ((self.rx_wifi_handle, self.rx_mqtt_handle, self.rx_name_handle),) = self.ble.gatts_register_services(SERVICES)

    def _start_advertising(self):
        name_bytes = bytes(self.device_name, 'utf-8')
        payload = bytes((len(name_bytes) + 1, 0x09)) + name_bytes
        self.ble.gap_advertise(100000, payload)

    def esperar_nombre(self):
        while not self.nuevo_nombre:
            time.sleep(0.2)
        return self.nuevo_nombre

    def esperar_wifi(self):
        while not self.ssid or not self.password:
            time.sleep(0.2)
        return self.ssid, self.password

    def esperar_mqtt(self):
        while not all([self.mqtt_id, self.mqtt_ip, self.mqtt_port, self.mqtt_user, self.mqtt_pass]):
            time.sleep(0.2)
        self.config_terminada = True
        return self.mqtt_id, self.mqtt_ip, self.mqtt_port, self.mqtt_user, self.mqtt_pass

    def apagar(self):
        try:
            time.sleep(0.5)
            self.ble.active(False)
        except Exception as e:
            pass