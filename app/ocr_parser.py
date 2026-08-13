"""OCR y parseo de la cédula de identidad chilena (SRCeI).

La foto se toma con la cámara web del funcionario, así que el OCR nunca va a
ser perfecto (ángulo, reflejos, fondo). Por eso este módulo entrega su mejor
estimación de cada campo junto con el texto crudo; la pantalla de registro
siempre muestra la foto capturada al lado del formulario para que el
funcionario revise y corrija antes de guardar.
"""

import re
import unicodedata

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

# Palabras del "boilerplate" del carnet (nacionalidades y etiquetas) que a veces
# el OCR arrastra junto al nombre cuando no reconoce bien la etiqueta que las
# antecede (ej. "NACIONALIDAD" mal leída). Nunca son parte de un nombre real,
# así que se descartan aunque hayan quedado pegadas al resto del texto.
PALABRAS_NO_NOMBRE = {
    "CHILENA", "CHILENO", "EXTRANJERA", "EXTRANJERO",
    "NACIONALIDAD", "SEXO", "REPUBLICA", "CHILE",
    "CEDULA", "IDENTIDAD", "SERVICIO", "REGISTRO", "CIVIL",
    "IDENTIFICACION", "DOCUMENTO", "NUMERO", "FECHA",
    "NACIMIENTO", "EMISION", "VENCIMIENTO", "FIRMA", "TITULAR",
    "APELLIDOS", "NOMBRES", "NOFIRMA",
}


def _sin_acentos(texto: str) -> str:
    normalizado = unicodedata.normalize("NFD", texto)
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def _factor_escala(w: int, h: int) -> int:
    """Cámaras de baja resolución entregan carnets con muy pocos píxeles por
    letra -- mientras más chica la foto, más hay que agrandarla para que
    Tesseract tenga margen para reconocer los caracteres."""
    lado_mayor = max(w, h)
    if lado_mayor < 900:
        return 4
    if lado_mayor < 1400:
        return 3
    if lado_mayor < 2200:
        return 2
    return 1


def _umbral_otsu(imagen_gris: Image.Image) -> int:
    """Umbral de binarización de Otsu, calculado a mano sobre el histograma
    (sin depender de numpy/opencv) -- separa texto de fondo incluso con
    contraste parejo o sombras, mejor que un umbral fijo."""
    hist = imagen_gris.histogram()
    total = sum(hist)
    if total == 0:
        return 127
    suma_total = sum(i * c for i, c in enumerate(hist))

    peso_fondo = 0
    suma_fondo = 0
    mejor_varianza = -1.0
    mejor_umbral = 127

    for i, c in enumerate(hist):
        peso_fondo += c
        if peso_fondo == 0:
            continue
        peso_frente = total - peso_fondo
        if peso_frente == 0:
            break
        suma_fondo += i * c
        media_fondo = suma_fondo / peso_fondo
        media_frente = (suma_total - suma_fondo) / peso_frente
        varianza_entre = peso_fondo * peso_frente * (media_fondo - media_frente) ** 2
        if varianza_entre > mejor_varianza:
            mejor_varianza = varianza_entre
            mejor_umbral = i

    return mejor_umbral


def _preprocess_variants(image: Image.Image):
    """Genera varias versiones preprocesadas de la imagen para intentar el OCR,
    pensadas para tolerar cámaras de baja resolución/borrosas."""
    base = image.convert("RGB")
    gray = ImageOps.grayscale(base)
    w, h = gray.size
    scale = _factor_escala(w, h)

    variants = [gray]

    contrast = ImageOps.autocontrast(gray, cutoff=1)
    upscaled = contrast.resize((w * scale, h * scale), Image.LANCZOS)
    sharpened = upscaled.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    variants.append(sharpened)

    umbral = _umbral_otsu(contrast)
    binarizada = upscaled.point(lambda p: 255 if p > umbral else 0)
    variants.append(binarizada)

    return variants


def _ocr_text(image: Image.Image, lang: str = "spa", psm: str = "6") -> str:
    config = f"--psm {psm}"
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


def _es_palabra_valida(palabra: str) -> bool:
    letras = re.sub(r"[^A-ZÁÉÍÓÚÑ]", "", palabra)
    if len(letras) < 3:
        return False
    return _sin_acentos(letras) not in PALABRAS_NO_NOMBRE


def _strip_short_words(text: str) -> str:
    """Descarta palabras sueltas de 1-2 letras y términos que no son nombres
    (nacionalidad, etiquetas del carnet, etc.) -- ruido típico del OCR."""
    words = [w for w in text.split() if _es_palabra_valida(w)]
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
    """Combina varias lecturas del mismo campo (una por variante de OCR).

    Antes se usaba la que tuviera más palabras, pero una variante ruidosa
    (típico con fotos de baja resolución) a veces agrega una palabra de
    ruido al final y terminaba "ganando" por ser la más larga. En cambio,
    se busca el prefijo de palabras más largo que compartan al menos dos
    variantes -- si dos lecturas independientes coinciden, es mucho más
    probable que sea el nombre real que una palabra extra que solo
    apareció en una pasada.
    """
    cleaned = [_strip_short_words(c) for c in candidates if c]
    cleaned = [c for c in cleaned if c]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]

    listas = [c.split() for c in cleaned]
    largo_max = max(len(p) for p in listas)

    for largo in range(largo_max, 0, -1):
        conteo = {}
        for palabras in listas:
            if len(palabras) >= largo:
                clave = tuple(palabras[:largo])
                conteo[clave] = conteo.get(clave, 0) + 1
        coincidencias = [clave for clave, n in conteo.items() if n >= 2]
        if coincidencias:
            return " ".join(max(coincidencias, key=len))

    # Ninguna variante coincide con otra -- nos quedamos con la más corta,
    # que arriesga menos que sumar palabras no confirmadas por nadie más.
    return min(cleaned, key=lambda c: len(c.split()))


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
