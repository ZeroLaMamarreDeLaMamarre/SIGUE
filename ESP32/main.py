from bluethooth_conf import Bluetooth
from wifi import WiFi
from estacionamiento import Estacionamiento
from semaforo import Semaforo
from gestor_nvs import NVS
from machine import reset
from gestor_mqtt import MQTT
import time
import sys

NOMBRE_CONFIG = "Esp32-C0NF"  # Nombre BLE durante la configuración
NOMBRE = NOMBRE_CONFIG  # Nombre real del dispositivo (se carga desde NVS)

RUTA_WIFI = "wifi_conf"
CLAVES_WIFI = ["SSID", "PASSWORD"]
RUTA_DISPOSITIVO = "sys_conf"
CLAVES_DISPOSITIVO = ["NOMBRE"]
RUTA_MQTT = "mqtt_conf"
CLAVES_MQTT = ["ID", "IP", "PUERTO", "USUARIO", "PASSWORD"]

TOPICO_COMANDOS = "estacionamiento/comandos/{}"  # {} = NOMBRE del dispositivo
TOPICO_ESTADO = "estacionamiento/estado/{}"  # Aquí responde al comando "estado"
TOPICO_CONEXION = "estacionamiento/conexion/{}"  # online/offline (última voluntad)

CIFRAR_ESTADO = True  # True: el estado se publica cifrado (AES + base64)

FILAS = 2
COLUMNAS = 3


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------
def verificar_claves(ruta, claves: list):
    """True si todas las claves existen y tienen valor.
    Tolera que NVS lance excepción cuando la clave no existe."""
    nvs = NVS(ruta)

    for clave in claves:
        try:
            if not nvs.obtener_cadena(clave):
                return False
        except Exception:
            return False

    return True


# ----------------------------------------------------------------------
# Primer inicio: UN solo objeto Bluetooth para todo
# ----------------------------------------------------------------------
def primer_inicio():
    ble = Bluetooth(NOMBRE_CONFIG)

    # --- WiFi ---
    print("Esperando datos de wifi por bluetooth...")
    ssid, password = ble.esperar_wifi()
    print(f"Datos obtenidos ssid: {ssid}, password: {password}")
    guardar_wifi_nvs(ssid, password)

    # --- MQTT ---
    print("Esperando datos de mqtt por bluetooth...")
    datos_mqtt = ble.esperar_mqtt()
    guardar_mqtt_nvs(datos_mqtt)

    # --- Nombre del dispositivo ---
    print("Esperando nombre del dispositivo por bluetooth...")
    nombre = ble.esperar_nombre()
    print(f"El nombre del dispositivo es: {nombre}")
    NVS(RUTA_DISPOSITIVO).guardar_cadena(CLAVES_DISPOSITIVO[0], nombre)
    print("Datos de dispositivo guardados")

    ble.apagar()
    time.sleep(1)


def guardar_wifi_nvs(ssid, password):
    nvs = NVS(RUTA_WIFI)
    nvs.guardar_cadena(CLAVES_WIFI[0], ssid)
    nvs.guardar_cadena(CLAVES_WIFI[1], password)
    print("Datos de wifi almacenados en nvs con éxito")


def guardar_mqtt_nvs(datos_mqtt):
    nvs = NVS(RUTA_MQTT)
    for clave, dato in zip(CLAVES_MQTT, datos_mqtt):
        nvs.guardar_cadena(clave, str(dato))
        print(f"Dato {clave}: {dato}, guardado con éxito")


# ----------------------------------------------------------------------
# WiFi
# ----------------------------------------------------------------------
def iniciar_wifi():
    nvs = NVS(RUTA_WIFI)
    ble = None  # Solo se crea si la conexión falla

    if not verificar_claves(RUTA_WIFI, CLAVES_WIFI):
        ble = Bluetooth(NOMBRE_CONFIG)
        ssid, password = ble.esperar_wifi()
        guardar_wifi_nvs(ssid, password)

    wifi = WiFi()

    while True:
        ssid = nvs.obtener_cadena(CLAVES_WIFI[0])
        password = nvs.obtener_cadena(CLAVES_WIFI[1])

        print(f"Intentando conectar a la red: {ssid}")
        resultado = wifi.conectar_red(ssid, password)

        if resultado and "Conexión exitosa" in str(resultado):
            print("Conexión exitosa")
            break

        print("Fallo en conexión, esperando nuevas credenciales por bluetooth")
        if ble is None:
            ble = Bluetooth(NOMBRE_CONFIG)
        else:
            ble.reiniciar_wifi()  # Evita leer los datos viejos

        ssid, password = ble.esperar_wifi()
        guardar_wifi_nvs(ssid, password)

    if ble is not None:
        ble.apagar()
        time.sleep(1)


# ----------------------------------------------------------------------
# MQTT
# ----------------------------------------------------------------------
def iniciar_mqtt():
    nvs = NVS(RUTA_MQTT)
    print("Obteniendo datos de mqtt")

    if not verificar_claves(RUTA_MQTT, CLAVES_MQTT):
        ble = Bluetooth(NOMBRE_CONFIG)
        print("Esperando datos de mqtt por bluetooth...")
        guardar_mqtt_nvs(ble.esperar_mqtt())
        ble.apagar()
        time.sleep(1)

    mqtt = MQTT(
        id_cliente=nvs.obtener_cadena(CLAVES_MQTT[0]),
        ip_servidor=nvs.obtener_cadena(CLAVES_MQTT[1]),
        puerto=int(nvs.obtener_cadena(CLAVES_MQTT[2])),
        usuario=nvs.obtener_cadena(CLAVES_MQTT[3]),
        password=nvs.obtener_cadena(CLAVES_MQTT[4]),
        nombre=NOMBRE,
        topico_lwt=TOPICO_CONEXION.format(NOMBRE)
    )

    return mqtt


def iniciar_dispositivo():
    global NOMBRE

    if not verificar_claves(RUTA_DISPOSITIVO, CLAVES_DISPOSITIVO):
        primer_inicio()
        reset()

    NOMBRE = NVS(RUTA_DISPOSITIVO).obtener_cadena(CLAVES_DISPOSITIVO[0])
    print(f"Dispositivo: {NOMBRE}")

    return segundo_inicio()


def segundo_inicio():
    iniciar_wifi()
    mqtt = iniciar_mqtt()
    return mqtt


def restablecer_dispositivo():
    print("Eliminando información de dispositivo . . .")
    nvs = NVS(RUTA_DISPOSITIVO)
    for clave in CLAVES_DISPOSITIVO:
        nvs.eliminar_cadena(clave)

    print("Eliminando información de wifi . . .")
    nvs = NVS(RUTA_WIFI)
    for clave in CLAVES_WIFI:
        nvs.eliminar_cadena(clave)

    print("Eliminando información de mqtt . . .")
    nvs = NVS(RUTA_MQTT)
    for clave in CLAVES_MQTT:
        nvs.eliminar_cadena(clave)


# ----------------------------------------------------------------------
# Estacionamiento
# ----------------------------------------------------------------------
def estacionamiento(mqtt: MQTT):
    estacionamiento = Estacionamiento()
    semaforo = Semaforo()
    topico_comandos = TOPICO_COMANDOS.format(NOMBRE)
    topico_estado = TOPICO_ESTADO.format(NOMBRE)

    def al_recibir_comando(topico, datos):
        # Acepta {"comando": "estado"} o el texto plano "estado"
        comando = datos.get("comando") if isinstance(datos, dict) else datos
        if str(comando).strip().lower() == "estado":
            mqtt.publicar_trama(topico_estado, estacionamiento.resumen(), cifrar=CIFRAR_ESTADO)

    mqtt.suscribir_trama(topico_comandos, al_recibir_comando)

    ocupados_anterior = -1
    while True:
        mqtt.escuchar_mensajes()

        resumen = estacionamiento.resumen()
        # Solo toca los LEDs cuando cambia la ocupación (evita parpadeo)
        if resumen["ocupados"] != ocupados_anterior:
            ocupados_anterior = resumen["ocupados"]
            semaforo.cambiar_estado(resumen["porcentaje"])

        time.sleep(0.2)


def main():
    # restablecer_dispositivo()
    mqtt = iniciar_dispositivo()

    while True:
        try:
            mqtt.conectar()
            break
        except Exception as e:
            print("No se pudo conectar al broker, reintentando en 5 s")
            sys.print_exception(e)  # Muestra el motivo real del fallo
            time.sleep(5)

    estacionamiento(mqtt)


if __name__ == "__main__":
    main()
