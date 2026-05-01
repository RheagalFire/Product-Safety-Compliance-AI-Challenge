from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path(".")
    forbidden_csv: Path = Path("forbidden_ingredients.csv")

    primary_text_model: str = "gemini/gemini-3-flash-preview"  # used by Layer C judge
    # Note: 'gemini-3-flash-preview-lite' was requested but doesn't exist on
    # Google's side; the closest stable preview is 'gemini-3-flash-preview'.
    # The 3.1-flash-lite-preview alternative has a repetition pathology on
    # some inputs (loops on SKU value), so we use the non-lite 3-preview.
    extraction_model: str = "gemini/gemini-3-flash-preview"  # used by LlmSchemaExtractor
    vision_model: str = "gemini/gemini-3-flash-preview"

    gemini_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None

    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    reducto_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None

    exhaustive_match: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
