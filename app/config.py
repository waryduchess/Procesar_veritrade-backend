from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "production"] = "local"
    mysql_url: str = "mysql+pymysql://veritrade:veritrade123@localhost:3306/veritrade?charset=utf8mb4"
    api_port: int = 8001
    cors_origins: str = ""

    auth_enabled: bool = False
    jwt_public_key: str = ""
    jwt_public_key_path: str = ""
    jwt_issuer: str = ""
    jwt_audience: str = "compras-api"
    jwt_leeway_seconds: int = 30
    empresa_id: int = 0
    empresa_clave: str = ""

    llm_provider: Literal["deepseek", "groq"] = "deepseek"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_thinking: bool = False

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"

    agente_max_tool_calls: int = 12
    agente_max_tokens: int = 0
    agente_informe_max_tokens: int = 0
    agente_timeout: float = 120.0
    agente_top_default: int = 10
    agente_top_max: int = 50
    agente_historial_mensajes: int = 12
    agente_historial_chars: int = 12000
    agente_historial_resumen_chars: int = 2000

    @model_validator(mode="after")
    def _validar_configuracion_auth(self) -> "Settings":
        if self.app_env == "production" and not self.auth_enabled:
            raise ValueError("AUTH_ENABLED debe ser true cuando APP_ENV=production.")

        if self.auth_enabled:
            if not self.jwt_public_key.strip() and not self.jwt_public_key_path.strip():
                raise ValueError("Configura JWT_PUBLIC_KEY o JWT_PUBLIC_KEY_PATH.")
            if not self.jwt_issuer.strip():
                raise ValueError("Configura JWT_ISSUER.")
            if not self.jwt_audience.strip():
                raise ValueError("Configura JWT_AUDIENCE.")
            if self.empresa_id <= 0:
                raise ValueError("Configura EMPRESA_ID.")
            if not self.empresa_clave.strip():
                raise ValueError("Configura EMPRESA_CLAVE.")

        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
