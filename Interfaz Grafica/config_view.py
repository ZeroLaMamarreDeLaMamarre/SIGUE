"""
Módulo de Configuración para ESP32 y Panel IoT.

Contiene dos componentes reutilizables:
  1. ConfigFrame (Configuración del ESP32 por BLE) con 4 pestañas:
       - 1. Wi-Fi
       - 2. Broker MQTT
       - 3. Dispositivo
       - 4. Enviar Datos (genera y retorna un diccionario por cada pestaña)
  2. AppConfigFrame (Configuración del Panel / App):
       - Parámetros MQTT propios de la aplicación + botón "Guardar y Conectar"
"""

import json
import os
import queue
import tkinter as tk
from tkinter import filedialog, messagebox

import config_store
from ble_cliente import EnviadorBLE, NOMBRE_BLE

# Colores coincidentes con app.py
BG = "#01040B"
CARD = "#030A19"
BORDER = "#192A4C"
INPUT_BG = "#071228"
TEXT = "#84ACE7"
MUTED = "#A9B7CE"
GREEN = "#16A24A"
AMBER = "#FBBF24"
RED = "#C11414"
FONT = "Helvetica"

# Certificado CA por defecto: ca.crt junto a este archivo
RUTA_CA_DEFECTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ca.crt")

MAX_CARACTERES = 30  # El firmware recorta cada parámetro a 30 caracteres


def validar_para_esp32(d):
    """Revisa los límites reales del firmware. Devuelve una lista de errores."""
    errores = []

    # El firmware ignora los textos vacíos: esos campos nunca quedarían "listos"
    for seccion, clave, nombre in (
        ("wifi", "password", "Contraseña Wi-Fi"),
        ("mqtt", "mqtt_user", "Usuario MQTT"),
        ("mqtt", "mqtt_pass", "Contraseña MQTT"),
    ):
        if not d[seccion].get(clave):
            errores.append(f"{nombre}: el firmware no acepta valores vacíos")

    etiquetas = {
        "ssid": "SSID", "password": "Contraseña Wi-Fi", "mqtt_id": "Client ID",
        "mqtt_ip": "IP del broker", "mqtt_port": "Puerto", "mqtt_user": "Usuario MQTT",
        "mqtt_pass": "Contraseña MQTT", "nuevo_nombre": "Nombre del dispositivo",
    }
    for campos in d.values():
        for clave, valor in campos.items():
            largo = len(str(valor or "").encode("utf-8"))
            if largo > MAX_CARACTERES:
                errores.append(
                    f"{etiquetas.get(clave, clave)}: máximo {MAX_CARACTERES} caracteres (tiene {largo})"
                )

    try:
        if not 1 <= int(d["mqtt"]["mqtt_port"]) <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        errores.append("Puerto MQTT: debe ser un número entre 1 y 65535")

    return errores


class _BaseFormFrame(tk.Frame):
    """Utilidades visuales compartidas para formularios."""

    # ---- cola para actualizar la UI de forma segura desde otros hilos ----
    def _init_cola(self):
        self._cola_ui = queue.Queue()
        self._drenar_cola()

    def _ui(self, fn, *args):
        self._cola_ui.put((fn, args))

    def _drenar_cola(self):
        try:
            while True:
                fn, args = self._cola_ui.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(100, self._drenar_cola)

    def _label(self, parent, text="", size=11, bold=False, color=TEXT):
        return tk.Label(
            parent,
            text=text,
            fg=color,
            bg=parent["bg"],
            font=(FONT, size, "bold" if bold else "normal"),
        )

    def _create_field(
        self, parent, label_text, is_password=False, default_val=""
    ):
        """Crea un Label con su Entry estilizado."""
        box = tk.Frame(parent, bg=CARD)
        box.pack(fill="x", pady=6)

        lbl = self._label(box, label_text, size=10, bold=True, color=MUTED)
        lbl.pack(anchor="w", pady=(0, 4))

        input_row = tk.Frame(box, bg=CARD)
        input_row.pack(fill="x")

        var = tk.StringVar(value=default_val)
        entry = tk.Entry(
            input_row,
            textvariable=var,
            font=(FONT, 11),
            bg=INPUT_BG,
            fg="#FFFFFF",
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=TEXT,
        )
        entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 4))

        if is_password:
            entry.config(show="•")
            btn_eye = tk.Button(
                input_row,
                text="👁",
                font=(FONT, 10),
                bg=INPUT_BG,
                fg=MUTED,
                activebackground=BORDER,
                activeforeground="#FFFFFF",
                relief="flat",
                highlightthickness=1,
                highlightbackground=BORDER,
                cursor="hand2",
                width=3,
                command=lambda: self._toggle_password_visibility(entry, btn_eye),
            )
            btn_eye.pack(side="right", ipady=4)

        return var, entry

    def _toggle_password_visibility(self, entry, btn):
        if entry.cget("show") == "":
            entry.config(show="•")
            btn.config(fg=MUTED)
        else:
            entry.config(show="")
            btn.config(fg="#FFFFFF")


class ConfigFrame(_BaseFormFrame):
    """
    Frame de configuración del ESP32 con 4 pestañas:
    1. Wi-Fi | 2. Broker MQTT | 3. Dispositivo | 4. Enviar Datos
    """

    def __init__(
        self,
        parent,
        on_save_callback=None,
        on_send_callback=None,      # se llama tras un envío BLE exitoso
        on_send_mqtt_callback=None,  # fn(diccionarios, destino, on_fin)
        on_restablecer_callback=None,  # fn(destino, on_fin)
        **kwargs,
    ):
        super().__init__(parent, bg=BG, **kwargs)
        self.on_save_callback = on_save_callback
        self.on_send_callback = on_send_callback
        self.on_send_mqtt_callback = on_send_mqtt_callback
        self.on_restablecer_callback = on_restablecer_callback
        self.ble = EnviadorBLE()
        self._init_cola()

        # Almacenamiento de variables (coincide con ESP32 / BLE)
        self.ssid = None
        self.password = None

        self.mqtt_id = None
        self.mqtt_ip = None
        self.mqtt_port = None
        self.mqtt_user = None
        self.mqtt_pass = None

        self.nuevo_nombre = None

        # Banderas de estado
        self.activo = True
        self.wifi_ssid_listo = False
        self.wifi_pass_listo = False
        self.mqtt_id_listo = False
        self.mqtt_ip_listo = False
        self.mqtt_port_listo = False
        self.mqtt_user_listo = False
        self.mqtt_pass_listo = False
        self.nombre_listo = False

        self.tab_buttons = {}
        self.tab_frames = {}
        self.current_tab = "wifi"
        self._cargando = False

        self._build()
        self._cargar_guardado()

    def _build(self):
        # Barra superior de navegación entre las 4 pestañas
        nav_bar = tk.Frame(self, bg=BG)
        nav_bar.pack(fill="x", pady=(0, 16))

        tabs_data = [
            ("wifi", "📶 1. Wi-Fi"),
            ("mqtt", "📡 2. Broker MQTT"),
            ("device", "⚙️ 3. Dispositivo"),
            ("send", "🚀 4. Enviar Datos"),
        ]

        for tab_id, tab_title in tabs_data:
            btn = tk.Button(
                nav_bar,
                text=tab_title,
                font=(FONT, 11, "bold"),
                relief="flat",
                padx=18,
                pady=8,
                cursor="hand2",
                highlightthickness=1,
                command=lambda t=tab_id: self.select_tab(t),
            )
            btn.pack(side="left", padx=(0, 10))
            self.tab_buttons[tab_id] = btn

        # Contenedor para las páginas
        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

        self._build_wifi_tab()
        self._build_mqtt_tab()
        self._build_device_tab()
        self._build_send_tab()

        self.select_tab("wifi")

    # ---------- Persistencia (config_panel.json) ----------
    def _cargar_guardado(self):
        g = config_store.cargar("esp32")
        if not g:
            return

        campos = {
            "ssid": self.var_ssid, "password": self.var_password,
            "mqtt_id": self.var_mqtt_id, "mqtt_ip": self.var_mqtt_ip,
            "mqtt_port": self.var_mqtt_port, "mqtt_user": self.var_mqtt_user,
            "mqtt_pass": self.var_mqtt_pass, "nuevo_nombre": self.var_device_name,
            "destino": self.var_destino,
        }
        for clave, var in campos.items():
            if g.get(clave) not in (None, ""):
                var.set(str(g[clave]))

        # Deja cada sección "guardada" en memoria si estaba completa, sin reescribir el archivo
        self._cargando = True
        try:
            if g.get("ssid"):
                self._guardar_wifi()
            if g.get("mqtt_id") and g.get("mqtt_ip") and g.get("mqtt_port"):
                self._guardar_mqtt()
            if g.get("nuevo_nombre"):
                self._guardar_dispositivo()
        finally:
            self._cargando = False

    def _persistir(self):
        if self._cargando:
            return
        try:
            config_store.guardar("esp32", {
                **self.get_config(),
                "destino": self.var_destino.get().strip(),
            })
        except OSError as e:
            print("[CONFIG] No se pudo guardar config_panel.json:", e)

    def select_tab(self, tab_id):
        self.current_tab = tab_id
        for tid, frame in self.tab_frames.items():
            if tid == tab_id:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

        for tid, btn in self.tab_buttons.items():
            if tid == tab_id:
                btn.config(
                    bg="#1E3A6B",
                    fg="#FFFFFF",
                    activebackground="#254B8C",
                    activeforeground="#FFFFFF",
                    highlightbackground=TEXT,
                )
            else:
                btn.config(
                    bg=CARD,
                    fg=TEXT,
                    activebackground="#101F3B",
                    activeforeground="#FFFFFF",
                    highlightbackground=BORDER,
                )

        # Actualizar vista previa al entrar a la pestaña 4
        if tab_id == "send":
            self._actualizar_resumen_envio()

    # ---------- 1. PESTAÑA WI-FI ----------
    def _build_wifi_tab(self):
        f = tk.Frame(self.container, bg=BG)
        self.tab_frames["wifi"] = f

        card = tk.Frame(f, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=4, pady=4)

        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=28, pady=(24, 12))
        self._label(head, "📶 Configuración de Wi-Fi", 17, True).pack(anchor="w")
        self._label(
            head,
            "Credenciales de la red inalámbrica para el ESP32.",
            11,
            False,
            MUTED,
        ).pack(anchor="w", pady=(3, 0))

        body = tk.Frame(card, bg=CARD)
        body.pack(fill="x", padx=28, pady=10)

        self.var_ssid, self.entry_ssid = self._create_field(
            body, "Nombre de Red (SSID):"
        )
        self.var_password, self.entry_password = self._create_field(
            body, "Contraseña:", is_password=True
        )

        actions = tk.Frame(card, bg=CARD)
        actions.pack(fill="x", padx=28, pady=(18, 20))

        btn_save = tk.Button(
            actions,
            text="Guardar Wi-Fi",
            font=(FONT, 11, "bold"),
            bg=GREEN,
            fg="#FFFFFF",
            activebackground="#13803B",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._guardar_wifi,
        )
        btn_save.pack(side="left")

        self.lbl_status_wifi = self._label(
            actions, "● Sin guardar", 11, False, AMBER
        )
        self.lbl_status_wifi.pack(side="left", padx=18)

        resumen = tk.Frame(card, bg="#071228", highlightthickness=1, highlightbackground=BORDER)
        resumen.pack(fill="x", padx=28, pady=(10, 24))
        self._label(resumen, "Variables en memoria (ESP32 / BLE):", 10, True, MUTED).pack(
            anchor="w", padx=16, pady=(10, 2)
        )
        self.lbl_resumen_wifi = self._label(
            resumen, "self.ssid = None   |   self.password = None", 11, False, "#C7D2E4"
        )
        self.lbl_resumen_wifi.pack(anchor="w", padx=16, pady=(0, 10))

    def _guardar_wifi(self):
        ssid = self.var_ssid.get().strip()
        pwd = self.var_password.get().strip()

        if not ssid:
            self.lbl_status_wifi.config(text="❌ El SSID es requerido", fg=RED)
            return False

        self.ssid = ssid
        self.password = pwd
        self.wifi_ssid_listo = True
        self.wifi_pass_listo = bool(pwd)

        hidden = "•" * len(pwd) if pwd else "(sin clave)"
        self.lbl_status_wifi.config(text="✅ Wi-Fi guardado", fg=GREEN)
        self.lbl_resumen_wifi.config(
            text=f"self.ssid = '{self.ssid}'   |   self.password = '{hidden}'"
        )
        self._persistir()
        if self.on_save_callback:
            self.on_save_callback("wifi", self.get_wifi_dict())
        return True

    # ---------- 2. PESTAÑA MQTT ----------
    def _build_mqtt_tab(self):
        f = tk.Frame(self.container, bg=BG)
        self.tab_frames["mqtt"] = f

        card = tk.Frame(f, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=4, pady=4)

        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=28, pady=(24, 12))
        self._label(head, "📡 Configuración del Broker MQTT (ESP32)", 17, True).pack(anchor="w")
        self._label(
            head,
            "Parámetros de conexión al servidor de telemetría que usará el ESP32.",
            11,
            False,
            MUTED,
        ).pack(anchor="w", pady=(3, 0))

        body = tk.Frame(card, bg=CARD)
        body.pack(fill="x", padx=28, pady=10)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        c_left = tk.Frame(body, bg=CARD)
        c_left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        c_right = tk.Frame(body, bg=CARD)
        c_right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

        self.var_mqtt_id, self.entry_mqtt_id = self._create_field(
            c_left, "Client ID:"
        )
        self.var_mqtt_ip, self.entry_mqtt_ip = self._create_field(
            c_left, "IP / Host del Broker:"
        )
        self.var_mqtt_port, self.entry_mqtt_port = self._create_field(
            c_left, "Puerto (ej. 8883 o 1883):", default_val="8883"
        )

        self.var_mqtt_user, self.entry_mqtt_user = self._create_field(
            c_right, "Usuario MQTT:"
        )
        self.var_mqtt_pass, self.entry_mqtt_pass = self._create_field(
            c_right, "Contraseña MQTT:", is_password=True
        )

        actions = tk.Frame(card, bg=CARD)
        actions.pack(fill="x", padx=28, pady=(18, 20))

        btn_save = tk.Button(
            actions,
            text="Guardar MQTT",
            font=(FONT, 11, "bold"),
            bg=GREEN,
            fg="#FFFFFF",
            activebackground="#13803B",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._guardar_mqtt,
        )
        btn_save.pack(side="left")

        self.lbl_status_mqtt = self._label(
            actions, "● Sin guardar", 11, False, AMBER
        )
        self.lbl_status_mqtt.pack(side="left", padx=18)

        resumen = tk.Frame(card, bg="#071228", highlightthickness=1, highlightbackground=BORDER)
        resumen.pack(fill="x", padx=28, pady=(10, 24))
        self._label(resumen, "Variables en memoria (ESP32 / BLE):", 10, True, MUTED).pack(
            anchor="w", padx=16, pady=(10, 2)
        )
        self.lbl_resumen_mqtt = self._label(
            resumen,
            "self.mqtt_id = None | self.mqtt_ip = None | self.mqtt_port = None | self.mqtt_user = None | self.mqtt_pass = None",
            10,
            False,
            "#C7D2E4",
        )
        self.lbl_resumen_mqtt.pack(anchor="w", padx=16, pady=(0, 10))

    def _guardar_mqtt(self):
        m_id = self.var_mqtt_id.get().strip()
        m_ip = self.var_mqtt_ip.get().strip()
        m_port = self.var_mqtt_port.get().strip()
        m_user = self.var_mqtt_user.get().strip()
        m_pass = self.var_mqtt_pass.get().strip()

        if not m_id or not m_ip or not m_port:
            self.lbl_status_mqtt.config(
                text="❌ Client ID, IP y Puerto son obligatorios", fg=RED
            )
            return False

        self.mqtt_id = m_id
        self.mqtt_ip = m_ip
        self.mqtt_port = m_port
        self.mqtt_user = m_user
        self.mqtt_pass = m_pass

        self.mqtt_id_listo = True
        self.mqtt_ip_listo = True
        self.mqtt_port_listo = True
        self.mqtt_user_listo = bool(m_user)
        self.mqtt_pass_listo = bool(m_pass)

        self.lbl_status_mqtt.config(text="✅ MQTT guardado", fg=GREEN)
        self.lbl_resumen_mqtt.config(
            text=f"ID: '{self.mqtt_id}' | IP: '{self.mqtt_ip}' | Puerto: {self.mqtt_port} | Usuario: '{self.mqtt_user}'"
        )
        self._persistir()
        if self.on_save_callback:
            self.on_save_callback("mqtt", self.get_mqtt_dict())
        return True

    # ---------- 3. PESTAÑA DISPOSITIVO ----------
    def _build_device_tab(self):
        f = tk.Frame(self.container, bg=BG)
        self.tab_frames["device"] = f

        card = tk.Frame(f, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=4, pady=4)

        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=28, pady=(24, 12))
        self._label(head, "⚙️ Configuración del Dispositivo", 17, True).pack(anchor="w")
        self._label(
            head,
            "Nombre que se usará para identificar el ESP32 por BLE y guardar en memoria NVS.",
            11,
            False,
            MUTED,
        ).pack(anchor="w", pady=(3, 0))

        body = tk.Frame(card, bg=CARD)
        body.pack(fill="x", padx=28, pady=10)

        self.var_device_name, self.entry_device_name = self._create_field(
            body, "Nombre del Dispositivo:"
        )

        lbl_hint = self._label(
            body, "ℹ️ Recomendación: Máximo 15 caracteres para memoria NVS", 10, False, MUTED
        )
        lbl_hint.pack(anchor="w", pady=(2, 0))

        actions = tk.Frame(card, bg=CARD)
        actions.pack(fill="x", padx=28, pady=(18, 20))

        btn_save = tk.Button(
            actions,
            text="Guardar Nombre",
            font=(FONT, 11, "bold"),
            bg=GREEN,
            fg="#FFFFFF",
            activebackground="#13803B",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._guardar_dispositivo,
        )
        btn_save.pack(side="left")

        self.lbl_status_device = self._label(
            actions, "● Sin guardar", 11, False, AMBER
        )
        self.lbl_status_device.pack(side="left", padx=18)

        resumen = tk.Frame(card, bg="#071228", highlightthickness=1, highlightbackground=BORDER)
        resumen.pack(fill="x", padx=28, pady=(10, 24))
        self._label(resumen, "Variables en memoria (ESP32 / BLE):", 10, True, MUTED).pack(
            anchor="w", padx=16, pady=(10, 2)
        )
        self.lbl_resumen_device = self._label(
            resumen, "self.nuevo_nombre = None", 11, False, "#C7D2E4"
        )
        self.lbl_resumen_device.pack(anchor="w", padx=16, pady=(0, 10))

    def _guardar_dispositivo(self):
        nombre = self.var_device_name.get().strip()
        if not nombre:
            self.lbl_status_device.config(
                text="❌ El nombre no puede estar vacío", fg=RED
            )
            return False

        if len(nombre) > 15:
            self.lbl_status_device.config(
                text="⚠️ Advertencia: Excede los 15 caracteres para NVS", fg=AMBER
            )
        else:
            self.lbl_status_device.config(text="✅ Nombre guardado", fg=GREEN)

        self.nuevo_nombre = nombre
        self.nombre_listo = True
        self.lbl_resumen_device.config(text=f"self.nuevo_nombre = '{self.nuevo_nombre}'")
        self._persistir()
        if self.on_save_callback:
            self.on_save_callback("device", self.get_device_dict())
        return True

    # ---------- 4. PESTAÑA ENVIAR DATOS ----------
    def _build_send_tab(self):
        f = tk.Frame(self.container, bg=BG)
        self.tab_frames["send"] = f

        card = tk.Frame(f, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=4, pady=4)

        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=28, pady=(24, 12))
        self._label(head, "🚀 Enviar Datos al ESP32 (Bluetooth BLE)", 17, True).pack(anchor="w")
        self._label(
            head,
            "Verifica la configuración de las 3 pestañas y genera los diccionarios para enviar al dispositivo.",
            11,
            False,
            MUTED,
        ).pack(anchor="w", pady=(3, 0))

        # Vista previa de los diccionarios generados por pestaña
        preview_box = tk.Frame(card, bg="#071228", highlightthickness=1, highlightbackground=BORDER)
        preview_box.pack(fill="both", expand=True, padx=28, pady=10)

        self._label(
            preview_box,
            "Diccionarios generados por pestaña:",
            10,
            True,
            MUTED,
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self.lbl_dict_preview = tk.Label(
            preview_box,
            text="",
            fg="#C7D2E4",
            bg="#071228",
            font=("Courier", 10),
            justify="left",
            anchor="nw",
        )
        self.lbl_dict_preview.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        # Dispositivo destino para el envío por MQTT
        destino_box = tk.Frame(card, bg=CARD)
        destino_box.pack(fill="x", padx=28)
        self.var_destino, self.entry_destino = self._create_field(
            destino_box, "Dispositivo destino para MQTT (nombre ACTUAL del ESP32):"
        )
        self._label(
            destino_box,
            "Si lo dejas vacío se usa el nombre de la pestaña 3. Solo aplica al envío por MQTT.",
            10, False, MUTED,
        ).pack(anchor="w")

        # Botones de envío y estado
        actions = tk.Frame(card, bg=CARD)
        actions.pack(fill="x", padx=28, pady=(14, 4))

        self.btn_send_ble = tk.Button(
            actions,
            text="🚀 Enviar por Bluetooth",
            font=(FONT, 11, "bold"),
            bg="#1E3A6B",
            fg="#FFFFFF",
            activebackground="#254B8C",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=24,
            pady=10,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=TEXT,
            command=self.enviar_datos,
        )
        self.btn_send_ble.pack(side="left", padx=(0, 10))

        self.btn_send_mqtt = tk.Button(
            actions,
            text="📡 Enviar por MQTT (comandos)",
            font=(FONT, 11, "bold"),
            bg="#1E3A6B",
            fg="#FFFFFF",
            activebackground="#254B8C",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=24,
            pady=10,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=TEXT,
            command=self.enviar_por_mqtt,
        )
        self.btn_send_mqtt.pack(side="left")

        self.lbl_status_send = self._label(
            card, "● Listo para validar y enviar", 11, False, MUTED
        )
        self.lbl_status_send.pack(anchor="w", padx=28, pady=(8, 10))

        # Zona de peligro: restablecer el ESP32 de fábrica
        zona = tk.Frame(card, bg=CARD)
        zona.pack(fill="x", padx=28, pady=(4, 24))
        self.btn_reset = tk.Button(
            zona,
            text="♻️ Restablecer dispositivo",
            font=(FONT, 11, "bold"),
            bg=RED,
            fg="#FFFFFF",
            activebackground="#9A1010",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=24,
            pady=10,
            cursor="hand2",
            command=self.restablecer_dispositivo,
        )
        self.btn_reset.pack(side="left")
        self._label(
            zona,
            "Borra Wi-Fi, MQTT y nombre del ESP32 y lo reinicia en modo configuración (Bluetooth).",
            10, False, MUTED,
        ).pack(side="left", padx=14)

    def _actualizar_resumen_envio(self, datos_por_pestana=None):
        datos = datos_por_pestana or self.get_config_por_pestana()
        texto = (
            f"1. dict_wifi        = {json.dumps(datos['wifi'], ensure_ascii=False)}\n"
            f"2. dict_mqtt        = {json.dumps(datos['mqtt'], ensure_ascii=False)}\n"
            f"3. dict_dispositivo = {json.dumps(datos['dispositivo'], ensure_ascii=False)}"
        )
        self.lbl_dict_preview.config(text=texto)

    def _estado_envio(self, texto, color):
        self.lbl_status_send.config(text=texto, fg=color)

    def _set_botones(self, habilitados):
        estado = "normal" if habilitados else "disabled"
        self.btn_send_ble.config(state=estado)
        self.btn_send_mqtt.config(state=estado)
        self.btn_reset.config(state=estado)

    def _validar_todo(self):
        """Guarda/valida las 3 pestañas y revisa los límites del firmware.
        Devuelve los diccionarios o None si hay errores (ya mostrados)."""
        ok_wifi = self._guardar_wifi()
        ok_mqtt = self._guardar_mqtt()
        ok_device = self._guardar_dispositivo()

        diccionarios = self.get_config_por_pestana()
        self._actualizar_resumen_envio(diccionarios)

        faltantes = []
        if not ok_wifi:
            faltantes.append("1. Wi-Fi")
        if not ok_mqtt:
            faltantes.append("2. Broker MQTT")
        if not ok_device:
            faltantes.append("3. Dispositivo")

        if faltantes:
            self._estado_envio(
                f"❌ Faltan datos obligatorios en: {', '.join(faltantes)}", RED
            )
            return None

        errores = validar_para_esp32(diccionarios)
        if errores:
            self._estado_envio("❌ " + errores[0], RED)
            return None

        return diccionarios

    # ---- Envío por Bluetooth ----
    def enviar_datos(self):
        """Valida y envía cada parámetro a su característica BLE del ESP32."""
        diccionarios = self._validar_todo()
        if diccionarios is None or self.ble.ocupado:
            return None

        print("[ESP32 CONFIG] Enviando configuración por BLE...")
        self._set_botones(False)
        self._estado_envio(f"⏳ Buscando '{NOMBRE_BLE}' por Bluetooth...", AMBER)
        self.ble.enviar(
            diccionarios,
            on_progreso=lambda t: self._ui(self._estado_envio, "⏳ " + t, AMBER),
            on_fin=lambda ok, m: self._ui(self._fin_ble, ok, m, diccionarios),
        )
        return diccionarios

    def _fin_ble(self, ok, mensaje, diccionarios):
        self._set_botones(True)
        if ok:
            self._estado_envio("✅ " + mensaje, GREEN)
            if self.on_send_callback:
                self.on_send_callback(diccionarios)
        else:
            self._estado_envio("❌ " + mensaje, RED)

    # ---- Envío por MQTT (trama de comandos) ----
    def enviar_por_mqtt(self):
        diccionarios = self._validar_todo()
        if diccionarios is None:
            return None

        if not self.on_send_mqtt_callback:
            self._estado_envio("❌ El envío por MQTT no está disponible", RED)
            return None

        destino = (
            self.var_destino.get().strip() or diccionarios["dispositivo"]["nuevo_nombre"]
        )
        self._persistir()
        self._set_botones(False)
        self._estado_envio("⏳ Publicando comando en el broker...", AMBER)
        self.on_send_mqtt_callback(
            diccionarios,
            destino,
            lambda ok, m: self._ui(self._fin_mqtt, ok, m),
        )
        return diccionarios

    # ---- Restablecer dispositivo (comando por MQTT) ----
    def restablecer_dispositivo(self):
        destino = self.var_destino.get().strip() or self.var_device_name.get().strip()
        if not destino:
            self._estado_envio(
                "❌ Escribe el nombre actual del ESP32 en 'Dispositivo destino'", RED
            )
            return None
        if not self.on_restablecer_callback:
            self._estado_envio("❌ El restablecimiento no está disponible", RED)
            return None

        confirmar = messagebox.askyesno(
            "Restablecer dispositivo",
            f"Se borrarán el Wi-Fi, el MQTT y el nombre de '{destino}', y el ESP32 se "
            "reiniciará en modo configuración Bluetooth.\n\n¿Continuar?",
            icon="warning",
        )
        if not confirmar:
            return None

        self._persistir()
        self._set_botones(False)
        self._estado_envio("⏳ Enviando comando de restablecimiento...", AMBER)
        self.on_restablecer_callback(
            destino, lambda ok, m: self._ui(self._fin_mqtt, ok, m)
        )
        return destino

    def _fin_mqtt(self, ok, mensaje):
        self._set_botones(True)
        self._estado_envio(("✅ " if ok else "❌ ") + mensaje, GREEN if ok else RED)

    # ---------- GETTERS DE DICCIONARIOS POR PESTAÑA ----------
    def get_wifi_dict(self):
        return {
            "ssid": self.ssid,
            "password": self.password,
        }

    def get_mqtt_dict(self):
        return {
            "mqtt_id": self.mqtt_id,
            "mqtt_ip": self.mqtt_ip,
            "mqtt_port": self.mqtt_port,
            "mqtt_user": self.mqtt_user,
            "mqtt_pass": self.mqtt_pass,
        }

    def get_device_dict(self):
        return {
            "nuevo_nombre": self.nuevo_nombre,
        }

    def get_config_por_pestana(self):
        """Retorna un diccionario separado por cada pestaña."""
        return {
            "wifi": self.get_wifi_dict(),
            "mqtt": self.get_mqtt_dict(),
            "dispositivo": self.get_device_dict(),
        }

    def get_config(self):
        """Retorna el diccionario plano consolidado (compatibilidad)."""
        return {
            **self.get_wifi_dict(),
            **self.get_mqtt_dict(),
            **self.get_device_dict(),
        }


class AppConfigFrame(_BaseFormFrame):
    """
    Vista para la 3ra opción de la barra superior: Configuración del Panel / App.
    Contiene las mismas opciones de MQTT y el botón 'Guardar y Conectar'.
    """

    def __init__(self, parent, on_connect_callback=None, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self.on_connect_callback = on_connect_callback
        self._init_cola()

        self.mqtt_id = None
        self.mqtt_ip = None
        self.mqtt_port = None
        self.mqtt_user = None
        self.mqtt_pass = None
        self.dispositivo = None
        self.ca_cert = None

        self._build()
        self._cargar_guardado()

    def _build(self):
        card = tk.Frame(self, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=4, pady=4)

        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=28, pady=(24, 12))
        self._label(head, "🖥️ Configuración MQTT del Panel / App", 17, True).pack(anchor="w")
        self._label(
            head,
            "Credenciales MQTT de esta interfaz gráfica para conectarse al broker y recibir telemetría.",
            11,
            False,
            MUTED,
        ).pack(anchor="w", pady=(3, 0))

        # Grid de campos idéntico al de MQTT
        body = tk.Frame(card, bg=CARD)
        body.pack(fill="x", padx=28, pady=10)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        c_left = tk.Frame(body, bg=CARD)
        c_left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        c_right = tk.Frame(body, bg=CARD)
        c_right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

        self.var_mqtt_id, self.entry_mqtt_id = self._create_field(
            c_left, "Client ID:"
        )
        self.var_mqtt_ip, self.entry_mqtt_ip = self._create_field(
            c_left, "IP / Host del Broker:"
        )
        self.var_mqtt_port, self.entry_mqtt_port = self._create_field(
            c_left, "Puerto (ej. 8883 o 1883):", default_val="8883"
        )

        self.var_ca, self.entry_ca = self._create_field(
            c_left, "Certificado CA del broker (.crt / .pem):", default_val=RUTA_CA_DEFECTO
        )
        tk.Button(
            self.entry_ca.master,
            text="📂",
            font=(FONT, 10),
            bg=INPUT_BG,
            fg=MUTED,
            activebackground=BORDER,
            activeforeground="#FFFFFF",
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            cursor="hand2",
            width=3,
            command=self._elegir_certificado,
        ).pack(side="right", ipady=4)

        self.var_mqtt_user, self.entry_mqtt_user = self._create_field(
            c_right, "Usuario MQTT:"
        )
        self.var_mqtt_pass, self.entry_mqtt_pass = self._create_field(
            c_right, "Contraseña MQTT:", is_password=True
        )
        self.var_dispositivo, self.entry_dispositivo = self._create_field(
            c_right, "Dispositivo a monitorear (nombre del ESP32):"
        )

        # Botón Guardar y Conectar
        actions = tk.Frame(card, bg=CARD)
        actions.pack(fill="x", padx=28, pady=(18, 20))

        btn_connect = tk.Button(
            actions,
            text="🔌 Guardar y Conectar",
            font=(FONT, 11, "bold"),
            bg=GREEN,
            fg="#FFFFFF",
            activebackground="#13803B",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=22,
            pady=9,
            cursor="hand2",
            command=self.guardar_y_conectar,
        )
        btn_connect.pack(side="left")

        self.lbl_status_app_mqtt = self._label(
            actions, "● Desconectado", 11, False, AMBER
        )
        self.lbl_status_app_mqtt.pack(side="left", padx=18)

        # Resumen en memoria
        resumen = tk.Frame(card, bg="#071228", highlightthickness=1, highlightbackground=BORDER)
        resumen.pack(fill="x", padx=28, pady=(10, 24))
        self._label(resumen, "Configuración MQTT de la App en memoria:", 10, True, MUTED).pack(
            anchor="w", padx=16, pady=(10, 2)
        )
        self.lbl_resumen_app_mqtt = self._label(
            resumen,
            "mqtt_id = None | mqtt_ip = None | mqtt_port = None | mqtt_user = None | mqtt_pass = None",
            10,
            False,
            "#C7D2E4",
        )
        self.lbl_resumen_app_mqtt.pack(anchor="w", padx=16, pady=(0, 10))

    def guardar_y_conectar(self):
        m_id = self.var_mqtt_id.get().strip()
        m_ip = self.var_mqtt_ip.get().strip()
        m_port = self.var_mqtt_port.get().strip()
        m_user = self.var_mqtt_user.get().strip()
        m_pass = self.var_mqtt_pass.get().strip()
        m_disp = self.var_dispositivo.get().strip()
        m_ca = self.var_ca.get().strip()

        if not m_id or not m_ip or not m_port or not m_disp:
            self.lbl_status_app_mqtt.config(
                text="❌ Client ID, IP, Puerto y Dispositivo son obligatorios", fg=RED
            )
            return None

        if m_port == "8883" and not os.path.isfile(m_ca):
            self.lbl_status_app_mqtt.config(
                text="❌ El puerto 8883 usa TLS: selecciona el certificado CA (📂)", fg=RED
            )
            return None

        self.mqtt_id = m_id
        self.mqtt_ip = m_ip
        self.mqtt_port = m_port
        self.mqtt_user = m_user
        self.mqtt_pass = m_pass
        self.dispositivo = m_disp
        self.ca_cert = m_ca

        datos_app_mqtt = self.get_config()
        try:
            config_store.guardar("panel", datos_app_mqtt)
        except OSError as e:
            print("[CONFIG] No se pudo guardar config_panel.json:", e)
        self.lbl_status_app_mqtt.config(
            text="✅ Guardado · Conectando al broker MQTT...", fg=GREEN
        )
        self.lbl_resumen_app_mqtt.config(
            text=f"ID: '{self.mqtt_id}' | IP: '{self.mqtt_ip}' | Puerto: {self.mqtt_port} | Usuario: '{self.mqtt_user}'"
        )
        print("[APP MQTT CONFIG] Datos del panel guardados y enviados a conectar")

        if self.on_connect_callback:
            self.on_connect_callback(datos_app_mqtt)

        return datos_app_mqtt

    def _cargar_guardado(self):
        g = config_store.cargar("panel")
        campos = {
            "mqtt_id": self.var_mqtt_id, "mqtt_ip": self.var_mqtt_ip,
            "mqtt_port": self.var_mqtt_port, "mqtt_user": self.var_mqtt_user,
            "mqtt_pass": self.var_mqtt_pass, "dispositivo": self.var_dispositivo,
            "ca_cert": self.var_ca,
        }
        for clave, var in campos.items():
            if g.get(clave) not in (None, ""):
                var.set(str(g[clave]))
        # ¿hay lo mínimo para conectar sola?
        self.tiene_guardado = all(g.get(k) for k in ("mqtt_id", "mqtt_ip", "mqtt_port", "dispositivo"))

    def autoconectar(self):
        """Conecta con los datos guardados (si estaban completos)."""
        if self.tiene_guardado:
            self.lbl_status_app_mqtt.config(text="⏳ Datos guardados cargados · conectando...", fg=AMBER)
            self.guardar_y_conectar()

    def _elegir_certificado(self):
        ruta = filedialog.askopenfilename(
            title="Certificado CA del broker",
            filetypes=[("Certificados", "*.crt *.pem *.cer"), ("Todos", "*.*")],
        )
        if ruta:
            self.var_ca.set(ruta)

    def set_estado(self, ok, texto):
        """Actualiza la etiqueta de estado (seguro desde cualquier hilo).
        ok: True conectado | False error | None conectando."""
        color = GREEN if ok else (AMBER if ok is None else RED)
        icono = "✅ " if ok else ("⏳ " if ok is None else "⚠️ ")
        self._ui(lambda: self.lbl_status_app_mqtt.config(text=icono + texto, fg=color))

    def get_config(self):
        return {
            "mqtt_id": self.mqtt_id,
            "mqtt_ip": self.mqtt_ip,
            "mqtt_port": self.mqtt_port,
            "mqtt_user": self.mqtt_user,
            "mqtt_pass": self.mqtt_pass,
            "dispositivo": self.dispositivo,
            "ca_cert": self.ca_cert,
        }


# Permite probar la vista de forma independiente
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Configuración ESP32 IoT")
    root.geometry("860x640")
    root.configure(bg=BG)

    def on_send(diccionarios):
        print("[CALLBACK ENVIAR] Diccionarios recibidos:", diccionarios)

    app_cfg = ConfigFrame(root, on_send_callback=on_send)
    app_cfg.pack(fill="both", expand=True, padx=20, pady=20)
    root.mainloop()