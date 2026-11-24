"""
Cliente MQTT del panel (lado PC): se conecta al broker y publica comandos
al ESP32 en  estacionamiento/comandos/<nombre>.

La configuración (contraseñas incluidas) viaja CIFRADA con la misma llave
AES-128-CBC que usa cifrado.py en el ESP32:  base64(IV + AES(JSON)).

Requiere:  pip install paho-mqtt pycryptodome
"""

import base64
import json
import os
import socket
import ssl
import threading
import time

import paho.mqtt.client as mqtt
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

LLAVE = b"Cl4veParqueo2026"  # DEBE ser igual a LLAVE de cifrado.py
TOPICO_COMANDOS = "estacionamiento/comandos/{}"
TOPICO_ESTADO = "estacionamiento/estado/{}"
INTERVALO_SONDEO = 5  # segundos entre peticiones de "estado" al ESP32
PUERTO_TLS = 8883
# Certificado CA por defecto (PEM, el mismo ca.crt que usa el ESP32). Se puede
# elegir otro desde la interfaz.
RUTA_CA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ca.crt")
# True: además de validar la CA, exige que el certificado del broker incluya la IP/host
# que escribes en la app. Déjalo en False si te conectas por IP y el certificado no la trae.
VERIFICAR_HOST = False


def cifrar_texto(texto: str) -> str:
    iv = os.urandom(16)
    cifrado = AES.new(LLAVE, AES.MODE_CBC, iv).encrypt(pad(texto.encode("utf-8"), 16))
    return base64.b64encode(iv + cifrado).decode("ascii")


def descifrar_texto(b64) -> str:
    """Inverso de cifrar_texto / Cifrado.cifrar() del ESP32: base64(IV + AES-CBC + PKCS7)."""
    datos = base64.b64decode(b64)
    if len(datos) < 32 or len(datos) % 16 != 0:
        raise ValueError("Longitud cifrada inválida")
    iv, cifrado = datos[:16], datos[16:]
    return unpad(AES.new(LLAVE, AES.MODE_CBC, iv).decrypt(cifrado), 16).decode("utf-8")


class PanelMQTT:
    def __init__(self, on_estado=None, on_datos=None):
        """on_estado(ok, texto): ok = True/False/None(conectando).
        on_datos(resumen): dict ya descifrado del ESP32. Ambos se llaman desde hilos."""
        self.on_estado = on_estado or (lambda ok, t: None)
        self.on_datos = on_datos or (lambda d: None)
        self.cliente = None
        self.nombre = ""
        self._conectado = threading.Event()
        self._stop_sondeo = threading.Event()

    @property
    def conectado(self):
        return self._conectado.is_set()

    # ------------------------------------------------------------------
    def conectar(self, cfg):
        self.desconectar()
        try:
            puerto = int(cfg["mqtt_port"])
        except (TypeError, ValueError):
            self.on_estado(False, "Puerto inválido")
            return

        try:
            cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cfg["mqtt_id"])
        except AttributeError:  # paho-mqtt 1.x
            cliente = mqtt.Client(client_id=cfg["mqtt_id"])

        if cfg.get("mqtt_user"):
            cliente.username_pw_set(cfg["mqtt_user"], cfg.get("mqtt_pass") or None)

        contexto = None
        if puerto == PUERTO_TLS:
            try:
                contexto = self._contexto_tls(cfg.get("ca_cert") or RUTA_CA)
            except Exception as e:
                self.on_estado(False, str(e))
                return
            cliente.tls_set_context(contexto)

        self.nombre = (cfg.get("dispositivo") or "").strip()
        cliente.on_connect = self._on_connect
        cliente.on_message = self._on_message
        cliente.on_disconnect = self._on_disconnect
        cliente.on_connect_fail = self._on_connect_fail
        cliente.reconnect_delay_set(1, 30)

        self.cliente = cliente
        self.on_estado(None, "Conectando al broker MQTT...")
        threading.Thread(
            target=self._arrancar,
            args=(cliente, cfg["mqtt_ip"], puerto, contexto),
            daemon=True,
        ).start()

    # ---- TLS / certificado ------------------------------------------------
    @staticmethod
    def _contexto_tls(ruta_ca):
        """Contexto que SOLO confía en la CA indicada (nada del almacén del sistema)."""
        if not os.path.isfile(ruta_ca):
            raise FileNotFoundError(
                f"No se encontró el certificado CA del broker: {ruta_ca}"
            )
        try:
            contexto = ssl.create_default_context(cafile=ruta_ca)
        except (ssl.SSLError, OSError) as e:
            raise ValueError(
                f"El certificado CA no es válido (debe ser PEM, texto con "
                f"'BEGIN CERTIFICATE'): {e}"
            )
        contexto.minimum_version = ssl.TLSVersion.TLSv1_2
        contexto.check_hostname = VERIFICAR_HOST
        # Python 3.13+ activa por defecto una verificación "estricta" que rechaza los
        # certificados autofirmados/caseros sin extensiones (error "invalid CA certificate"),
        # aunque sean exactamente los del broker. La cadena SIGUE validándose contra tu CA.
        contexto.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
        return contexto

    @staticmethod
    def _probar_tls(ip, puerto, contexto):
        """Handshake de prueba: paho no explica por qué falla un TLS, esto sí."""
        with socket.create_connection((ip, puerto), timeout=6) as sock:
            with contexto.wrap_socket(sock, server_hostname=ip):
                pass

    # Pistas por código de error de OpenSSL
    _PISTAS_TLS = {
        9: "El certificado aún no es válido: revisa la fecha y hora de esta PC.",
        10: "El certificado del broker está caducado: hay que regenerarlo.",
        18: "El broker usa un certificado autofirmado: en ca.crt pon ESE mismo certificado.",
        19: "La cadena termina en una CA que no es la de ca.crt.",
        20: "ca.crt no contiene la CA que firmó el certificado del broker.",
        21: "ca.crt no contiene la CA que firmó el certificado del broker.",
        62: "El nombre/IP de la app no coincide con el del certificado (VERIFICAR_HOST).",
        89: "La IP de la app no figura en el certificado (VERIFICAR_HOST).",
    }

    @classmethod
    def _explicar_tls(cls, e, ip, puerto):
        if isinstance(e, ssl.SSLCertVerificationError):
            pista = cls._PISTAS_TLS.get(e.verify_code, "")
            return (
                f"Certificado rechazado [código {e.verify_code}: {e.verify_message}]. "
                f"{pista}".strip()
            )
        if isinstance(e, ssl.SSLError):
            return f"Falló el handshake TLS con el broker: {e}"
        return f"No se pudo alcanzar el broker en {ip}:{puerto} ({e})"

    def _arrancar(self, cliente, ip, puerto, contexto):
        if contexto is not None:
            try:
                self._probar_tls(ip, puerto, contexto)
            except Exception as e:
                if cliente is self.cliente:
                    self.on_estado(False, self._explicar_tls(e, ip, puerto))
                return
        if cliente is not self.cliente:  # el usuario volvió a pulsar "Conectar"
            return
        cliente.connect_async(ip, puerto, keepalive=60)
        cliente.loop_start()

    def desconectar(self):
        cliente, self.cliente = self.cliente, None
        self._conectado.clear()
        self._stop_sondeo.set()
        if cliente is not None:
            try:
                cliente.disconnect()
                cliente.loop_stop()
            except Exception:
                pass

    # ---- callbacks (compatibles con paho 1.x y 2.x) --------------------
    def _on_connect(self, cliente, userdata, flags, rc, *extra):
        if cliente is not self.cliente:
            return
        codigo = int(getattr(rc, "value", rc))
        if codigo == 0:
            self._conectado.set()
            self.on_estado(True, "Conectado al broker MQTT")
            # Suscribir aquí (no antes) para que se repita tras cada reconexión
            topico_estado = TOPICO_ESTADO.format(self.nombre or "+")
            cliente.subscribe(topico_estado, qos=0)
            if self.nombre:
                self._iniciar_sondeo(cliente)
        else:
            self.on_estado(False, f"El broker rechazó la conexión (código {codigo})")

    def _on_message(self, cliente, userdata, msg):
        """Descifra la trama de estado del ESP32 y se la pasa a la interfaz."""
        try:
            crudo = msg.payload.strip()
            try:
                texto = descifrar_texto(crudo)          # normal: viene cifrada
            except Exception:
                texto = crudo.decode("utf-8")           # por si CIFRAR_ESTADO = False
            datos = json.loads(texto)
            if not isinstance(datos, dict) or "espacios" not in datos:
                return
            self.on_datos(datos)
        except Exception as e:
            self.on_estado(
                False, f"Trama de estado ilegible (¿llave AES distinta?): {e}"
            )

    # ---- petición periódica de "estado" ---------------------------------
    def _iniciar_sondeo(self, cliente):
        self._stop_sondeo.set()            # detiene un sondeo anterior (reconexión)
        stop = self._stop_sondeo = threading.Event()
        topico = TOPICO_COMANDOS.format(self.nombre)

        def _bucle():
            while not stop.is_set():
                if self.conectado:
                    cliente.publish(topico, "estado")
                if stop.wait(INTERVALO_SONDEO):
                    break

        threading.Thread(target=_bucle, daemon=True).start()

    def _on_disconnect(self, cliente, userdata, *args):
        if cliente is not self.cliente:
            return
        self._conectado.clear()
        self.on_estado(False, "Desconectado del broker (reintentando...)")

    def _on_connect_fail(self, cliente, userdata):
        if cliente is self.cliente:
            self.on_estado(False, "No se pudo conectar al broker (reintentando...)")

    # ------------------------------------------------------------------
    def enviar_config(self, nombre_destino, datos, on_fin):
        """Publica el comando 'configurar' (cifrado) en segundo plano."""
        self.enviar_comando(nombre_destino, {"comando": "configurar", **datos}, on_fin)

    def enviar_comando(self, nombre_destino, trama, on_fin):
        """Cifra y publica un comando en estacionamiento/comandos/<nombre>.
        on_fin(ok, mensaje) se llama desde el hilo."""
        threading.Thread(
            target=self._publicar, args=(nombre_destino, trama, on_fin), daemon=True
        ).start()

    def _publicar(self, nombre_destino, trama, on_fin):
        try:
            if not self.conectado:
                raise RuntimeError(
                    "El panel no está conectado al broker (pestaña 'Configuración del Panel')"
                )
            topico = TOPICO_COMANDOS.format(nombre_destino)
            trama = {**trama, "ts": int(time.time())}  # el ESP32 descarta comandos viejos
            payload = cifrar_texto(json.dumps(trama))
            info = self.cliente.publish(topico, payload, qos=1)
            info.wait_for_publish(timeout=8)
            if not info.is_published():
                raise RuntimeError("El broker no confirmó la publicación")
            on_fin(True, f"Comando '{trama['comando']}' enviado a [{topico}]. El ESP32 debería reiniciarse.")
        except Exception as e:
            on_fin(False, str(e) or e.__class__.__name__)
