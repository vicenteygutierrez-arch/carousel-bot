import os
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY)

def transcribir_audio(audio_bytes: bytes) -> str:
    """Transcribe audio bytes usando OpenAI Whisper."""
    try:
        with open("/tmp/audio.ogg", "wb") as f:
            f.write(audio_bytes)
        with open("/tmp/audio.ogg", "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=f
            )
        return result.text.strip()
    except Exception as e:
        print(f"[WHISPER] Error: {e}")
        return ""
