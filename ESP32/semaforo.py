from machine import Pin

class Semaforo: #Clase encargada de controlar el semaforo de entrada
    def __init__(self,
                 medio=50, #Indica cuanto porcentaje de espacion debe de estar ocupado para considerarse medio lleno
                 lleno = 80):#Lo mismo pero ya casi lleno

        self.leds ={ #Diccionario con nustros leds
            "ROJO" : Pin(16, Pin.OUT),
            "AMARILLO" : Pin(17, Pin.OUT),
            "VERDE" : Pin(18, Pin.OUT)
        }

        self.estados = {
            "MEDIO" : medio,
            "LLENO" : lleno
        }

    def apagar_todo(self): #Apaga todo los leds usando el diccionario
        for led in self.leds.values():
            led.off()

    def prender_todo(self): #Enciende todo los leds usando el diccionario
        for led in self.leds.values():
            led.on()

    def cambiar_estado(self, promedio): #Se encarga de prender la luz dependiendo de cuanto espacio sea utilizado
        self.apagar_todo()


        if promedio >= self.estados["LLENO"]: #Si el espacio supera el "LLENO" o esigual se pone rojo
            self.leds["ROJO"].on()
        elif promedio >= self.estados["MEDIO"]: #Si supera el MEDIO o es igual seprende amarillo
            self.leds["AMARILLO"].on()
        else: #Y si no es ni una ni otra se pende el verde
            self.leds["VERDE"].on()