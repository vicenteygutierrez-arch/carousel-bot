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

SYSTEM_PROMPT = """Eres un experto en diseño de carruseles profesionales para redes sociales.
Creas contenido visualmente atractivo, de alto engagement y diseñado para convertir.

ESTRUCTURA DEL CARRUSEL (7 slides):
1. HERO: Titular impactante (máx 10 palabras)
2. CONTEXT: Por qué es importante + enganche emocional
3. INSIGHT: El dato o secreto clave + cita destacada
4. FEATURES: 3 puntos principales con descripciones claras
5. DEPTH: Profundización y detalles críticos
6. PROOF: Pasos concretos para aplicar o implementar
7. CTA: Call-to-action claro

Devuelve SOLO JSON válido (sin markdown, sin código):

{
  "idea": "resumen en 1 línea",
  "slides": [
    {"type":"hero","tag":"TEMA CLAVE","heading":"Titular máx 10 palabras","body":""},
    {"type":"context","tag":"CONTEXTO","heading":"Por qué importa","body":"2 oraciones que enganchen"},
    {"type":"insight","tag":"DESCUBRIMIENTO","heading":"El dato clave","body":"Revelación clara","quote":"estadística o cita poderosa"},
    {"type":"features","tag":"BENEFICIOS","heading":"Lo fundamental","items":[{"label":"Punto 1","description":"Explicación clara y concisa"},{"label":"Punto 2","description":"Beneficio específico"},{"label":"Punto 3","description":"Valor agregado"}]},
    {"type":"depth","tag":"PROFUNDIDAD","heading":"El detalle que decide","body":"2-3 oraciones con detalles críticos"},
    {"type":"proof","tag":"APLICAR AHORA","heading":"Cómo implementarlo","steps":[{"number":"01","title":"Primer paso","description":"Acción específica"},{"number":"02","title":"Segundo paso","description":"Siguiente acción"},{"number":"03","title":"Tercer paso","description":"Resultado final"}]},
    {"type":"cta","tag":"¡ACTÚA YA!","heading":"¿Listo para empezar?","body":"Guarda este carrusel y comparte con tu equipo.","cta_text":"COMENTA INFO"}
  ],
  "caption": "Pie conversacional con emojis (máx 100 palabras) que invite a compartir",
  "hashtags": ["#hashtag1","#hashtag2","#hashtag3","#hashtag4","#hashtag5"]
}

REGLAS CRÍTICAS:
✓ Hero: MÁXIMO 10 PALABRAS. Impactante y directo.
✓ Tags: MAYÚSCULAS describiendo el TEMA, no el tipo de slide
✓ items[] y steps[]: SIEMPRE objetos {label/title, description} — NUNCA strings
✓ Contenido: Práctico, específico, sin frases vacías
✓ Tono: Profesional pero conversacional. Que inspire acción.
✓ Responde SOLO el JSON. Nada más.
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
