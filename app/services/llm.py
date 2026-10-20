from functools import lru_cache

from openai import OpenAI

from app.config import settings


class LLMNoConfigurado(RuntimeError):
    pass


def _config() -> tuple[str, str, str]:
    if settings.llm_provider == "groq":
        return settings.groq_api_key, settings.groq_base_url, settings.groq_model
    return settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model


def variable_api_key() -> str:
    return "GROQ_API_KEY" if settings.llm_provider == "groq" else "DEEPSEEK_API_KEY"


@lru_cache(maxsize=1)
def cliente() -> OpenAI:
    api_key, base_url, _ = _config()
    if not api_key:
        raise LLMNoConfigurado(f"{variable_api_key()} no está configurada en .env")
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=settings.agente_timeout,
    )


def disponible() -> bool:
    return bool(_config()[0])


def modelo() -> str:
    return _config()[2]


def opciones() -> dict:
    if settings.llm_provider == "deepseek" and not settings.deepseek_thinking:
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {}
