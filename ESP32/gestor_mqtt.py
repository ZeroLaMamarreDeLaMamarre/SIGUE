from umqtt.robust import MQTTClient
import json


class MQTT:
    def __init__(self,
                 id_cliente: str,
                 ip_servidor: str,
                 puerto: int,
                 usuario: str,
                 password: str,
                 ca_cert_path="ca.crt",
                 nombre="Esp32-C0NF"):
        self.id_cliente = id_cliente
        self.ip_servidor = ip_servidor
        self.puerto = puerto
        self.usuario = usuario
        self.password = password
        self.ca_cert_path = ca_cert_path
        self.nombre = nombre
        self.mqtt = None
        self.ca_cert = None

        self._cargar_certificados()

    def _cargar_certificados(self):
        try:
            with open(self.ca_cert_path, "rb") as certificado:
                self.ca_cert = certificado.read()
        except OSError:
            self.ca_cert = None

    def conectar(self):
        print("Iniciando conexion con el broker . . .")
        parametros_ssl = {
            "cadata": self.ca_cert,
            "server_side": False
        }

        self.mqtt = MQTTClient(
            client_id=self.id_cliente,
            server=self.ip_servidor,
            port=self.puerto,
            user=self.usuario,
            password=self.password,
            ssl=True,
            ssl_params=parametros_ssl
        )

        try:
            self.mqtt.connect()
            self.mqtt.publish(f"{self.nombre}".encode('utf-8'), b"Conexion exitosa")
        except Exception as e:
            print("Conexion fallida")
            raise e

    def publicar_trama(self, topico: str, datos: dict):
        """
        Serializa un diccionario a JSON y lo publica en el tópico indicado.
        """
        try:
            # Convertir el diccionario a string JSON y luego a bytes UTF-8
            payload = json.dumps(datos).encode('utf-8')
            topico_bytes = topico.encode('utf-8')

            self.mqtt.publish(topico_bytes, payload)
            print(f"Trama publicada en [{topico}]: {datos}")
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
                    # Decodificar y convertir el mensaje JSON de vuelta a diccionario
                    datos_decodificados = json.loads(msg.decode('utf-8'))
                    # Ejecutar la función del usuario pasando el diccionario limpio
                    callback(t.decode('utf-8'), datos_decodificados)
                except Exception as err:
                    print(f"❌ Error al decodificar la trama entrante: {err}")

            # Asignar el callback global de mensajes de la librería umqtt
            self.mqtt.set_callback(_callback_interno)
            self.mqtt.subscribe(topico.encode('utf-8'))
            print(f"Suscrito correctamente a la trama del tópico: {topico}")
        except Exception as e:
            print(f"❌ Error en la suscripción por trama: {e}")
            raise e

    def escuchar_mensajes(self):
        """
        Método auxiliar opcional para mantener el ESP32 escuchando
        tramas entrantes de forma no bloqueante (checkeo rápido).
        """
        try:
            self.mqtt.check_msg()
        except Exception as e:
            print(f"❌ Error al revisar mensajes entrantes: {e}")