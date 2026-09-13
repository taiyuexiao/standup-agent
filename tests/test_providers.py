import os
import tempfile
import unittest
from pathlib import Path

from highagent.config import Config, _parse_toml_fallback, default_config_toml, load_config
from highagent.summarizer.providers import (
    PRESETS,
    available_providers,
    get_provider,
)


class ProviderPresetTest(unittest.TestCase):
    def test_three_presets(self):
        self.assertEqual(
            set(PRESETS),
            {"deepseek", "moonshot", "openai"},
        )
        self.assertEqual(PRESETS["deepseek"]["base_url"], "https://api.deepseek.com")
        self.assertEqual(PRESETS["deepseek"]["model"], "deepseek-chat")
        self.assertEqual(PRESETS["deepseek"]["api_key_env"], "DEEPSEEK_API_KEY")
        self.assertEqual(PRESETS["moonshot"]["base_url"], "https://api.moonshot.cn/v1")
        self.assertEqual(PRESETS["moonshot"]["model"], "kimi-k2-0905-preview")
        self.assertEqual(PRESETS["moonshot"]["api_key_env"], "MOONSHOT_API_KEY")
        self.assertEqual(PRESETS["openai"]["base_url"], "https://api.openai.com/v1")
        self.assertEqual(PRESETS["openai"]["model"], "gpt-4o-mini")
        self.assertEqual(PRESETS["openai"]["api_key_env"], "OPENAI_API_KEY")

    def test_default_provider(self):
        p = get_provider()
        self.assertEqual(p.name, "deepseek")
        self.assertEqual(p.base_url, "https://api.deepseek.com")
        self.assertEqual(p.model, "deepseek-chat")
        self.assertEqual(p.api_key_env, "DEEPSEEK_API_KEY")

    def test_config_overrides(self):
        config = Config(
            llm_provider="moonshot",
            llm_model="kimi-k2-turbo-preview",
            llm_base_url="https://example.com/v1",
            llm_api_key_env="MY_KEY",
        )
        p = get_provider(config.llm_provider, config)
        self.assertEqual(p.name, "moonshot")
        self.assertEqual(p.base_url, "https://example.com/v1")
        self.assertEqual(p.model, "kimi-k2-turbo-preview")
        self.assertEqual(p.api_key_env, "MY_KEY")

    def test_unknown_provider_error(self):
        with self.assertRaises(ValueError):
            get_provider("nosuch")

    def test_trailing_slash_stripped(self):
        config = Config(llm_base_url="https://example.com/v1/")
        p = get_provider("deepseek", config)
        self.assertEqual(p.base_url, "https://example.com/v1")


class ConfigLLMFieldsTest(unittest.TestCase):
    def test_old_config_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                'enabled_agents = ["kimi_code"]\nday_start_hour = 0\n', encoding="utf-8"
            )
            config = load_config(path)
            self.assertEqual(config.llm_provider, "deepseek")
            self.assertEqual(config.llm_model, "")
            self.assertEqual(config.llm_base_url, "")
            self.assertEqual(config.llm_api_key_env, "")
            p = get_provider(config.llm_provider, config)
            self.assertEqual(p.base_url, PRESETS["deepseek"]["base_url"])
            self.assertEqual(p.model, PRESETS["deepseek"]["model"])

    def test_new_fields_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                'llm_provider = "moonshot"\n'
                'llm_model = "kimi-k2-turbo-preview"\n'
                'llm_base_url = "https://api.moonshot.cn/v1"\n'
                'llm_api_key_env = "MOONSHOT_API_KEY"\n',
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(config.llm_provider, "moonshot")
            self.assertEqual(config.llm_model, "kimi-k2-turbo-preview")
            self.assertEqual(config.llm_api_key_env, "MOONSHOT_API_KEY")

    def test_inline_comment_fallback(self):
        data = _parse_toml_fallback(
            'llm_provider = "moonshot"  # 行内注释\n'
            'llm_base_url = "https://a.com/#/v1"\n'
            "day_start_hour = 3 # 注释\n"
        )
        self.assertEqual(data["llm_provider"], "moonshot")
        self.assertEqual(data["llm_base_url"], "https://a.com/#/v1")
        self.assertEqual(data["day_start_hour"], 3)

    def test_default_config_toml_roundtrip(self):
        data = _parse_toml_fallback(default_config_toml())
        self.assertEqual(data["llm_provider"], "deepseek")
        self.assertNotIn("llm_model", data)


class ApiKeyResolutionTest(unittest.TestCase):
    def test_env_name_follows_config(self):
        os.environ.pop("MY_CUSTOM_KEY", None)
        config = Config(llm_api_key_env="MY_CUSTOM_KEY")
        p = get_provider("deepseek", config)
        self.assertEqual(p.api_key_env, "MY_CUSTOM_KEY")
        self.assertEqual(p.api_key, "")
        os.environ["MY_CUSTOM_KEY"] = "sk-test-value"
        try:
            p2 = get_provider("deepseek", config)
            self.assertEqual(p2.api_key, "sk-test-value")
        finally:
            del os.environ["MY_CUSTOM_KEY"]


if __name__ == "__main__":
    unittest.main()
