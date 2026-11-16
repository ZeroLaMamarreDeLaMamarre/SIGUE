import asyncio
from bleak import BleakClient, BleakScanner

# --- CONFIGURACIÓN DE DATOS A ENVIAR ---
DEVICE_NAME = "Esp32-C0NF"  # Nombre con el que se anuncia tu ESP32

# 1. Credenciales de Wi-Fi
WIFI_SSID = "Cantarella"
WIFI_PASS = "magicalDoc"

# 2. Datos de MQTT (id_cliente, ip_servidor, puerto, usuario, password)
MQTT_ID = "Panchito"
MQTT_IP = "172.30.33.188"
MQTT_PORT = "8883"
MQTT_USER = "Panchito"
MQTT_PASS = "Panchito"

# 3. Nombre personalizado del dispositivo (máx 15 caracteres para NVS)
NUEVO_NOMBRE = "P4NCH1T0"

# --- UUIDs de las características BLE (Deben coincidir exactamente con los del ESP32) ---
RX_WIFI_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
RX_MQTT_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
RX_NAME_UUID = "6E400004-B5A3-F393-E0A9-E50E24DCCA9E"


async def enviar_wifi(client):
    wifi_payload = f"{WIFI_SSID},{WIFI_PASS}"
    print(f"Enviando Wi-Fi -> {wifi_payload}")
    await client.write_gatt_char(RX_WIFI_UUID, wifi_payload.encode("utf-8"))
    await asyncio.sleep(1)
    print("✅ Wi-Fi enviado con éxito.")


async def enviar_mqtt(client):
    mqtt_payload = f"{MQTT_ID},{MQTT_IP},{MQTT_PORT},{MQTT_USER},{MQTT_PASS}"
    print(f"Enviando MQTT -> {mqtt_payload}")
    await client.write_gatt_char(RX_MQTT_UUID, mqtt_payload.encode("utf-8"))
    await asyncio.sleep(1)
    print("✅ Datos MQTT enviados con éxito.")


async def enviar_nombre(client):
    print(f"Enviando Nombre -> {NUEVO_NOMBRE}")
    await client.write_gatt_char(RX_NAME_UUID, NUEVO_NOMBRE.encode("utf-8"))
    await asyncio.sleep(1)
    print("✅ Nombre enviado con éxito.")


async def enviar_todo(client):
    await enviar_wifi(client)
    await enviar_mqtt(client)
    await enviar_nombre(client)
    print("\n✅ ¡Toda la configuración ha sido enviada al ESP32 correctamente!")


async def main():
    print(f"Buscando dispositivo BLE '{DEVICE_NAME}'...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)

    if not device:
        print(f"❌ No se encontró ningún dispositivo con el nombre '{DEVICE_NAME}'.")
        return

    print(f"¡Dispositivo encontrado! Conectando a {device.address}...")

    async with BleakClient(device) as client:
        if not client.is_connected:
            print("❌ No se pudo establecer la conexión BLE.")
            return

        print("¡Conexión BLE exitosa con el ESP32!\n")

        while True:
            print("\n--- MENÚ DE CONFIGURACIÓN BLE ---")
            print("1. Enviar solo Wi-Fi")
            print("2. Enviar solo MQTT")
            print("3. Enviar solo Nombre")
            print("4. Enviar TODO (Wi-Fi + MQTT + Nombre)")
            print("5. Salir")

            opcion = input("Elige una opción (1-5): ").strip()

            if opcion == "1":
                await enviar_wifi(client)
            elif opcion == "2":
                await enviar_mqtt(client)
            elif opcion == "3":
                await enviar_nombre(client)
            elif opcion == "4":
                await enviar_todo(client)
            elif opcion == "5":
                print("Cerrando conexión BLE. ¡Adiós!")
                break
            else:
                print("❌ Opción inválida. Intenta de nuevo.")


if __name__ == "__main__":
    asyncio.run(main())