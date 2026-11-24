"""
Dashboard de estacionamiento IoT (6 espacios) - tkinter.

Vistas en la barra superior:
  1. 📊 Panel de Monitoreo
  2. ⚙️ Configuración Dispositivo (4 pestañas: Wi-Fi, MQTT, Dispositivo, Enviar Datos)
  3. 🖥️ Configuración del Panel (MQTT de la App + Guardar y Conectar)
"""

import queue
import time
import tkinter as tk
from config_view import AppConfigFrame, ConfigFrame
from mqtt_panel import PanelMQTT

N = 6
AUTOCONECTAR = True  # conecta el panel al abrir si hay datos guardados
OFFLINE_AFTER = 20  # segundos sin datos para pasar a modo offline

BG, CARD, BORDER = "#01040B", "#030A19", "#192A4C"
TEXT, MUTED = "#84ACE7", "#A9B7CE"
GREEN, AMBER, RED = "#16A24A", "#FBBF24", "#C11414"
FREE_BG, FREE_INK = "#0F2A1D", "#BBF7D0"
OCC_BG, OCC_INK = "#3A1416", "#FECACA"
FONT = "Helvetica"


class App(tk.Tk):
    def __init__(self, on_send_esp32=None, on_connect_app=None):
        super().__init__()
        self.title("Estacionamiento IoT")
        self.configure(bg=BG)
        self.geometry("1100x760")
        self.minsize(920, 680)

        self.on_send_esp32 = on_send_esp32
        self.on_connect_app = on_connect_app
        self._cola = queue.Queue()  # hilo de paho -> hilo de tkinter
        self.panel_mqtt = PanelMQTT(
            on_estado=self._estado_panel_mqtt, on_datos=self._recibir_estado
        )
        self.protocol("WM_DELETE_WINDOW", self._cerrar)

        self.occ = [False] * N
        self.last_msg = None  # time.time() del último dato; None = aún no llega ninguno
        self.offline = True  # offline hasta recibir el primer dato
        self.eventos = []
        self.vista_actual = "dashboard"

        self._build()
        self.refresh()
        self._tick()
        self._drenar_cola()
        if AUTOCONECTAR:
            self.after(500, self.app_config_view.autoconectar)

    # ---------- UI ----------
    def _label(self, parent, text="", size=12, bold=False, color=TEXT):
        return tk.Label(
            parent,
            text=text,
            fg=color,
            bg=parent["bg"],
            font=(FONT, size, "bold" if bold else "normal"),
        )

    def _build(self):
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=32, pady=24)

        # Encabezado
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        left = tk.Frame(head, bg=BG)
        left.pack(side="left")
        self._label(left, "CENTRO DE CONTROL · ESTACIONAMIENTO", 10, True, MUTED).pack(
            anchor="w"
        )
        self._label(left, "Panel en tiempo real", 26, True).pack(anchor="w")

        self.badge = tk.Label(
            head, font=(FONT, 12, "bold"), padx=16, pady=8, highlightthickness=1
        )
        self.badge.pack(side="right")

        # Barra de navegación principal (3 opciones)
        nav_bar = tk.Frame(root, bg=BG)
        nav_bar.pack(fill="x", pady=(16, 12))

        self.btn_nav_dashboard = tk.Button(
            nav_bar,
            text="📊 Panel de Monitoreo",
            font=(FONT, 11, "bold"),
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            highlightthickness=1,
            command=lambda: self._cambiar_vista("dashboard"),
        )
        self.btn_nav_dashboard.pack(side="left", padx=(0, 10))

        self.btn_nav_config = tk.Button(
            nav_bar,
            text="⚙️ Configuración Dispositivo (ESP32)",
            font=(FONT, 11, "bold"),
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            highlightthickness=1,
            command=lambda: self._cambiar_vista("config"),
        )
        self.btn_nav_config.pack(side="left", padx=(0, 10))

        self.btn_nav_app_config = tk.Button(
            nav_bar,
            text="🖥️ Configuración del Panel",
            font=(FONT, 11, "bold"),
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            highlightthickness=1,
            command=lambda: self._cambiar_vista("app_config"),
        )
        self.btn_nav_app_config.pack(side="left")

        # Contenedor para alternar vistas
        self.container = tk.Frame(root, bg=BG)
        self.container.pack(fill="both", expand=True)

        # 1. Vista de Monitoreo (Dashboard)
        self.frame_dashboard = tk.Frame(self.container, bg=BG)

        # Banner (lleno / offline); se muestra u oculta en refresh()
        self.banner = tk.Label(
            self.frame_dashboard, font=(FONT, 14, "bold"), anchor="w", padx=20, pady=14
        )

        # Cuerpo
        self.body = tk.Frame(self.frame_dashboard, bg=BG)
        self.body.pack(fill="both", expand=True, pady=(16, 0))
        self.body.columnconfigure(0, weight=1, uniform="c")
        self.body.columnconfigure(1, weight=2, uniform="c")
        self.body.rowconfigure(0, weight=1)

        # Tarjeta anillo
        c1 = tk.Frame(
            self.body, bg=CARD, highlightthickness=1, highlightbackground=BORDER
        )
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._label(c1, "Ocupación", 12, True, MUTED).pack(
            anchor="w", padx=24, pady=(20, 0)
        )
        self.ring = tk.Canvas(c1, width=260, height=260, bg=CARD, highlightthickness=0)
        self.ring.pack(pady=12)
        self.lbl_count = self._label(c1, "", 13, False, "#C7D2E4")
        self.lbl_count.pack(pady=(0, 20))

        # Tarjeta espacios
        c2 = tk.Frame(
            self.body, bg=CARD, highlightthickness=1, highlightbackground=BORDER
        )
        c2.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        self._label(c2, "Espacios", 12, True, MUTED).pack(
            anchor="w", padx=24, pady=(20, 8)
        )

        grid = tk.Frame(c2, bg=CARD)
        grid.pack(fill="both", expand=True, padx=24)
        self.cards = []
        for i in range(N):
            r, c = divmod(i, 3)
            grid.columnconfigure(c, weight=1, uniform="s")
            grid.rowconfigure(r, weight=1, uniform="r")
            f = tk.Frame(grid, highlightthickness=3)
            f.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            inner = tk.Frame(f)
            inner.place(relx=0.5, rely=0.5, anchor="center")
            l_tit = tk.Label(inner, text="ESPACIO", font=(FONT, 10, "bold"))
            l_id = tk.Label(inner, text=f"P{i + 1}", font=(FONT, 24, "bold"))
            l_ico = tk.Label(inner, font=(FONT, 28))
            l_est = tk.Label(inner, font=(FONT, 13, "bold"))
            for w in (l_tit, l_id, l_ico, l_est):
                w.pack()
            self.cards.append((f, inner, l_tit, l_id, l_ico, l_est))

        # Barra segmentada
        bar_box = tk.Frame(c2, bg=CARD)
        bar_box.pack(fill="x", padx=24, pady=(8, 20))
        self._label(
            bar_box, "Barra de ocupación · un segmento por espacio", 10, False, MUTED
        ).pack(anchor="w")
        self.bar = tk.Canvas(bar_box, height=26, bg=CARD, highlightthickness=0)
        self.bar.pack(fill="x", pady=(6, 0))
        self.bar.bind("<Configure>", lambda e: self._draw_bar())

        # Pie: última actualización + eventos
        foot = tk.Frame(self.frame_dashboard, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        foot.pack(fill="x", pady=(16, 0))
        self.lbl_update = self._label(foot, "", 13, True)
        self.lbl_update.pack(anchor="w", padx=24, pady=(16, 4))
        self.lbl_events = self._label(foot, "", 11, False, MUTED)
        self.lbl_events.pack(anchor="w", padx=24, pady=(0, 16))

        # 2. Vista de Configuración del ESP32 (4 pestañas)
        self.config_view = ConfigFrame(
            self.container,
            on_send_callback=self.on_send_esp32,
            on_send_mqtt_callback=self._enviar_config_mqtt,
            on_restablecer_callback=self._restablecer_esp32,
        )

        # 3. Vista de Configuración del Panel / App (MQTT + Guardar y Conectar)
        self.app_config_view = AppConfigFrame(
            self.container, on_connect_callback=self._conectar_panel
        )

        # Mostrar por defecto el Dashboard
        self._cambiar_vista("dashboard")

    # ---------- MQTT del panel ----------
    def _conectar_panel(self, datos_mqtt_app):
        self.panel_mqtt.conectar(datos_mqtt_app)
        if self.on_connect_app:
            self.on_connect_app(datos_mqtt_app)

    def _estado_panel_mqtt(self, ok, texto):
        # Lo llama paho desde su hilo; set_estado es seguro entre hilos
        self.app_config_view.set_estado(ok, texto)

    def _enviar_config_mqtt(self, diccionarios, destino, on_fin):
        self.panel_mqtt.enviar_config(destino, diccionarios, on_fin)

    def _restablecer_esp32(self, destino, on_fin):
        self.panel_mqtt.enviar_comando(destino, {"comando": "restablecer"}, on_fin)

    def _recibir_estado(self, resumen):
        # Lo llama paho desde su hilo: se encola y se aplica en el hilo de tkinter
        self._cola.put(lambda: self.on_estado_esp32(resumen))

    def _drenar_cola(self):
        try:
            while True:
                self._cola.get_nowait()()
        except queue.Empty:
            pass
        self.after(100, self._drenar_cola)

    def on_estado_esp32(self, resumen):
        """resumen = JSON ya descifrado del ESP32: {"espacios": {"1,1": 0/1, ...}, ...}
        Sensor (fila, columna) -> índice: (fila-1)*3 + (columna-1)."""
        nuevos = [False] * N
        for clave, valor in resumen.get("espacios", {}).items():
            fila, col = (int(x) for x in clave.split(","))
            idx = (fila - 1) * 3 + (col - 1)
            if 0 <= idx < N:
                nuevos[idx] = bool(valor)

        if self.last_msg is not None:  # el primer dato no genera eventos
            hora = time.strftime("%H:%M")
            for i, (antes, ahora) in enumerate(zip(self.occ, nuevos)):
                if antes != ahora:
                    self.eventos.insert(
                        0, f"{hora} · P{i + 1} {'ocupado' if ahora else 'libre'}"
                    )
            self.eventos = self.eventos[:3]

        self.occ = nuevos
        self.last_msg = time.time()
        self.offline = False
        self.refresh()

    def _cerrar(self):
        self.panel_mqtt.desconectar()
        self.destroy()

    def _cambiar_vista(self, vista):
        self.vista_actual = vista

        vistas = {
            "dashboard": (self.frame_dashboard, self.btn_nav_dashboard),
            "config": (self.config_view, self.btn_nav_config),
            "app_config": (self.app_config_view, self.btn_nav_app_config),
        }

        for key, (frame, btn) in vistas.items():
            if key == vista:
                frame.pack(fill="both", expand=True)
                btn.config(
                    bg="#1E3A6B",
                    fg="#FFFFFF",
                    activebackground="#254B8C",
                    activeforeground="#FFFFFF",
                    highlightbackground=TEXT,
                )
            else:
                frame.pack_forget()
                btn.config(
                    bg=CARD,
                    fg=TEXT,
                    activebackground="#101F3B",
                    activeforeground="#FFFFFF",
                    highlightbackground=BORDER,
                )

    # Accesos directos a diccionarios de configuración
    def get_config_esp32_por_pestana(self):
        """Retorna {'wifi': {...}, 'mqtt': {...}, 'dispositivo': {...}}."""
        return self.config_view.get_config_por_pestana()

    def get_config_panel(self):
        """Retorna el diccionario MQTT propio de la App."""
        return self.app_config_view.get_config()

    # ---------- API para el backend ----------
    def on_message(self, indice, ocupado):
        """Llamar cuando llegue un dato del sensor (indice 0..N-1)."""
        if self.occ[indice] != ocupado and self.last_msg is not None:
            hora = time.strftime("%H:%M")
            self.eventos.insert(
                0, f"{hora} · P{indice + 1} {'ocupado' if ocupado else 'libre'}"
            )
            self.eventos = self.eventos[:3]
        self.occ[indice] = ocupado
        self.last_msg = time.time()
        self.offline = False
        self.refresh()

    # ---------- Lógica interna ----------
    def _tick(self):
        edad = None if self.last_msg is None else time.time() - self.last_msg
        nuevo = edad is None or edad > OFFLINE_AFTER
        if nuevo != self.offline:
            self.offline = nuevo
            self.refresh()
        self._update_label()
        self.after(1000, self._tick)

    def _update_label(self):
        if self.last_msg is None:
            self.lbl_update.config(text="Última actualización: sin datos", fg=AMBER)
            return
        edad = int(time.time() - self.last_msg)
        hora = time.strftime("%H:%M:%S", time.localtime(self.last_msg))
        self.lbl_update.config(
            text=f"Última actualización: hace {edad} s  ({hora})",
            fg=AMBER if self.offline else TEXT,
        )

    def _estado(self):
        used = sum(self.occ)
        pct = round(used / N * 100)
        if pct >= 100:
            return used, pct, RED, "Lleno"
        if pct >= 70:
            return used, pct, AMBER, "Casi lleno"
        return used, pct, GREEN, "Disponible"

    # ---------- Dibujo ----------
    def refresh(self):
        used, pct, color, estado = self._estado()
        dim = self.offline

        if self.offline:
            self.badge.config(
                text="● MODO OFFLINE · datos en caché",
                fg=AMBER,
                bg=CARD,
                highlightbackground=AMBER,
            )
        else:
            self.badge.config(
                text="● Broker MQTT en línea",
                fg=TEXT,
                bg=CARD,
                highlightbackground=BORDER,
            )

        self.banner.pack_forget()
        if self.offline:
            msg = (
                "Esperando datos del ESP32..."
                if self.last_msg is None
                else "Sin conexión con el ESP32. Mostrando el último dato conocido."
            )
            self.banner.config(text="⚠  " + msg, bg=AMBER, fg="#1F1500")
            self.banner.pack(fill="x", pady=(16, 0), before=self.body)
        elif pct >= 100:
            self.banner.config(
                text="⚠  Estacionamiento lleno · alerta visual y sonora activada",
                bg=RED,
                fg="#1F0A0A",
            )
            self.banner.pack(fill="x", pady=(16, 0), before=self.body)

        # Anillo
        r = self.ring
        r.delete("all")
        box = (30, 30, 230, 230)
        r.create_oval(*box, outline=BORDER, width=26)
        if pct > 0:
            ext = -359.9 if pct >= 100 else -pct * 3.6
            r.create_arc(
                *box,
                start=90,
                extent=ext,
                style="arc",
                outline=MUTED if dim else color,
                width=26,
            )
        r.create_text(130, 118, text=f"{pct}%", fill=TEXT, font=(FONT, 44, "bold"))
        r.create_text(
            130, 160, text=estado, fill=MUTED if dim else color, font=(FONT, 13, "bold")
        )
        self.lbl_count.config(text=f"{used} ocupados · {N - used} libres")

        # Espacios
        for i, (f, inner, l_tit, l_id, l_ico, l_est) in enumerate(self.cards):
            o = self.occ[i]
            bg, ink, edge = (OCC_BG, OCC_INK, RED) if o else (FREE_BG, FREE_INK, GREEN)
            if dim:
                edge = "#7C8CA8"
            f.config(bg=bg, highlightbackground=edge, highlightcolor=edge)

            inner.config(bg=bg)
            for w in (l_tit, l_id, l_ico, l_est):
                w.config(bg=bg, fg=ink)

            l_ico.config(text="🚗" if o else "✔")
            l_est.config(text="Ocupado" if o else "Libre")

        self._draw_bar()
        self.lbl_events.config(
            text="Eventos recientes:  " + ("   |   ".join(self.eventos) or "—")
        )
        self._update_label()

    def _draw_bar(self):
        b = self.bar
        b.delete("all")
        w = max(b.winfo_width(), 100)
        gap = 6
        seg = (w - gap * (N - 1)) / N
        _, _, color, _ = self._estado()
        if self.offline:
            color = MUTED
        for i in range(N):
            x0 = i * (seg + gap)
            if self.occ[i]:
                b.create_rectangle(x0, 2, x0 + seg, 24, fill=color, outline=color)
            else:
                b.create_rectangle(
                    x0 + 1, 3, x0 + seg - 1, 23, fill=CARD, outline="#7C8CA8", width=2
                )


if __name__ == "__main__":
    # El envío por BLE y por MQTT ya está integrado; los callbacks son opcionales.
    app = App()
    app.mainloop()