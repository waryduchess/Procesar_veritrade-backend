from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mysql_url: str = "mysql+pymysql://veritrade:veritrade123@localhost:3306/veritrade?charset=utf8mb4"
    api_port: int = 8000
    cors_origins: str = ""

    llm_provider: Literal["deepseek", "groq"] = "deepseek"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_thinking: bool = False

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"

    agente_max_tool_calls: int = 4
    agente_max_tokens: int = 700
    agente_timeout: float = 30.0
    agente_top_default: int = 10
    agente_top_max: int = 50

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
