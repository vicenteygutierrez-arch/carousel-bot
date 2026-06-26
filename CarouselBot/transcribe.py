"""
transcribe.py — Transcripción de audio con OpenAI Whisper.
"""
import os
import tempfile
from pathlib import Path
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def transcribir_audio(audio_bytes: bytes, extension: str = "ogg") -> str:
    cliente = OpenAI(api_key=OPENAI_API_KEY)
    with tempfile.NamedTemporaryFile(suffix=f".{extension}", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            resultado = cliente.audio.transcriptions.create(
                model="whisper-1", file=f, language="es"
            )
        return resultado.text
    finally:
        tmp_path.unlink(missing_ok=True)
