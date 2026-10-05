import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv(override=True)  # o .env do projeto tem prioridade sobre variáveis do sistema

OPENROUTER_URL = "https://openrouter.ai/api/v1"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OPENROUTER_DEFAULT_MODELS = (
    "openrouter/free,nvidia/nemotron-3.5-lightning:free,"
    "z-ai/glm-5.2:free,google/gemma-4-26b-a4b-it:free"
)


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    models: list[str]


def _split(value: str) -> list[str]:
    return [m.strip() for m in value.split(",") if m.strip()]


def build_providers() -> list[Provider]:
    """Provedores na ordem de LLM_PROVIDERS; só entram os que têm chave. A ordem é o fallback."""
    catalog = {
        "gemini": Provider("gemini", GEMINI_URL, os.getenv("GEMINI_API_KEY", ""),
                           _split(os.getenv("GEMINI_MODELS", "gemini-2.5-flash"))),
        "openrouter": Provider("openrouter", OPENROUTER_URL, os.getenv("OPENROUTER_API_KEY", ""),
                               _split(os.getenv("OPENROUTER_MODELS", OPENROUTER_DEFAULT_MODELS))),
    }
    order = _split(os.getenv("LLM_PROVIDERS", "gemini,openrouter"))
    return [catalog[n] for n in order if n in catalog and catalog[n].api_key]


@dataclass
class Settings:
    providers: list[Provider] = field(default_factory=build_providers)
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "cinerocket.db"))
    query_timeout: int = field(default_factory=lambda: int(os.getenv("QUERY_TIMEOUT", "60")))  # segundos por SQL
    max_steps: int = 4          # máx. de chamadas ao LLM por pergunta
    max_rows_to_llm: int = 50   # linhas devolvidas ao modelo
    max_rows_query: int = 500   # LIMIT de segurança
    cache_path: str = ".cache/answers.json"
