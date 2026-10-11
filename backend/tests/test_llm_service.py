import pytest
from app.core.config import is_api_key_configured, settings
from app.services.llm_service import QwenLLMService
from fastapi import HTTPException


def test_placeholder_and_empty_keys_count_as_unconfigured() -> None:
    assert is_api_key_configured("") is False
    assert is_api_key_configured(None) is False
    assert is_api_key_configured("your_dashscope_api_key") is False
    assert is_api_key_configured("prefix-your_dashscope_api_key-suffix") is False
    assert is_api_key_configured("sk-real-key") is True


def test_placeholder_key_creates_no_client_and_answers_503(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dashscope_api_key", "your_dashscope_api_key")
    service = QwenLLMService()

    assert service.client is None
    assert service.available is False

    with pytest.raises(HTTPException) as excinfo:
        service.chat("system", "user")

    assert excinfo.value.status_code == 503


def test_missing_key_answers_503(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dashscope_api_key", "")
    service = QwenLLMService()

    assert service.available is False

    with pytest.raises(HTTPException) as excinfo:
        service.chat("system", "user")

    assert excinfo.value.status_code == 503
