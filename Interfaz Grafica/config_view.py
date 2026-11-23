"""
Módulo de Configuración con 3 Pestañas para ESP32 / IoT.

Pestañas:
  1. Wi-Fi: SSID y Contraseña (con botón ver/ocultar)
  2. MQTT: Client ID, IP del Broker, Puerto, Usuario, Contraseña (con ver/ocultar)
  3. Dispositivo: Nombre del ESP32 (máx 15 chars para memoria NVS)

Puede usarse:
  - De forma independiente: python3 config_view.py
  - Importado en app.py: como un Frame incrustable
"""

import tkinter as tk

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


class ConfigFrame(tk.Frame):
    """
    Frame contenedor con las 3 pestañas de configuración.
    Se puede incrustar en cualquier ventana o usarse como vista principal.
    """

    def __init__(self, parent, on_save_callback=None, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self.on_save_callback = on_save_callback

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

        self._build()

    def _label(self, parent, text="", size=11, bold=False, color=TEXT):
        return tk.Label(
            parent,
            text=text,
            fg=color,
            bg=parent["bg"],
            font=(FONT, size, "bold" if bold else "normal"),
        )

    def _create_field(
        self, parent, label_text, is_password=False, default_val="", max_len=None
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

    def _build(self):
        # Barra superior de navegación entre las 3 pestañas
        nav_bar = tk.Frame(self, bg=BG)
        nav_bar.pack(fill="x", pady=(0, 16))

        tabs_data = [
            ("wifi", "📶 1. Wi-Fi"),
            ("mqtt", "📡 2. Broker MQTT"),
            ("device", "⚙️ 3. Dispositivo"),
        ]

        for tab_id, tab_title in tabs_data:
            btn = tk.Button(
                nav_bar,
                text=tab_title,
                font=(FONT, 11, "bold"),
                relief="flat",
                padx=20,
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

        self.select_tab("wifi")

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

    # ---------- 1. PESTAÑA WI-FI ----------
    def _build_wifi_tab(self):
        f = tk.Frame(self.container, bg=BG)
        self.tab_frames["wifi"] = f

        card = tk.Frame(f, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=4, pady=4)

        # Encabezado
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

        # Campos
        body = tk.Frame(card, bg=CARD)
        body.pack(fill="x", padx=28, pady=10)

        self.var_ssid, self.entry_ssid = self._create_field(
            body, "Nombre de Red (SSID):"
        )
        self.var_password, self.entry_password = self._create_field(
            body, "Contraseña:", is_password=True
        )

        # Botones y status
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

        # Tarjeta de variables en memoria
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
            return

        self.ssid = ssid
        self.password = pwd
        self.wifi_ssid_listo = True
        self.wifi_pass_listo = bool(pwd)

        hidden = "•" * len(pwd) if pwd else "(sin clave)"
        self.lbl_status_wifi.config(text="✅ Wi-Fi guardado", fg=GREEN)
        self.lbl_resumen_wifi.config(
            text=f"self.ssid = '{self.ssid}'   |   self.password = '{hidden}'"
        )
        if self.on_save_callback:
            self.on_save_callback("wifi", {"ssid": self.ssid, "password": self.password})

    # ---------- 2. PESTAÑA MQTT ----------
    def _build_mqtt_tab(self):
        f = tk.Frame(self.container, bg=BG)
        self.tab_frames["mqtt"] = f

        card = tk.Frame(f, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=4, pady=4)

        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=28, pady=(24, 12))
        self._label(head, "📡 Configuración del Broker MQTT", 17, True).pack(anchor="w")
        self._label(
            head,
            "Parámetros de conexión al servidor de telemetría MQTT.",
            11,
            False,
            MUTED,
        ).pack(anchor="w", pady=(3, 0))

        # Grid de campos
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

        # Acciones
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

        # Resumen
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
            return

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
        if self.on_save_callback:
            self.on_save_callback(
                "mqtt",
                {
                    "id": self.mqtt_id,
                    "ip": self.mqtt_ip,
                    "port": self.mqtt_port,
                    "user": self.mqtt_user,
                    "pass": self.mqtt_pass,
                },
            )

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

        # Resumen
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
            return

        if len(nombre) > 15:
            self.lbl_status_device.config(
                text="⚠️ Advertencia: Excede los 15 caracteres para NVS", fg=AMBER
            )
        else:
            self.lbl_status_device.config(text="✅ Nombre guardado", fg=GREEN)

        self.nuevo_nombre = nombre
        self.nombre_listo = True
        self.lbl_resumen_device.config(text=f"self.nuevo_nombre = '{self.nuevo_nombre}'")
        if self.on_save_callback:
            self.on_save_callback("device", {"nuevo_nombre": self.nuevo_nombre})

    def get_config(self):
        """Retorna el diccionario consolidado con todas las variables."""
        return {
            "ssid": self.ssid,
            "password": self.password,
            "mqtt_id": self.mqtt_id,
            "mqtt_ip": self.mqtt_ip,
            "mqtt_port": self.mqtt_port,
            "mqtt_user": self.mqtt_user,
            "mqtt_pass": self.mqtt_pass,
            "nuevo_nombre": self.nuevo_nombre,
        }


# Permite probar la vista de forma independiente
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Configuración ESP32 IoT")
    root.geometry("820x620")
    root.configure(bg=BG)

    def on_save(modulo, datos):
        print(f"[CALLBACK] {modulo} guardado:", datos)

    app_cfg = ConfigFrame(root, on_save_callback=on_save)
    app_cfg.pack(fill="both", expand=True, padx=20, pady=20)
    root.mainloop()
