import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")
    return value


def _csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class Settings:
    def __init__(self) -> None:
        self.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.embedding_provider = os.getenv("EMBEDDING_PROVIDER", "dashscope").lower()
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
        self.qwen_base_url = os.getenv(
            "QWEN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.qwen_model = os.getenv("QWEN_MODEL", "qwen-plus")
        self.upload_max_bytes = _positive_int("UPLOAD_MAX_BYTES", 50 * 1024 * 1024)
        self.llm_timeout_seconds = _positive_int("LLM_TIMEOUT_SECONDS", 60)
        self.history_max_messages = _positive_int("HISTORY_MAX_MESSAGES", 20)
        self.history_max_chars = _positive_int("HISTORY_MAX_CHARS", 16_000)
        self.embedding_batch_size = _positive_int("EMBEDDING_BATCH_SIZE", 10)
        self.cors_origins = _csv(
            "CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        )


settings = Settings()
