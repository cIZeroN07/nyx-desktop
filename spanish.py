"""Corrector: cambia expresiones de español latino por las de España."""
import re

# Frases primero (se aplican antes que las palabras sueltas)
PHRASES = {
    "qué onda": "qué pasa",
    "que onda": "qué pasa",
    "te quedó claro": "te ha quedado claro",
    "me quedó claro": "me ha quedado claro",
    "está padre": "mola",
    "qué padre": "qué guay",
}

WORDS = {
    "lindo": "bonito", "linda": "bonita", "lindos": "bonitos", "lindas": "bonitas",
    "chévere": "guay", "chido": "guay", "chida": "guay", "padrísimo": "genial",
    "celular": "móvil", "celulares": "móviles",
    "computadora": "ordenador", "computadoras": "ordenadores", "computador": "ordenador",
    "carro": "coche", "carros": "coches",
    "ahorita": "ahora", "acá": "aquí",
    "platicar": "hablar", "platicamos": "hablamos", "platiquemos": "hablemos",
    "chamba": "curro", "chambear": "currar",
    "contá": "cuéntame", "decime": "dime", "mirá": "mira", "vos": "tú",
    "jalar": "funcionar", "jala": "funciona",
}


def _keep_case(original, new):
    if original.isupper():
        return new.upper()
    if original[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


def _replace_all(text, table):
    for old, new in table.items():
        pattern = re.compile(rf"(?<!\w){re.escape(old)}(?!\w)", re.IGNORECASE)
        text = pattern.sub(lambda m, n=new: _keep_case(m.group(0), n), text)
    return text


# Letras de otros idiomas (chino, japonés, coreano, vietnamita...): señal de que el modelo se ha liado
FOREIGN = re.compile(r"[぀-ヿ㐀-鿿가-힯Ѐ-ӿ]|[ạảấầẩẫậắằẳẵặẹẻẽếềểễệịỉọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹđ]")


def cut_garbage(text: str) -> str:
    """Corta la respuesta donde empiecen caracteres de otro idioma."""
    m = FOREIGN.search(text)
    if not m:
        return text
    cut = text[:m.start()]
    # Volver al final de la última frase completa
    end = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
    return cut[:end + 1].strip() if end > 0 else cut.strip()


def strip_markdown(text: str) -> str:
    """Quita los *asteriscos* y **negritas** que algunos modelos (Gemma) ponen para resaltar."""
    return re.sub(r"\*{1,2}([^*\n]+?)\*{1,2}", r"\1", text)


def to_spain(text: str) -> str:
    return _replace_all(_replace_all(strip_markdown(cut_garbage(text)), PHRASES), WORDS)


if __name__ == "__main__":
    print(to_spain("¡Qué onda! Qué linda noche. Contá qué celular tienes. ¿Te quedó claro?"))
