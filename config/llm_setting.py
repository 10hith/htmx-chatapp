"""
LLM settings for the HTMX chat app.

Adapted from OrdeloAgent's config/llm_setting.py, but with the AWS Secrets Manager
dependency removed: secrets come from a local `.env` file via pydantic-settings.
Field aliases (`llm_model`, `llm_openai_api_key`) match the OrdeloAgent convention.
"""

from __future__ import annotations

from functools import cached_property

from langchain_openai import ChatOpenAI
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    model: str = Field("gpt-4o-mini", alias="llm_model")
    openai_api_key: str = Field(..., alias="llm_openai_api_key")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @cached_property
    def llm_client(self) -> ChatOpenAI:
        """ChatOpenAI instance passed directly to create_deep_agent(model=...).

        deepagents 0.6.12 accepts `str | BaseChatModel`, so handing it this
        instance preserves temperature / retry config (verified in the spike).
        """
        return ChatOpenAI(
            model=self.model,
            openai_api_key=self.openai_api_key,
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
        )


llm_settings = LLMSettings()  # reads .env at import; requires llm_openai_api_key
