import bluetooth
import time

MAX_CHARS = 30      # Máximo de caracteres por parámetro
BUFFER_SIZE = 64    # Buffer por característica (mayor al máximo, por seguridad)
MTU_SIZE = 64       # MTU solicitado (>= 33 para 30 caracteres)

_IRQ_CENTRAL_CONNECT = 1
_IRQ_CENTRAL_DISCONNECT = 2
_IRQ_GATTS_WRITE = 3
_IRQ_MTU_EXCHANGED = 21


class Bluetooth:

    def __init__(self, device_name="Esp32-C0NF"):
        self.device_name = device_name

        # Almacenamiento de variables
        self.ssid = None
        self.password = None

        self.mqtt_id = None
        self.mqtt_ip = None    # Por defecto 172.30.33.188
        self.mqtt_port = None  # Por defecto 8883
        self.mqtt_user = None
        self.mqtt_pass = None

        self.nuevo_nombre = None

        # Banderas de estado individuales
        self.activo = True
        self.wifi_ssid_listo = False
        self.wifi_pass_listo = False
        self.mqtt_id_listo = False
        self.mqtt_ip_listo = False
        self.mqtt_port_listo = False
        self.mqtt_user_listo = False
        self.mqtt_pass_listo = False
        self.nombre_listo = False

        # Inicialización del BLE
        self.ble = bluetooth.BLE()
        # El MTU debe configurarse ANTES de activar el BLE
        try:
            self.ble.config(mtu=MTU_SIZE)
        except Exception as e:
            print("No se pudo configurar MTU:", e)
        self.ble.active(True)
        self.ble.irq(self._irq_handler)
        self._setup_services()
        self._start_advertising()

    def _irq_handler(self, event, data):
        if not self.activo:
            return

        if event == _IRQ_CENTRAL_CONNECT:
            print("Cliente conectado")

        elif event == _IRQ_CENTRAL_DISCONNECT:
            print("Cliente desconectado")
            # Volver a anunciar para poder reconectar
            self._start_advertising()

        elif event == _IRQ_MTU_EXCHANGED:
            conn_handle, mtu = data
            print("MTU negociado:", mtu)

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            try:
                buffer = self.ble.gatts_read(value_handle)
                if not buffer:
                    return

                texto = buffer.decode("utf-8").replace("\x00", "").strip()
                # Quitar cualquier salto de línea por si el cliente lo envía
                texto = texto.replace("\r", "").replace("\n", "")
                if not texto:
                    return

                # Limitar a 30 caracteres
                texto = texto[:MAX_CHARS]
                print("Recibido (%d): %s" % (len(texto), texto))

                if value_handle == self.h_ssid:
                    self.ssid = texto
                    self.wifi_ssid_listo = True
                elif value_handle == self.h_pass:
                    self.password = texto
                    self.wifi_pass_listo = True
                elif value_handle == self.h_mqtt_id:
                    self.mqtt_id = texto
                    self.mqtt_id_listo = True
                elif value_handle == self.h_mqtt_ip:
                    self.mqtt_ip = texto
                    self.mqtt_ip_listo = True
                elif value_handle == self.h_mqtt_port:
                    self.mqtt_port = int(texto)
                    self.mqtt_port_listo = True
                elif value_handle == self.h_mqtt_user:
                    self.mqtt_user = texto
                    self.mqtt_user_listo = True
                elif value_handle == self.h_mqtt_pass:
                    self.mqtt_pass = texto
                    self.mqtt_pass_listo = True
                elif value_handle == self.h_name:
                    self.nuevo_nombre = texto
                    self.nombre_listo = True

            except Exception as e:
                print("Error en escritura BLE:", e)

    def _setup_services(self):
        UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")

        UUID_SSID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
        UUID_PASS = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
        UUID_MQTT_ID = bluetooth.UUID("6E400004-B5A3-F393-E0A9-E50E24DCCA9E")
        UUID_MQTT_IP = bluetooth.UUID("6E400005-B5A3-F393-E0A9-E50E24DCCA9E")
        UUID_MQTT_PORT = bluetooth.UUID("6E400006-B5A3-F393-E0A9-E50E24DCCA9E")
        UUID_MQTT_USER = bluetooth.UUID("6E400007-B5A3-F393-E0A9-E50E24DCCA9E")
        UUID_MQTT_PASS = bluetooth.UUID("6E400008-B5A3-F393-E0A9-E50E24DCCA9E")
        UUID_NAME = bluetooth.UUID("6E400009-B5A3-F393-E0A9-E50E24DCCA9E")

        FLAGS = bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE

        SERVICES = (
            (
                UART_UUID,
                (
                    (UUID_SSID, FLAGS),
                    (UUID_PASS, FLAGS),
                    (UUID_MQTT_ID, FLAGS),
                    (UUID_MQTT_IP, FLAGS),
                    (UUID_MQTT_PORT, FLAGS),
                    (UUID_MQTT_USER, FLAGS),
                    (UUID_MQTT_PASS, FLAGS),
                    (UUID_NAME, FLAGS),
                ),
            ),
        )

        handles = self.ble.gatts_register_services(SERVICES)
        (
            self.h_ssid,
            self.h_pass,
            self.h_mqtt_id,
            self.h_mqtt_ip,
            self.h_mqtt_port,
            self.h_mqtt_user,
            self.h_mqtt_pass,
            self.h_name,
        ) = handles[0]

        # CLAVE: ampliar el buffer de cada característica (por defecto es 20 bytes)
        for h in handles[0]:
            self.ble.gatts_set_buffer(h, BUFFER_SIZE)

    def _start_advertising(self):
        if not self.activo:
            return
        name_bytes = bytes(self.device_name, "utf-8")
        payload = b"\x02\x01\x06" + bytes((len(name_bytes) + 1, 0x09)) + name_bytes
        try:
            self.ble.gap_advertise(100000, payload)
        except Exception as e:
            print("Error advertising:", e)

    def esperar_wifi(self):
        while (not self.wifi_ssid_listo or not self.wifi_pass_listo) and self.activo:
            time.sleep(0.1)
        return self.ssid, self.password

    def esperar_mqtt(self):
        while not (
                self.mqtt_id_listo and self.mqtt_ip_listo and self.mqtt_port_listo
                and self.mqtt_user_listo and self.mqtt_pass_listo) and self.activo:
            time.sleep(0.1)
        return self.mqtt_id, self.mqtt_ip, self.mqtt_port, self.mqtt_user, self.mqtt_pass

    def esperar_nombre(self):
        while not self.nombre_listo and self.activo:
            time.sleep(0.1)
        return self.nuevo_nombre

    def apagar(self):
        try:
            self.activo = False
            self.ble.irq(None)
            time.sleep(0.2)
            self.ble.active(False)
        except Exception:
            pass