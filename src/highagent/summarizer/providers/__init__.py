from __future__ import annotations

from highagent.summarizer.providers.base import LLMError, LLMProvider
from highagent.summarizer.providers.openai_compat import PRESETS, OpenAICompatProvider

DEFAULT_PROVIDER = "deepseek"


def available_providers() -> list:
    return sorted(PRESETS)


def get_provider(name: str = None, config=None) -> LLMProvider:
    name = name or DEFAULT_PROVIDER
    if name not in PRESETS:
        raise ValueError(
            "未知的 LLM provider: %s（当前预设: %s；也可用 llm_base_url 指向任意 OpenAI 兼容端点）"
            % (name, ", ".join(available_providers()))
        )
    preset = dict(PRESETS[name])
    if config is not None:
        if getattr(config, "llm_base_url", None):
            preset["base_url"] = config.llm_base_url
        if getattr(config, "llm_model", None):
            preset["model"] = config.llm_model
        if getattr(config, "llm_api_key_env", None):
            preset["api_key_env"] = config.llm_api_key_env
    return OpenAICompatProvider(name=name, **preset)
