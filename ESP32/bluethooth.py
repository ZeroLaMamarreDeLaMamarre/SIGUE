import bluetooth
import time


class Bluetooth:
    def __init__(self, device_name="ESP32_Config"):
        self.device_name = device_name
        self.ssid = None
        self.password = None

        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._ble_irq)

        self._register_services()
        self._start_advertising()
        print(f"Dispositivo BLE '{self.device_name}' iniciado. Esperando credenciales...")

    def _ble_irq(self, event, data):
        if event == 1:
            print("Cliente BLE conectado.")
        elif event == 2:
            print("Cliente BLE desconectado. Reiniciando publicidad...")
            self._start_advertising()
        elif event == 3:
            conn_handle, value_handle = data
            if value_handle == self.rx_handle:
                buffer = self.ble.gatts_read(self.rx_handle)
                try:
                    texto = buffer.decode('utf-8').strip()
                    print(f"Datos recibidos: {texto}")

                    if "," in texto:
                        # Extraer SSID y Password divididos por la coma
                        temp_ssid, temp_password = texto.split(",", 1)
                        if temp_ssid and temp_password:
                            self.ssid = temp_ssid
                            self.password = temp_password
                            print("¡Credenciales completas almacenadas internamente!")
                except Exception as e:
                    print(f"Error al procesar datos: {e}")

    def _register_services(self):
        UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
        RX_UUID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")

        SERVICES = (
            (
                UART_UUID,
                (
                    (RX_UUID, bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE),
                ),
            ),
        )
        ((self.rx_handle,),) = self.ble.gatts_register_services(SERVICES)

    def _start_advertising(self):
        name_bytes = bytes(self.device_name, 'utf-8')
        payload = bytes((len(name_bytes) + 1, 0x09)) + name_bytes
        self.ble.gap_advertise(100000, payload)

    def esperar_credenciales(self):
        """Mantiene el ESP32 retenido aquí hasta recibir SSID y Password."""
        print("Bloqueando ejecución: esperando datos por Bluetooth...")
        while not self.ssid or not self.password:
            time.sleep(0.2)  # Pausa breve para no saturar el procesador

        return self.ssid, self.password

