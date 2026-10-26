"""Memoria de Nyx: guarda la conversación y las cosas que va aprendiendo del usuario."""
import json

import config
import persona

DATA = config.DATA_DIR
HISTORY = DATA / "history.json"
FACTS = DATA / "facts.json"
MAX_HISTORY = 30   # mensajes que recuerda de la conversación
MAX_FACTS = 40     # datos sobre el usuario que guarda como mucho


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path, data):
    DATA.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- conversación ----------
def load_history():
    return _read(HISTORY, [])[-MAX_HISTORY:]


def save_history(messages):
    _write(HISTORY, messages[-MAX_HISTORY:])


# ---------- datos sobre el usuario ----------
def load_facts():
    return _read(FACTS, [])


def add_facts(new):
    facts = load_facts()
    known = {f.lower() for f in facts}
    for fact in new:
        if fact.lower() not in known:
            facts.append(fact)
            known.add(fact.lower())
    _write(FACTS, facts[-MAX_FACTS:])


def clear():
    for path in (HISTORY, FACTS):
        path.unlink(missing_ok=True)


# ---------- instrucciones para el modelo ----------
def system_prompt(extra=""):
    parts = [persona.system_text()]
    facts = load_facts()
    if facts:
        parts.append(f"Cosas que recuerdas de {config.name()} (úsalas con naturalidad, sin soltarlas todas de golpe):\n"
                     + "\n".join(f"- {f}" for f in facts))
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


FACT_PROMPT = """Extrae datos sobre {name} de su mensaje: qué juegos juega, qué le gusta, qué estudia,
exámenes o fechas, planes, amigos, mascotas, cosas que le preocupan. No apuntes saludos ni preguntas.
Cada dato es una frase corta en español de España que empieza por "{name}".
Responde SOLO con JSON: {{"datos": [ ... ]}}  (lista vacía si no hay nada nuevo).

Ejemplos:
Mensaje: «hola que tal» -> {{"datos": []}}
Mensaje: «estoy jugando al minecraft con una build de arquero» -> {{"datos": ["{name} juega al Minecraft con una build de arquero"]}}
Mensaje: «mi colega Pablo me ha dicho que pruebe el Hades» -> {{"datos": ["{name} tiene un amigo que se llama Pablo"]}}
Mensaje: «el lunes tengo examen de bases de datos y estoy agobiado» -> {{"datos": ["{name} tiene examen de bases de datos el lunes", "A {name} le agobian los exámenes"]}}

Datos que ya se saben (no los repitas):
{known}

Mensaje: «{msg}» ->"""


def fact_prompt(known, msg):
    return FACT_PROMPT.format(name=config.name(), known=known, msg=msg)


def parse_facts(answer):
    try:
        items = json.loads(answer).get("datos", [])
    except (ValueError, AttributeError):
        return []
    out = []
    for item in items:
        if isinstance(item, str) and config.name().lower() in item.lower() and 8 < len(item) < 160:
            out.append(item.strip().rstrip(".") + ".")
    return out
