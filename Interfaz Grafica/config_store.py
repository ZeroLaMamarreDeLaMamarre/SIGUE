"""
Persistencia de la configuración de la interfaz en un archivo JSON
(config_panel.json, junto a los .py). Así no hay que reescribir los datos
en cada arranque.

Estructura:  {"esp32": {...campos...}, "panel": {...campos...}}
"""

import json
import os

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_panel.json")

# False: no se escriben contraseñas en el archivo (habrá que teclearlas cada vez)
GUARDAR_CONTRASENAS = True
CAMPOS_SECRETOS = {"password", "mqtt_pass"}


def cargar(seccion):
    """Devuelve el dict guardado de la sección ({} si no hay archivo o está dañado)."""
    try:
        with open(RUTA, encoding="utf-8") as f:
            datos = json.load(f)
        valor = datos.get(seccion, {})
        return valor if isinstance(valor, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar(seccion, campos):
    """Mezcla `campos` en la sección (ignora los None) y escribe el archivo de forma
    atómica: nunca queda a medias si el programa se cierra mientras escribe."""
    try:
        with open(RUTA, encoding="utf-8") as f:
            todo = json.load(f)
        if not isinstance(todo, dict):
            todo = {}
    except (OSError, ValueError):
        todo = {}

    nuevos = {
        k: v for k, v in campos.items()
        if v is not None and (GUARDAR_CONTRASENAS or k not in CAMPOS_SECRETOS)
    }
    todo[seccion] = {**todo.get(seccion, {}), **nuevos}

    tmp = RUTA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(todo, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(tmp, 0o600)  # solo el usuario (en Windows no tiene efecto)
    except OSError:
        pass
    os.replace(tmp, RUTA)
