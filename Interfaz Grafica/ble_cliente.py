"""
Cliente BLE (lado PC) para configurar el ESP32.

Escribe cada parámetro en SU característica (mismos UUID que bluethooth_conf.py)
y lo hace en un hilo aparte para no congelar tkinter.

Requiere:  pip install bleak
"""

import asyncio
import threading

from bleak import BleakClient, BleakScanner

NOMBRE_BLE = "Esp32-C0NF"  # Nombre que anuncia el ESP32 en modo configuración

# UUID idénticos a los de bluethooth_conf.py
UUID_SSID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UUID_PASS = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
UUID_MQTT_ID = "6E400004-B5A3-F393-E0A9-E50E24DCCA9E"
UUID_MQTT_IP = "6E400005-B5A3-F393-E0A9-E50E24DCCA9E"
UUID_MQTT_PORT = "6E400006-B5A3-F393-E0A9-E50E24DCCA9E"
UUID_MQTT_USER = "6E400007-B5A3-F393-E0A9-E50E24DCCA9E"
UUID_MQTT_PASS = "6E400008-B5A3-F393-E0A9-E50E24DCCA9E"
UUID_NAME = "6E400009-B5A3-F393-E0A9-E50E24DCCA9E"


def _a_escrituras(datos):
    """{'wifi':..,'mqtt':..,'dispositivo':..} -> [(etiqueta, uuid, valor)].
    El nombre va al final: al recibirlo el ESP32 apaga el BLE y se reinicia."""
    w, m, n = datos["wifi"], datos["mqtt"], datos["dispositivo"]
    return [
        ("Wi-Fi SSID", UUID_SSID, w["ssid"]),
        ("Wi-Fi contraseña", UUID_PASS, w["password"]),
        ("MQTT Client ID", UUID_MQTT_ID, m["mqtt_id"]),
        ("MQTT IP", UUID_MQTT_IP, m["mqtt_ip"]),
        ("MQTT puerto", UUID_MQTT_PORT, m["mqtt_port"]),
        ("MQTT usuario", UUID_MQTT_USER, m["mqtt_user"]),
        ("MQTT contraseña", UUID_MQTT_PASS, m["mqtt_pass"]),
        ("Nombre del dispositivo", UUID_NAME, n["nuevo_nombre"]),
    ]


class EnviadorBLE:
    def __init__(self, nombre_ble=NOMBRE_BLE, timeout_scan=10):
        self.nombre_ble = nombre_ble
        self.timeout_scan = timeout_scan
        self.ocupado = False

    def enviar(self, datos, on_progreso=None, on_fin=None):
        """Envía los datos en segundo plano.
        on_progreso(texto) y on_fin(ok, mensaje) se llaman DESDE EL HILO:
        en tkinter hay que pasarlos por una cola (ver ConfigFrame._ui)."""
        if self.ocupado:
            return False
        self.ocupado = True
        threading.Thread(
            target=self._hilo, args=(datos, on_progreso, on_fin), daemon=True
        ).start()
        return True

    def _hilo(self, datos, on_progreso, on_fin):
        progreso = on_progreso or (lambda _t: None)
        try:
            asyncio.run(self._enviar_async(_a_escrituras(datos), progreso))
            ok, msg = True, "Datos enviados por Bluetooth. El ESP32 se reiniciará."
        except Exception as e:
            ok, msg = False, str(e) or e.__class__.__name__
        finally:
            self.ocupado = False
        if on_fin:
            on_fin(ok, msg)

    async def _enviar_async(self, escrituras, progreso):
        progreso(f"Buscando '{self.nombre_ble}' por Bluetooth...")
        dispositivo = await BleakScanner.find_device_by_name(
            self.nombre_ble, timeout=self.timeout_scan
        )
        if dispositivo is None:
            raise RuntimeError(
                f"No se encontró '{self.nombre_ble}'. El ESP32 solo anuncia ese "
                "nombre si no tiene configuración guardada o falló el Wi-Fi."
            )

        async with BleakClient(dispositivo, timeout=15) as cliente:
            total = len(escrituras)
            for i, (etiqueta, uuid, valor) in enumerate(escrituras, 1):
                progreso(f"Enviando {etiqueta} ({i}/{total})...")
                try:
                    await cliente.write_gatt_char(
                        uuid, str(valor).encode("utf-8"), response=True
                    )
                except Exception:
                    # Tras el último dato el ESP32 apaga el BLE: no es un error real.
                    if i == total:
                        break
                    raise
                await asyncio.sleep(0.15)
