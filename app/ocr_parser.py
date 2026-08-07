"""OCR y parseo de la cédula de identidad chilena (SRCeI).

La foto se toma con la cámara web del funcionario, así que el OCR nunca va a
ser perfecto (ángulo, reflejos, fondo). Por eso este módulo entrega su mejor
estimación de cada campo junto con el texto crudo; la pantalla de registro
siempre muestra la foto capturada al lado del formulario para que el
funcionario revise y corrija antes de guardar.
"""

import re

import pytesseract
from PIL import Image, ImageFilter, ImageOps

MESES = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "SET": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}

RUN_RE = re.compile(r"(\d{1,2}\.\d{3}\.\d{3}-[\dkK])")
FECHA_RE = re.compile(r"(\d{1,2})\s+([A-ZÑ]{3,4})\.?\s+(\d{4})")

STOP_LABELS_NOMBRES = ("NOMBRES", "NACIONALIDAD", "SEXO", "REPUBLICA", "REPÚBLICA")
STOP_LABELS_APELLIDOS = ("APELLIDOS",)


def _preprocess_variants(image: Image.Image):
    """Genera un par de versiones preprocesadas de la imagen para intentar el OCR."""
    base = image.convert("RGB")
    gray = ImageOps.grayscale(base)

    variants = [gray]

    contrast = ImageOps.autocontrast(gray, cutoff=1)
    w, h = contrast.size
    scale = 2 if max(w, h) < 2200 else 1
    upscaled = contrast.resize((w * scale, h * scale), Image.LANCZOS)
    sharpened = upscaled.filter(ImageFilter.SHARPEN)
    variants.append(sharpened)

    return variants


def _ocr_text(image: Image.Image, lang: str = "spa") -> str:
    config = "--psm 6"
    return pytesseract.image_to_string(image, lang=lang, config=config)


def _clean_lines(text: str):
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.upper().splitlines()]
    return [ln for ln in lines if ln]


def _looks_like_name(line: str) -> bool:
    if not line or len(line) < 2:
        return False
    if any(ch.isdigit() for ch in line):
        return False
    letters = re.sub(r"[^A-ZÁÉÍÓÚÑ]", "", line)
    return len(letters) >= 3


def _clean_edges(candidate: str) -> str:
    candidate = re.sub(r"^[^A-ZÁÉÍÓÚÑ]+", "", candidate)
    candidate = re.sub(r"[^A-ZÁÉÍÓÚÑ]+$", "", candidate)
    return candidate


def _strip_short_words(text: str) -> str:
    """Descarta palabras sueltas de 1-2 letras (ruido típico del OCR)."""
    words = [w for w in text.split() if len(re.sub(r"[^A-ZÁÉÍÓÚÑ]", "", w)) >= 3]
    return " ".join(words)


def _quality(text: str) -> int:
    """Cuenta palabras 'reales' (>=3 letras) en un candidato, para comparar opciones."""
    return len(_strip_short_words(text).split())


def _extract_forward(lines, start_labels, stop_labels, max_lines=2):
    for i, line in enumerate(lines):
        if any(lbl in line for lbl in start_labels):
            collected = []
            for j in range(i + 1, min(i + 1 + max_lines + 2, len(lines))):
                candidate = lines[j]
                if any(stop in candidate for stop in stop_labels):
                    break
                if any(stop in candidate for stop in start_labels):
                    break
                candidate = _clean_edges(candidate)
                if _looks_like_name(candidate):
                    collected.append(candidate)
                if len(collected) >= max_lines:
                    break
            if collected:
                return " ".join(collected)
    return ""


def _extract_backward(lines, anchor_labels, stop_labels, max_lines=2):
    """Busca el bloque de apellidos mirando las líneas justo ANTES de 'NOMBRES',
    útil cuando la etiqueta 'APELLIDOS' no fue reconocida por el OCR."""
    for i, line in enumerate(lines):
        if any(lbl in line for lbl in anchor_labels):
            collected = []
            for j in range(i - 1, max(i - 1 - max_lines - 2, -1), -1):
                candidate = lines[j]
                if any(stop in candidate for stop in stop_labels):
                    break
                if any(stop in candidate for stop in anchor_labels):
                    break
                candidate = _clean_edges(candidate)
                if _looks_like_name(candidate):
                    collected.append(candidate)
                if len(collected) >= max_lines:
                    break
            if collected:
                return " ".join(reversed(collected))
    return ""


def _best_candidate(*candidates):
    cleaned = [_strip_short_words(c) for c in candidates if c]
    if not cleaned:
        return ""
    return max(cleaned, key=lambda c: len(c.split()))


def _extract_run(text: str) -> str:
    match = RUN_RE.search(text.upper())
    return match.group(1) if match else ""


def _extract_fecha_nacimiento(text: str):
    upper = text.upper()
    idx = upper.find("NACIMIENTO")
    search_zone = upper[idx:] if idx != -1 else upper
    match = FECHA_RE.search(search_zone)
    if not match:
        return None, ""
    dia, mes_txt, anio = match.groups()
    mes = MESES.get(mes_txt[:3])
    if not mes:
        return None, match.group(0)
    try:
        from datetime import date
        return date(int(anio), mes, int(dia)), match.group(0)
    except ValueError:
        return None, match.group(0)


def validar_run(run: str) -> bool:
    """Valida el dígito verificador del RUN chileno (módulo 11)."""
    if not run:
        return False
    run = run.replace(".", "").replace("-", "").strip().upper()
    if len(run) < 2:
        return False
    cuerpo, dv = run[:-1], run[-1]
    if not cuerpo.isdigit():
        return False
    suma = 0
    multiplo = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplo
        multiplo = multiplo + 1 if multiplo < 7 else 2
    resto = 11 - (suma % 11)
    dv_esperado = {11: "0", 10: "K"}.get(resto, str(resto))
    return dv_esperado == dv


def _parse_text(text: str) -> dict:
    lines = _clean_lines(text)

    apellidos_fwd = _extract_forward(lines, STOP_LABELS_APELLIDOS, STOP_LABELS_NOMBRES)
    apellidos_bwd = _extract_backward(lines, ("NOMBRES",), STOP_LABELS_APELLIDOS)
    apellidos = _best_candidate(apellidos_fwd, apellidos_bwd)

    nombres_raw = _extract_forward(lines, ("NOMBRES",), STOP_LABELS_NOMBRES[1:])
    nombres = _strip_short_words(nombres_raw)

    rut = _extract_run(text)
    fecha_nacimiento, fecha_raw = _extract_fecha_nacimiento(text)

    return {
        "apellidos": apellidos,
        "nombres": nombres,
        "rut": rut,
        "rut_valido": validar_run(rut) if rut else False,
        "fecha_nacimiento": fecha_nacimiento.isoformat() if fecha_nacimiento else "",
        "fecha_nacimiento_texto_detectado": fecha_raw,
    }


def _merge_results(results: list) -> dict:
    """Combina los resultados de cada variante de preprocesamiento, quedándose
    con el mejor valor individual para cada campo (no con una variante entera),
    ya que distintas versiones de la imagen aciertan en distintos campos."""
    merged = {
        "apellidos": _best_candidate(*(r["apellidos"] for r in results)),
        "nombres": _best_candidate(*(r["nombres"] for r in results)),
        "rut": "",
        "fecha_nacimiento": "",
        "fecha_nacimiento_texto_detectado": "",
    }

    ruts_validos = [r["rut"] for r in results if r["rut"] and r["rut_valido"]]
    ruts_cualquiera = [r["rut"] for r in results if r["rut"]]
    merged["rut"] = (ruts_validos or ruts_cualquiera or [""])[0]
    merged["rut_valido"] = validar_run(merged["rut"]) if merged["rut"] else False

    for r in results:
        if r["fecha_nacimiento"]:
            merged["fecha_nacimiento"] = r["fecha_nacimiento"]
            merged["fecha_nacimiento_texto_detectado"] = r["fecha_nacimiento_texto_detectado"]
            break

    return merged


def parse_cedula(image_path: str, lang: str = "spa") -> dict:
    """Ejecuta OCR sobre la foto de la cédula y devuelve los campos detectados.

    Prueba varias variantes de preprocesamiento (la foto puede salir con
    ángulo, reflejos o poca luz) y combina el mejor valor de cada campo entre
    todas ellas, en vez de confiar en una sola pasada de OCR.
    """
    image = Image.open(image_path)
    results = []
    raw_texts = []

    for variant in _preprocess_variants(image):
        text = _ocr_text(variant, lang=lang)
        raw_texts.append(text)
        results.append(_parse_text(text))

    merged = _merge_results(results)
    merged["texto_ocr_crudo"] = "\n\n---\n\n".join(raw_texts)
    return merged
