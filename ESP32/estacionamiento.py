from collections import OrderedDict
from machine import Pin

VALOR_OCUPADO = 0  # Valor que entrega el sensor cuando hay un auto (cámbialo a 1 si es al revés)


class Estacionamiento:
    def __init__(self):
        self.sensores = {
            (1, 1): Pin(13, Pin.IN),
            (1, 2): Pin(14, Pin.IN),
            (1, 3): Pin(19, Pin.IN),
            (2, 1): Pin(27, Pin.IN),
            (2, 2): Pin(32, Pin.IN),
            (2, 3): Pin(33, Pin.IN)
        }

    def estado(self):
        """Devuelve {"fila,columna": 1 (ocupado) / 0 (libre)}"""
        return OrderedDict([
            (f"{fila},{columna}", 1 if pin.value() == VALOR_OCUPADO else 0)
            for (fila, columna), pin in sorted(self.sensores.items())
        ])

    def resumen(self):
        """Estado completo listo para publicar por MQTT."""
        espacios = self.estado()
        total = len(espacios)
        ocupados = sum(espacios.values())
        return {
            "espacios": espacios,
            "total": total,
            "ocupados": ocupados,
            "libres": total - ocupados,
            "porcentaje": round(ocupados * 100 / total, 1),
        }
