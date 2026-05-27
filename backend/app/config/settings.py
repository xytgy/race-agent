from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 2
    embedding_model: str
    data_dir: str
    api_key: str

    model_config = ConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8")

    @property
    def log_dir(self) -> str:
        return f"{self.data_dir}/logs"


settings = Settings()
