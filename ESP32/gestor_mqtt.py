from umqtt.robust import MQTTClient
from umqtt.simple import MQTTClient as _ClienteSimple
import json
import time
import binascii

from cifrado import Cifrado

MSG_ONLINE = b'{"estado": "online"}'
MSG_OFFLINE = b'{"estado": "offline"}'


class _ClienteRobusto(MQTTClient):
    """umqtt.robust reconecta solo dentro de publish/wait_msg, pero NO vuelve a
    suscribirse tras reconectar. Esta versión restaura las suscripciones y el
    aviso "online", y permite reintentar la conexión una sola vez sin bloquear."""

    topicos = None
    topico_lwt = None

    def _restaurar(self):
        for t in self.topicos or []:
            self.subscribe(t)
        if self.topico_lwt:
            _ClienteSimple.publish(self, self.topico_lwt, MSG_ONLINE, True, 1)
        print("Reconectado: suscripciones restauradas")

    def reconnect(self):  # ruta interna de umqtt.robust
        resultado = super().reconnect()
        try:
            self._restaurar()
        except Exception as e:
            print("No se pudieron restaurar las suscripciones:", e)
        return resultado

    def intentar_reconexion(self):
        """Un único intento (lanza excepción si falla); no bloquea el programa."""
        try:
            self.sock.close()
        except Exception:
            pass
        super().connect(True)
        self._restaurar()


class MQTT:
    def __init__(self,
                 id_cliente: str,
                 ip_servidor: str,
                 puerto: int,
                 usuario: str,
                 password: str,
                 ca_cert_path="ca.crt",
                 nombre="Esp32-C0NF",
                 topico_lwt=None,
                 keepalive=60):
        self.id_cliente = id_cliente
        self.ip_servidor = ip_servidor
        self.puerto = puerto
        self.usuario = usuario
        self.password = password
        self.ca_cert_path = ca_cert_path
        self.nombre = nombre
        # Tópico de la última voluntad (LWT): el broker publica "offline" aquí si el ESP32 se cae
        self.topico_lwt = topico_lwt or f"estacionamiento/conexion/{nombre}"
        self.keepalive = keepalive
        self._ultimo_ping = 0
        self._ultimo_intento = 0
        self.cifrado = Cifrado()  # Para publicar tramas cifradas
        self.mqtt = None
        self.ca_cert = None

        self._cargar_certificados()

    def _cargar_certificados(self):
        try:
            with open(self.ca_cert_path, "rb") as certificado:
                self.ca_cert = certificado.read()
        except OSError:
            self.ca_cert = None
            print(f"⚠️ No se encontró el certificado '{self.ca_cert_path}' en el ESP32: "
                  "la conexión TLS al broker fallará o no se verificará")

    def conectar(self):
        print("Iniciando conexion con el broker . . .")
        parametros_ssl = {
            "cadata": self.ca_cert,
            "server_side": False
        }

        self.mqtt = _ClienteRobusto(
            client_id=self.id_cliente,
            server=self.ip_servidor,
            port=self.puerto,
            user=self.usuario,
            password=self.password,
            keepalive=self.keepalive,
            ssl=True,
            ssl_params=parametros_ssl
        )

        self.mqtt.topicos = []
        self.mqtt.topico_lwt = self.topico_lwt.encode('utf-8')

        # Última voluntad: debe configurarse ANTES de connect()
        self.mqtt.set_last_will(self.topico_lwt.encode('utf-8'), MSG_OFFLINE, retain=True, qos=1)

        try:
            self.mqtt.connect()
            self.mqtt.publish(f"{self.nombre}".encode('utf-8'), b"Dispositivo conectado")
            # Avisa que está en línea (retenido, reemplaza el "offline" de la última voluntad)
            self.mqtt.publish(self.topico_lwt.encode('utf-8'), MSG_ONLINE, retain=True, qos=1)
            self._ultimo_ping = time.ticks_ms()
            print("Dispositivo conectado")
        except Exception as e:
            print("Conexion fallida")
            raise e

    def publicar_trama(self, topico: str, datos: dict, cifrar=False):
        """
        Serializa un diccionario a JSON y lo publica en el tópico indicado.
        Con cifrar=True el JSON se cifra con AES (ver cifrado.py) y se envía
        en base64: base64(IV + JSON cifrado).
        """
        try:
            # Convertir el diccionario a string JSON y luego a bytes UTF-8
            texto = json.dumps(datos)
            if cifrar:
                payload = binascii.b2a_base64(self.cifrado.cifrar(texto)).strip()
            else:
                payload = texto.encode('utf-8')
            topico_bytes = topico.encode('utf-8')

            self.mqtt.publish(topico_bytes, payload)
            print(f"Trama {'cifrada ' if cifrar else ''}publicada en [{topico}]: {datos}")
        except Exception as e:
            print(f"❌ Error al publicar trama: {e}")
            raise e

    def suscribir_trama(self, topico: str, callback):
        """
        Se suscribe a un tópico y asigna una función de callback
        que deserializará automáticamente la trama JSON recibida.
        """
        try:
            def _callback_interno(t, msg):
                try:
                    print(f"Mensaje recibido en [{t.decode('utf-8')}] ({len(msg)} bytes)")
                    # Decodificar y convertir el mensaje JSON de vuelta a diccionario
                    texto = msg.decode('utf-8')
                    try:
                        datos_decodificados = json.loads(texto)
                    except ValueError:
                        datos_decodificados = texto.strip()  # Texto plano (ej. "estado")
                    # Ejecutar la función del usuario pasando el diccionario limpio
                    callback(t.decode('utf-8'), datos_decodificados)
                except Exception as err:
                    print(f"❌ Error al decodificar la trama entrante: {err}")

            # Asignar el callback global de mensajes de la librería umqtt
            self.mqtt.set_callback(_callback_interno)
            self.mqtt.subscribe(topico.encode('utf-8'))
            if topico.encode('utf-8') not in self.mqtt.topicos:
                self.mqtt.topicos.append(topico.encode('utf-8'))  # para restaurarla al reconectar
            print(f"Suscrito correctamente a la trama del tópico: {topico}")
        except Exception as e:
            print(f"❌ Error en la suscripción por trama: {e}")
            raise e

    def escuchar_mensajes(self):
        """
        Revisa mensajes entrantes sin bloquear. Si la conexión se cayó,
        reintenta cada 5 s (sin congelar el resto del programa) y restaura
        las suscripciones.
        """
        try:
            # Con keepalive el broker necesita pings; sin ellos dispararía la última voluntad
            if time.ticks_diff(time.ticks_ms(), self._ultimo_ping) > self.keepalive * 500:
                self.mqtt.ping()
                self._ultimo_ping = time.ticks_ms()
            self.mqtt.check_msg()
        except Exception as e:
            self._recuperar(e)

    def _recuperar(self, error):
        ahora = time.ticks_ms()
        if time.ticks_diff(ahora, self._ultimo_intento) < 5000:
            return
        self._ultimo_intento = ahora
        print(f"❌ Conexión con el broker perdida ({error}). Reconectando . . .")
        try:
            self.mqtt.intentar_reconexion()
            self._ultimo_ping = time.ticks_ms()
        except Exception as e:
            print(f"Reconexión fallida ({e}); se reintentará en 5 s")

    def desconectar(self):
        """Desconexión limpia. El broker NO dispara la última voluntad en este caso,
        por eso se publica "offline" manualmente."""
        try:
            self.mqtt.publish(self.topico_lwt.encode('utf-8'), MSG_OFFLINE, retain=True, qos=1)
            self.mqtt.disconnect()
        except Exception as e:
            print(f"❌ Error al desconectar: {e}")