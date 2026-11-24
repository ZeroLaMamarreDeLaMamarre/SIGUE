from bluethooth_conf import Bluetooth
from wifi import WiFi
from estacionamiento import Estacionamiento
from semaforo import Semaforo
from gestor_nvs import NVS
from machine import reset
from gestor_mqtt import MQTT
import time
import sys
import json
import binascii

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
            # El certificado del broker tiene fecha de validez: sin hora correcta
            # (el ESP32 arranca en el año 2000) la verificación TLS falla.
            try:
                wifi.sincronizar_hora()
            except Exception as e:
                print("No se pudo sincronizar la hora (el TLS podría fallar):", e)
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
# Configuración remota por MQTT (comando "configurar")
# ----------------------------------------------------------------------
def comando_vigente(datos, tolerancia=120):
    """Anti-repetición: el comando trae 'ts' (segundos Unix UTC de la PC) y solo vale
    unos minutos. Si el reloj del ESP32 no está sincronizado no se puede comprobar."""
    if time.localtime()[0] < 2024:
        return True
    ts = datos.get("ts")
    if not isinstance(ts, int):
        return False
    ahora = time.time()
    if time.gmtime(0)[0] == 2000:  # En el ESP32 time.time() cuenta desde el año 2000
        ahora += 946684800
    return abs(ahora - ts) <= tolerancia


def restablecer_remoto(mqtt: MQTT):
    """Borra wifi, mqtt y nombre de la NVS y reinicia: queda en modo configuración BLE."""
    print("Restablecimiento remoto solicitado . . .")
    mqtt.desconectar()  # Publica "offline" limpio antes de borrar
    restablecer_dispositivo()
    time.sleep(1)
    reset()


def aplicar_configuracion(mqtt: MQTT, datos: dict):
    """Guarda en NVS lo recibido por el comando y reinicia.
    Solo se escriben los campos presentes y no vacíos."""
    wifi = datos.get("wifi") or {}
    broker = datos.get("mqtt") or {}
    disp = datos.get("dispositivo") or {}

    try:
        if broker.get("mqtt_port") is not None:
            int(broker["mqtt_port"])
    except (TypeError, ValueError):
        print("Configuración rechazada: puerto MQTT inválido")
        return

    escrituras = [
        (RUTA_WIFI, CLAVES_WIFI[0], wifi.get("ssid")),
        (RUTA_WIFI, CLAVES_WIFI[1], wifi.get("password")),
        (RUTA_MQTT, CLAVES_MQTT[0], broker.get("mqtt_id")),
        (RUTA_MQTT, CLAVES_MQTT[1], broker.get("mqtt_ip")),
        (RUTA_MQTT, CLAVES_MQTT[2], broker.get("mqtt_port")),
        (RUTA_MQTT, CLAVES_MQTT[3], broker.get("mqtt_user")),
        (RUTA_MQTT, CLAVES_MQTT[4], broker.get("mqtt_pass")),
        (RUTA_DISPOSITIVO, CLAVES_DISPOSITIVO[0], disp.get("nuevo_nombre")),
    ]

    aplicadas = 0
    for ruta, clave, valor in escrituras:
        if valor is None or not str(valor).strip():
            continue
        NVS(ruta).guardar_cadena(clave, str(valor).strip())
        aplicadas += 1

    if aplicadas:
        print(f"Configuración remota aplicada ({aplicadas} datos). Reiniciando . . .")
        mqtt.desconectar()  # Publica "offline" limpio antes de reiniciar
        time.sleep(1)
        reset()


# ----------------------------------------------------------------------
# Estacionamiento
# ----------------------------------------------------------------------
def estacionamiento(mqtt: MQTT):
    estacionamiento = Estacionamiento()
    semaforo = Semaforo()
    topico_comandos = TOPICO_COMANDOS.format(NOMBRE)
    topico_estado = TOPICO_ESTADO.format(NOMBRE)

    def al_recibir_comando(topico, datos):
        print("Comando recibido en", topico)
        cifrado = False

        # Un comando cifrado llega como texto base64: base64(IV + AES(JSON))
        if isinstance(datos, str) and datos.strip().lower() != "estado":
            try:
                datos = json.loads(mqtt.cifrado.descifrar(binascii.a2b_base64(datos)))
                cifrado = True
            except Exception as e:
                print("Comando ignorado (no se pudo descifrar):", e)
                return

        # Acepta {"comando": "estado"} o el texto plano "estado"
        comando = datos.get("comando") if isinstance(datos, dict) else datos
        comando = str(comando).strip().lower()

        if comando == "estado":
            mqtt.publicar_trama(topico_estado, estacionamiento.resumen(), cifrar=CIFRAR_ESTADO)
        elif comando in ("configurar", "restablecer"):
            # Comandos que modifican el equipo: SOLO si llegaron cifrados y vigentes
            if not (cifrado and isinstance(datos, dict)):
                print(f"Comando '{comando}' ignorado: debe llegar cifrado")
                return
            if not comando_vigente(datos):
                print(f"Comando '{comando}' ignorado: fuera de vigencia (reloj de la PC?)")
                return
            if comando == "configurar":
                aplicar_configuracion(mqtt, datos)
            else:
                restablecer_remoto(mqtt)
        else:
            print("Comando desconocido:", comando)

    mqtt.suscribir_trama(topico_comandos, al_recibir_comando)
    print(f"Escuchando comandos en [{topico_comandos}] · respondiendo en [{topico_estado}]")

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
