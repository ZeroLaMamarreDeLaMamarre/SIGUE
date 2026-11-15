
import network
import time
import ntptime
import machine
#Clase encargada de administrar la red wifi
class WiFi:
    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)  #Hacemos que wlan trabaje en modo estacion
        if not self.wlan.active(): #Comprobamos si la red no esta activa
            self.wlan.active(True) #Si no lo esta la actuvamos

    def escanear_redes(self):
        print("Escaneando redes . . . ")
        redes_codificadas = self.wlan.scan() #Nos da todas las redes que la palca logro observar
        redes_descodificadas = [] #una mausqueramienta misteriosa que nos servira para mas tarde

        for red in redes_codificadas: #Por cada red escaneada
            redes_descodificadas.append({ #Agregamsos a la mauseherramientamisteriosa
                "ssid" : red[0].decode('utf-8'), #El dato decodificado de el nombre de la reed
                'rssid' : red[3] #La potencia de la señal
            })

        return redes_descodificadas #Devolvemos todas las redes decodificadas

    def conectar_red(self, ssid, password, timeout = 10): # Metodo para activar el wifi
        self.wlan.active(False) #Desactivamos la red
        time.sleep(0.5) #Esperamos un poco para no generar errores
        self.wlan.active(True) #volvemos a activar la red
        #En caso de un reinicio, o que queramos cambiar la red ocupamos este paso
        #Para que no tengamos errores

        if self.wlan.isconnected():#En caso de que este conectada a una red
            self.wlan.disconnect()# La desconectamos



        print(f"Intentando conectar a {ssid}. . . ")
        self.wlan.connect(ssid, password) #Intentamos establecer conecion

        errores = { #Los posibles errores mas comunes que puede haber
            network.STAT_WRONG_PASSWORD : "Contraseña Incorrecta",
            network.STAT_NO_AP_FOUND : "No se a podido localizar el punto de acceso indicado",
            "TIMEOUT" : "Tiempo de espera agotado"
        }
        inicio = time.time() #Necesitamos esta variable para saber cuando iniciamos el intento d conexion

        while not self.wlan.isconnected(): #Mientras que no este coenctado
            estado = self.wlan.status() #Guardamos el estado del bucle actual

            if estado in errores: #En caso de que el estado nos de un error
                return errores[estado]#Comprobamos si es uno de los errores mas comunes y devolvemos el error en caso de que si

            if (time.time() - inicio) > timeout: #Si pasamos el timeout configurado
                return errores["TIMEOUT"] #Entonces devolvermos el error de TIMEOUT



            time.sleep(0.5)
        return f"Conexión exitosa con {ssid}" #En caso de una coneion exitosasolamente debolbemos esto

    def desconectar_red(self): #funcion para desconectar la red
        if self.wlan.isconnected(): #En caso de que este conectado
            self.wlan.disconnect() #Lo desconectamos
            return "Desconectado Exitosamente" #Damos el semanje que de hhemos desconectado

        return "No hay ninguna red conectada"#Si no hacemos saber que no se hizo nada

    def status(self): #Devolvemos la informacion de la red
        conexion = self.wlan.isconnected() #Comprobamos si estamos conectados

        if not conexion:# En caso de no estarlo
            return {
                "Conectado" : False,
                "ssid" : None,
                "rssid" : None
            }
        #Devolvemos el diccionario con nuestra informacion
        #En caso de si tenerlo

        try:#Primero intentamos ver si podemos acceder a la informacion de el nombre de la red
            #Esto lo hacemos en un try exept por si justo en ese momento se va la red
            ssid = self.wlan.config("essid") #En caso de que si se pudo guardamos la informacion
            if isinstance(ssid, bytes): #Comprobamos que no sea basura, isinstance comprueba si es un objeto
                #Y la clase de objeto que queremos, en este caso como la mayoria de cosa en esp, nos lo devulvel en bytes
                ssid = ssid.decode('utf-8')#Lo decodificamos a algo legible
        except:#En caso de no haber podido encontrar el nombre
            ssid = "Desconocido"#Solamente ponemos desconocido

        try:#mismo caso de arriba, pero con la señal de internet
            rssid =self.wlan.status("rssid")
        except:
            rssid = 0


        return {
            "conexion" : True,
            "ssid" : ssid,
            "rssid" : rssid
        }
    def sincronizar_hora(self):
        ntptime.host = "pool.ntp.org"
        intento = 0

        while intento < 5:
            try:
                ntptime.settime()
                t = time.localtime(time.time() - 21600)
                machine.RTC().datetime((t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))
                print(f"Hora NTP sincronizada: {t[0]}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d} UTC")
                return


            except Exception:
                intento += 1
                print(f"Intento fallido intento: {intento}")
                time.sleep(2)

        raise RuntimeError("Fallo en validación TLS: No se obtuvo tiempo de referencia para verificar certificados.")














