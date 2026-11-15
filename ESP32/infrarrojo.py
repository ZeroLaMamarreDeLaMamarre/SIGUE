from machine import Pin

class Infrarrojo:
    def __init__(self, entrada):
        self.sensor = Pin(entrada, Pin.IN)

    def estado(self):
        if self.sensor.value() == 0:
            return True
        else:
            return False

