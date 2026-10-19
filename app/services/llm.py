from functools import lru_cache

from groq import Groq

from app.config import settings


class LLMNoConfigurado(RuntimeError):
    pass


@lru_cache(maxsize=1)
def cliente() -> Groq:
    if not settings.groq_api_key:
        raise LLMNoConfigurado("GROQ_API_KEY no está configurada en .env")
    return Groq(api_key=settings.groq_api_key, timeout=settings.agente_timeout)


def disponible() -> bool:
    return bool(settings.groq_api_key)
