from typing import Any

from fastapi import HTTPException, status
from openai import APIConnectionError, APIStatusError, OpenAI

from app.core.config import settings


class QwenLLMService:
    def __init__(self) -> None:
        self.model = settings.qwen_model
        self.base_url = settings.qwen_base_url
        self.api_key = settings.dashscope_api_key
        self.client: OpenAI | None = None
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        if self.client is None or not self.api_key or self.api_key == "your_dashscope_api_key":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="DASHSCOPE_API_KEY is not configured. Please set it in backend/.env.",
            )

        try:
            response = self.client.chat.completions.create(
                model=model or self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
            )
        except APIStatusError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Qwen API error: {exc.status_code} {exc.message}",
            ) from exc
        except APIConnectionError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not connect to Qwen API: {exc}",
            ) from exc

        usage = response.usage.model_dump() if response.usage else None
        return {
            "content": response.choices[0].message.content or "",
            "usage": usage,
        }


llm_service = QwenLLMService()
