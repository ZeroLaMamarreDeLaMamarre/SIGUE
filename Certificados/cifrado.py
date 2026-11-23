import os

try:
    from cryptolib import aes
except ImportError:
    from ucryptolib import aes

# IMPORTANTE: exactamente 16 bytes y la MISMA llave en tu app/cliente.
# Cámbiala por una propia antes de usarla en producción.
LLAVE = b"Cl4veParqueo2026"


class Cifrado:
    """AES-128-CBC con IV aleatorio y relleno PKCS7.

    Formato: IV (16 bytes) + texto cifrado (múltiplo de 16).
    Con 30 caracteres máx. -> 16 + 32 = 48 bytes (cabe en el buffer BLE de 64).
    """

    MODO_CBC = 2
    TAM_BLOQUE = 16

    def __init__(self, llave=LLAVE):
        if len(llave) != 16:
            raise ValueError("La llave debe tener 16 bytes")
        self.llave = llave

    def cifrar(self, texto: str) -> bytes:
        datos = texto.encode("utf-8")
        relleno = self.TAM_BLOQUE - (len(datos) % self.TAM_BLOQUE)
        datos += bytes([relleno]) * relleno
        iv = os.urandom(self.TAM_BLOQUE)
        return iv + aes(self.llave, self.MODO_CBC, iv).encrypt(datos)

    def descifrar(self, datos) -> str:
        datos = bytes(datos)
        if len(datos) < 32 or len(datos) % self.TAM_BLOQUE != 0:
            raise ValueError("Longitud cifrada invalida")
        iv, cifrado = datos[:16], datos[16:]
        claro = aes(self.llave, self.MODO_CBC, iv).decrypt(cifrado)
        relleno = claro[-1]
        if relleno < 1 or relleno > self.TAM_BLOQUE:
            raise ValueError("Relleno invalido (llave incorrecta?)")
        return claro[:-relleno].decode("utf-8")