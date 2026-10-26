"""Recordatorios: "recuérdame el examen el jueves a las 10" y Nyx te avisa.

La fecha y la hora se calculan aquí con reglas (los modelos pequeños se lían con las fechas);
el modelo solo resume QUÉ hay que recordar.
"""
import json
import re
from datetime import datetime, timedelta

from memory import DATA, _read, _write

FILE = DATA / "reminders.json"
DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
NUMBERS = {"una": 1, "un": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
           "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20,
           "treinta": 30, "cuarenta": 40, "cuarenta y cinco": 45}
NUM = r"(\d{1,3}|" + "|".join(sorted(NUMBERS, key=len, reverse=True)) + ")"

# Solo preguntamos al modelo si el mensaje suena a recordatorio
TRIGGER = re.compile(r"recu[eé]rd|av[ií]sa|recordatorio|no me dejes olvidar|apunta que", re.IGNORECASE)

PROMPT = """El usuario pide a su asistente que le recuerde algo. Escribe SOLO qué hay que recordar, en pocas palabras,
sin fechas ni horas, como una nota. Responde SOLO con JSON: {{"texto": "..."}}

Ejemplos:
«recuérdame el examen de Java el jueves a las 10» -> {{"texto": "Examen de Java"}}
«avísame en 10 minutos de sacar la pizza» -> {{"texto": "Sacar la pizza del horno"}}
«mañana recuérdame llamar a mi madre» -> {{"texto": "Llamar a tu madre"}}

«{msg}» ->"""


def _num(word):
    word = word.lower()
    return int(word) if word.isdigit() else NUMBERS.get(word)


def when_from(text, now=None):
    """Saca la fecha y hora de un mensaje en español. Devuelve datetime o None."""
    now = now or datetime.now()
    t = text.lower()

    # "en 10 minutos", "dentro de una hora", "en media hora"
    if re.search(r"(en|dentro de) media hora", t):
        return now + timedelta(minutes=30)
    m = re.search(rf"(?:en|dentro de) {NUM} (minuto|minutos|min|hora|horas)\b", t)
    if m:
        n = _num(m.group(1))
        return now + (timedelta(hours=n) if m.group(2).startswith("hora") else timedelta(minutes=n))

    # Día
    day = None
    if "pasado mañana" in t:
        day = now.date() + timedelta(days=2)
    elif re.search(r"\bmañana\b", t.replace("por la mañana", "").replace("de la mañana", "")):
        day = now.date() + timedelta(days=1)
    elif re.search(r"\bhoy\b|esta tarde|esta noche", t):
        day = now.date()
    else:
        for i, name in enumerate(DAYS):
            if re.search(rf"\b{name.replace('é', '[eé]').replace('á', '[aá]')}\b", t):
                ahead = (i - now.weekday()) % 7 or 7     # "el lunes" dicho un lunes = el que viene
                day = now.date() + timedelta(days=ahead)
                break
        m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", t)
        if m:
            d, mo = int(m.group(1)), int(m.group(2))
            year = now.year + (1 if (mo, d) < (now.month, now.day) else 0)
            day = datetime(year, mo, d).date()

    # Hora: "a las 10", "a las 17:30", "a las diez de la noche", "a la una"
    hour = minute = None
    m = re.search(rf"a las? {NUM}(?:[:.h](\d{{2}}))?( y media| y cuarto)?", t)
    if m and _num(m.group(1)) is not None and _num(m.group(1)) <= 24:
        hour = _num(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if m.group(3):
            minute = 30 if "media" in m.group(3) else 15
        if hour < 12 and re.search(r"de la (tarde|noche)|esta (tarde|noche)", t):
            hour += 12

    if day is None and hour is None:
        return None
    if hour is None:
        hour, minute = 9, 0                                   # sin hora: a las 9 de ese día
    if day is None:                                           # sin día: hoy, o mañana si ya ha pasado
        day = now.date() if (hour, minute) > (now.hour, now.minute) else now.date() + timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute)


def parse_text(answer):
    try:
        text = (json.loads(answer).get("texto") or "").strip()
    except (ValueError, AttributeError):
        return None
    return text or None


def load():
    return _read(FILE, [])


def add(text, when):
    items = load()
    items.append({"texto": text, "cuando": when.strftime("%Y-%m-%d %H:%M")})
    items.sort(key=lambda r: r["cuando"])
    _write(FILE, items)


def pop_due():
    """Saca los recordatorios que ya han vencido."""
    items = load()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    due = [r for r in items if r["cuando"] <= now]
    if due:
        _write(FILE, [r for r in items if r["cuando"] > now])
    return due


def pretty(when):
    today = datetime.now().date()
    if when.date() == today:
        day = "hoy"
    elif when.date() == today + timedelta(days=1):
        day = "mañana"
    else:
        day = f"el {DAYS[when.weekday()]} {when:%d/%m}"
    return f"{day} a las {when:%H:%M}"
