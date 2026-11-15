import esp32


class NVS:
    def __init__(self, namespace):
        self.nvs = esp32.NVS(namespace)

    def guardar_cadena(self, clave: str, valor: str):
        # Convertimos el string a bytes usando utf-8
        self.nvs.set_blob(clave, valor.encode("utf-8"))
        self.nvs.commit()

    def obtener_cadena(self, clave):
        try:
            # Creamos un buffer de un tamaño prudente para leer el blob
            buffer = bytearray(128)
            longitud = self.nvs.get_blob(clave, buffer)

            # Recortamos el buffer a los bytes reales leídos y decodificamos
            cadena = buffer[:longitud].decode("utf-8").strip()
            return cadena if len(cadena) > 0 else None
        except Exception:
            return None

    def verificar_existencia(self, clave):
        try:
            buffer = bytearray(128)
            longitud = self.nvs.get_blob(clave, buffer)
            return longitud > 0
        except Exception:
            return False

    def eliminar_cadena(self, clave):
        try:
            self.nvs.erase_key(clave)
            self.nvs.commit()
            return True
        except Exception:
            print("No se ha podido encontrar o eliminar la clave.")
            return False