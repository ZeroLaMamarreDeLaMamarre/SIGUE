import asyncio
from bleak import BleakScanner, BleakClient

# UUID de la característica RX definida en el ESP32
RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
DEVICE_NAME = "ESP32_Config"


async def enviar_configuracion():
    print(f"Buscando dispositivo BLE: {DEVICE_NAME}...")

    # Escanear y buscar el ESP32 por su nombre
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)

    if not device:
        print("❌ No se encontró el ESP32. Asegúrate de que esté encendido.")
        return

    print(f"¡Dispositivo encontrado! Conectando a {device.address}...")

    async with BleakClient(device) as client:
        if client.is_connected:
            print("✅ ¡Conectado exitosamente al ESP32!")

            # Credenciales que deseas enviar (separadas por coma)
            ssid = "MiCasa_WiFi"
            password = "contraseña_segura_123"
            mensaje = f"{ssid},{password}"

            # Enviar los datos a la característica RX del ESP32
            print(f"Enviando credenciales: {mensaje}")
            await client.write_gatt_char(RX_UUID, mensaje.encode('utf-8'))
            print("🚀 ¡Credenciales enviadas correctamente!")


# Ejecutar el script asíncrono
asyncio.run(enviar_configuracion())