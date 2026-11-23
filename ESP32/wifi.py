import network
import time
import ntptime

# Zona horaria local: México
OFFSET_LOCAL = -6 * 3600


_ERRORES = {}
for _nombre, _mensaje in (
        ("STAT_WRONG_PASSWORD", "Contraseña incorrecta"),
        ("STAT_NO_AP_FOUND", "No se ha podido localizar el punto de acceso indicado"),
        ("STAT_ASSOC_FAIL", "Fallo de asociación con el punto de acceso"),
        ("STAT_HANDSHAKE_TIMEOUT", "Fallo de autenticación (contraseña incorrecta o seguridad no compatible)"),
):
    _valor = getattr(network, _nombre, None)
    if _valor is not None:
        _ERRORES[_valor] = _mensaje


class WiFi:
    """Administra la conexión WiFi en modo estación."""

    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)

    # ------------------------------------------------------------------
    def escanear_redes(self):
        print("Escaneando redes . . .")
        if not self.wlan.active():
            self.wlan.active(True)

        redes = []
        for red in self.wlan.scan():
            try:
                ssid = red[0].decode("utf-8")
            except Exception:
                continue  # SSID con bytes inválidos

            if not ssid:
                continue  # Red oculta

            redes.append({
                "ssid": ssid,
                "rssi": red[3],  # Potencia de la señal en dBm
            })

        # Más fuerte primero
        redes.sort(key=lambda r: r["rssi"], reverse=True)
        return redes

    # ------------------------------------------------------------------
    def conectar_red(self, ssid, password, timeout=15):
        """Intenta conectar. Devuelve un texto; si empieza con
        'Conexión exitosa' la conexión fue correcta."""
        if not ssid:
            return "SSID vacío"

        # Reiniciamos la interfaz para limpiar estados de intentos anteriores
        self.wlan.active(False)
        time.sleep(0.5)
        self.wlan.active(True)

        self.wlan.connect(ssid, password)

        inicio = time.ticks_ms()
        limite_ms = timeout * 1000

        while not self.wlan.isconnected():
            estado = self.wlan.status()

            if estado in _ERRORES:
                self.wlan.disconnect()  # Detiene los reintentos automáticos
                return _ERRORES[estado]

            # ticks_diff no se ve afectado si la hora cambia por NTP
            if time.ticks_diff(time.ticks_ms(), inicio) > limite_ms:
                self.wlan.disconnect()
                return "Tiempo de espera agotado"

            time.sleep(0.5)

        return f"Conexión exitosa con {ssid}"

    # ------------------------------------------------------------------
    def desconectar_red(self):
        if self.wlan.isconnected():
            self.wlan.disconnect()
            return "Desconectado exitosamente"

        return "No hay ninguna red conectada"

    # ------------------------------------------------------------------
    def status(self):
        """Devuelve siempre las mismas claves: conectado, ssid, rssi."""
        if not self.wlan.isconnected():
            return {
                "conectado": False,
                "ssid": None,
                "rssi": None,
            }

        try:
            ssid = self.wlan.config("essid")
            if isinstance(ssid, bytes):
                ssid = ssid.decode("utf-8")
        except Exception:
            ssid = "Desconocido"

        try:
            rssi = self.wlan.status("rssi")
        except Exception:
            rssi = None

        return {
            "conectado": True,
            "ssid": ssid,
            "rssi": rssi,
        }

    # ------------------------------------------------------------------
    def sincronizar_hora(self, intentos=5):

        if not self.wlan.isconnected():
            raise RuntimeError("No hay conexión WiFi para sincronizar la hora")

        ntptime.host = "pool.ntp.org"
        try:
            ntptime.timeout = 5
        except Exception:
            pass

        for intento in range(1, intentos + 1):
            try:
                ntptime.settime()
                t = time.localtime()
                print(f"Hora NTP sincronizada: {t[0]}-{t[1]:02d}-{t[2]:02d} "
                      f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d} UTC")
                return
            except Exception as e:
                print(f"Intento fallido {intento}/{intentos}: {e}")
                time.sleep(2)

        raise RuntimeError(
            "Fallo en validación TLS: No se obtuvo tiempo de referencia "
            "para verificar certificados."
        )

    def hora_local(self):
        """Devuelve time.localtime() ajustado a la zona horaria local,
        sin modificar el RTC."""
        return time.localtime(time.time() + OFFSET_LOCAL)
