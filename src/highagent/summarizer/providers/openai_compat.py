from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from highagent.config import ENV_PATH, read_env_file
from highagent.summarizer.providers.base import LLMError, LLMProvider

TIMEOUT_SECONDS = 120

PRESETS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k2-0905-preview",
        "api_key_env": "MOONSHOT_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
    },
}


class OpenAICompatProvider(LLMProvider):
    """OpenAI 兼容 /chat/completions 端点（DeepSeek/Moonshot/OpenAI 等同一协议）。"""

    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key_env: str,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.api_key = os.environ.get(api_key_env, "").strip() or read_env_file().get(
            api_key_env, ""
        ).strip()

    def complete_json(self, system: str, user: str) -> dict:
        if not self.api_key:
            raise LLMError(
                "未找到 %s 的 API key：请设置环境变量 %s，或将 %s=<key> 写入 %s（权限 0600）。"
                "也可使用 --dry-run 跳过 LLM 调用。"
                % (self.name, self.api_key_env, self.api_key_env, ENV_PATH)
            )
        last_error = None
        for attempt in (1, 2):
            try:
                return self._request_json(system, user)
            except LLMError as exc:
                last_error = exc
                if "不是合法 JSON" not in str(exc):
                    raise
        raise last_error

    def _request_json(self, system: str, user: str) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": 8000,
            "stream": False,
        }
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            if exc.code in (401, 403):
                raise LLMError(
                    "%s 鉴权失败（HTTP %s）：请检查环境变量 %s 是否有效。"
                    % (self.name, exc.code, self.api_key_env)
                ) from exc
            raise LLMError(
                "%s 请求失败（HTTP %s）：%s" % (self.name, exc.code, detail)
            ) from exc
        except urllib.error.URLError as exc:
            raise LLMError(
                "无法连接 %s（%s）：请检查网络。" % (self.name, exc.reason)
            ) from exc
        except TimeoutError as exc:
            raise LLMError(
                "%s 请求超时（%ds）。" % (self.name, TIMEOUT_SECONDS)
            ) from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("%s 返回格式异常：%s" % (self.name, str(body)[:300])) from exc
        if self.api_key:
            content = content.replace(self.api_key, "***")
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content[:4].lower() == "json":
                content = content[4:]
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(
                "%s 返回的内容不是合法 JSON：%s" % (self.name, content[:300])
            ) from exc
