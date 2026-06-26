"""
carousel.py — Genera contenido del carrusel con Claude + búsqueda web.
Soporta: texto libre, tema con investigación, y fotos con Claude Vision.
"""
import json
import os
import base64
import urllib.request
import urllib.parse
import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

PLATFORMS = {
    "instagram": {"name": "Instagram", "ratio": "4:5 (1080×1350px)", "slides": 7},
    "linkedin":  {"name": "LinkedIn",  "ratio": "1:1 (1080×1080px)", "slides": 6},
    "facebook":  {"name": "Facebook",  "ratio": "1:1 (1080×1080px)", "slides": 6},
}

SYSTEM_PROMPT = """Eres un experto en contenido para redes sociales.
Creas carruseles profesionales, atractivos y diseñados para generar engagement.

Devuelve SOLO JSON válido (sin markdown), con esta estructura exacta:

{
  "idea": "resumen del tema en 1 línea",
  "slides": [
    {"type":"hero","tag":"TEMA EN MAYÚSCULAS","heading":"Titular impactante máx 10 palabras","body":""},
    {"type":"context","tag":"TEMA","heading":"Por qué importa esto","body":"1-2 oraciones que enganchen"},
    {"type":"insight","tag":"TEMA","heading":"El dato o secreto clave","body":"Revelación en 1-2 oraciones","quote":"estadística o cita destacada (o vacío)"},
    {"type":"features","tag":"TEMA","heading":"Lo que necesitas saber","items":[{"label":"Punto 1","description":"explicación"},{"label":"Punto 2","description":"explicación"},{"label":"Punto 3","description":"explicación"}]},
    {"type":"depth","tag":"TEMA","heading":"El detalle que marca la diferencia","body":"Profundización en 1-2 oraciones"},
    {"type":"proof","tag":"TEMA","heading":"Pasos para aplicarlo hoy","steps":[{"number":"01","title":"Primer paso","description":"acción concreta"},{"number":"02","title":"Segundo paso","description":"acción concreta"},{"number":"03","title":"Tercer paso","description":"acción concreta"}]},
    {"type":"cta","tag":"SÍGUENOS","heading":"¿Quieres más contenido como este?","body":"Guarda este post y síguenos para no perderte nada.","cta_text":"COMENTA \"INFO\""}
  ],
  "caption": "Pie de foto conversacional con emojis, máx 80 palabras",
  "hashtags": ["#hashtag1","#hashtag2","#hashtag3","#hashtag4","#hashtag5"]
}

REGLAS CRÍTICAS:
- Slide hero: MÁXIMO 10 palabras.
- items[] SIEMPRE lista de objetos {label, description} — NUNCA strings.
- steps[] SIEMPRE lista de objetos {number, title, description} — NUNCA strings.
- Tags en MAYÚSCULAS describiendo el TEMA, no el rol del slide.
- Tono conversacional, útil. Sin frases motivacionales vacías.
- Responde SOLO con el JSON.
"""


def buscar_web(query: str) -> str:
    try:
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        resultados = []
        if data.get("AbstractText"):
            resultados.append(data["AbstractText"])
        for t in data.get("RelatedTopics", [])[:4]:
            if isinstance(t, dict) and t.get("Text"):
                resultados.append(t["Text"])
        return "\n".join(resultados)
    except Exception:
        return ""


def normalizar(datos: dict) -> dict:
    for slide in datos.get("slides", []):
        if slide.get("type") == "features":
            slide["items"] = [
                i if isinstance(i, dict) else {"label": str(i), "description": ""}
                for i in slide.get("items", [])
            ]
        if slide.get("type") == "proof":
            slide["steps"] = [
                s if isinstance(s, dict)
                else {"number": f"0{i+1}", "title": str(s), "description": ""}
                for i, s in enumerate(slide.get("steps", []))
            ]
    return datos


def _llamar_claude(messages: list) -> dict:
    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = cliente.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=messages
    )
    texto = resp.content[0].text.strip()
    if texto.startswith("```"):
        texto = texto.split("```")[1]
        if texto.startswith("json"):
            texto = texto[4:]
    return normalizar(json.loads(texto.strip()))


def generar_desde_texto(prompt: str, plataforma: str = "instagram") -> dict:
    info = PLATFORMS.get(plataforma, PLATFORMS["instagram"])
    web  = buscar_web(prompt)
    contexto = f"\n\nInformación encontrada online:\n{web}" if web else ""
    return _llamar_claude([{"role": "user", "content":
        f"Crea un carrusel para {info['name']} ({info['ratio']}) sobre:\n{prompt}{contexto}"
    }])


def generar_desde_foto(image_bytes: bytes, caption: str, plataforma: str = "instagram") -> dict:
    """Analiza foto con Claude Vision y genera carrusel."""
    if not image_bytes:
        return generar_desde_texto(caption or "carousel", plataforma)

    info = PLATFORMS.get(plataforma, PLATFORMS["instagram"])

    # Detectar formato de imagen
    media_type = "image/jpeg"
    if image_bytes.startswith(b'\x89PNG'):
        media_type = "image/png"
    elif image_bytes.startswith(b'\xff\xd8\xff'):
        media_type = "image/jpeg"
    elif image_bytes.startswith(b'GIF'):
        media_type = "image/gif"

    img_b64 = base64.standard_b64encode(image_bytes).decode()

    try:
        return _llamar_claude([{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
            {"type": "text", "text":
                f"Analiza DETENIDAMENTE esta imagen y crea un carrusel para {info['name']} ({info['ratio']}).\n"
                f"Contexto/solicitud del usuario: {caption or 'Crear contenido basado en la imagen'}\n"
                f"IMPORTANTE: El carrusel DEBE estar diseñado específicamente alrededor de lo que ves en la imagen.\n"
                "Crea contenido profesional, atractivo y relevante a esta imagen específica."
            }
        ]}])
    except Exception as e:
        print(f"[VISION] Error analizando foto: {e}")
        return generar_desde_texto(caption or "carousel", plataforma)
