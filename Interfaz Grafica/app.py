"""
Dashboard de estacionamiento IoT (6 espacios) - tkinter.

Solo interfaz: no genera datos. El backend debe llamar a
    app.on_message(indice, ocupado)      # indice 0..5, ocupado True/False
cada vez que llegue un dato (MQTT, serial, HTTP...). Si pasan OFFLINE_AFTER
segundos sin datos, la UI entra sola en "Modo offline".
"""

import time
import tkinter as tk
from config_view import ConfigFrame

N = 6
OFFLINE_AFTER = 20  # segundos sin datos para pasar a modo offline

BG, CARD, BORDER = "#01040B", "#030A19", "#192A4C"
TEXT, MUTED = "#84ACE7", "#A9B7CE"
GREEN, AMBER, RED = "#16A24A", "#FBBF24", "#C11414"
FREE_BG, FREE_INK = "#0F2A1D", "#BBF7D0"
OCC_BG, OCC_INK = "#3A1416", "#FECACA"
FONT = "Helvetica"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Estacionamiento IoT")
        self.configure(bg=BG)
        self.geometry("1100x740")
        self.minsize(900, 660)

        self.occ = [False] * N
        self.last_msg = None  # time.time() del último dato; None = aún no llega ninguno
        self.offline = True  # offline hasta recibir el primer dato
        self.eventos = []
        self.vista_actual = "dashboard"

        self._build()
        self.refresh()
        self._tick()

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

        # Barra de navegación principal (Monitoreo vs Configuración)
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
            text="⚙️ Configuración (Wi-Fi · MQTT · Dispositivo)",
            font=(FONT, 11, "bold"),
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            highlightthickness=1,
            command=lambda: self._cambiar_vista("config"),
        )
        self.btn_nav_config.pack(side="left")

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

        # 2. Vista de Configuración (3 pestañas: Wi-Fi, MQTT, Dispositivo)
        self.config_view = ConfigFrame(self.container)

        # Mostrar por defecto el Dashboard
        self._cambiar_vista("dashboard")

    def _cambiar_vista(self, vista):
        self.vista_actual = vista
        if vista == "dashboard":
            self.config_view.pack_forget()
            self.frame_dashboard.pack(fill="both", expand=True)
            self.btn_nav_dashboard.config(
                bg="#1E3A6B",
                fg="#FFFFFF",
                activebackground="#254B8C",
                activeforeground="#FFFFFF",
                highlightbackground=TEXT,
            )
            self.btn_nav_config.config(
                bg=CARD,
                fg=TEXT,
                activebackground="#101F3B",
                activeforeground="#FFFFFF",
                highlightbackground=BORDER,
            )
        else:
            self.frame_dashboard.pack_forget()
            self.config_view.pack(fill="both", expand=True)
            self.btn_nav_config.config(
                bg="#1E3A6B",
                fg="#FFFFFF",
                activebackground="#254B8C",
                activeforeground="#FFFFFF",
                highlightbackground=TEXT,
            )
            self.btn_nav_dashboard.config(
                bg=CARD,
                fg=TEXT,
                activebackground="#101F3B",
                activeforeground="#FFFFFF",
                highlightbackground=BORDER,
            )

    # Accesos directos a variables de configuración
    @property
    def ssid(self):
        return self.config_view.ssid

    @property
    def password(self):
        return self.config_view.password

    @property
    def mqtt_id(self):
        return self.config_view.mqtt_id

    @property
    def mqtt_ip(self):
        return self.config_view.mqtt_ip

    @property
    def mqtt_port(self):
        return self.config_view.mqtt_port

    @property
    def mqtt_user(self):
        return self.config_view.mqtt_user

    @property
    def mqtt_pass(self):
        return self.config_view.mqtt_pass

    @property
    def nuevo_nombre(self):
        return self.config_view.nuevo_nombre

    def get_config(self):
        return self.config_view.get_config()

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
        dim = self.offline  # en offline se muestra el "último dato conocido"

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
    app = App()
    app.mainloop()
