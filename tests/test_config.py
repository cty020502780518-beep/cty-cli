"""Tests for config.py — provider/model switching."""
import os
from pathlib import Path

import pytest
from config import Config, ProviderConfig, PROVIDER_PRESETS


class TestProviderPresets:
    def test_deepseek_preset(self):
        assert "deepseek" in PROVIDER_PRESETS
        pc = PROVIDER_PRESETS["deepseek"]
        assert pc.name == "deepseek"
        assert pc.base_url == "https://api.deepseek.com"
        assert pc.env_key == "DEEPSEEK_API_KEY"
        assert pc.default_model == "deepseek-v4-pro"

    def test_anthropic_preset(self):
        assert "anthropic" in PROVIDER_PRESETS
        pc = PROVIDER_PRESETS["anthropic"]
        assert pc.name == "anthropic"
        assert "claude" in pc.models[0].lower()

    def test_openai_preset(self):
        assert "openai" in PROVIDER_PRESETS
        pc = PROVIDER_PRESETS["openai"]
        assert "gpt" in pc.default_model


class TestConfig:
    def test_default_provider(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        config = Config()
        assert config.provider_name in PROVIDER_PRESETS

    def test_switch_provider(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        os.environ["ANTHROPIC_API_KEY"] = "test-key-ant"
        config = Config()
        result = config.switch_provider("anthropic")
        assert "anthropic" in result
        assert config.provider_name == "anthropic"

    def test_switch_unknown_provider(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        config = Config()
        result = config.switch_provider("nonexistent")
        assert "Unknown" in result

    def test_switch_model_exact(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        config = Config()
        config.switch_provider("deepseek")
        result = config.switch_model("deepseek-chat")
        assert "deepseek-chat" in result

    def test_switch_model_fuzzy(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        config = Config()
        config.switch_provider("deepseek")
        result = config.switch_model("chat")
        assert "deepseek-chat" in result

    def test_switch_model_not_found(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        config = Config()
        config.switch_provider("deepseek")
        result = config.switch_model("nonexistent-model-xyz")
        assert "not found" in result

    def test_list_providers(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        config = Config()
        result = config.list_providers()
        assert "deepseek" in result
        assert "anthropic" in result
        assert "openai" in result

    def test_list_models(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        config = Config()
        config.switch_provider("deepseek")
        result = config.list_models()
        assert "deepseek-v4-pro" in result

    def test_summary(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        config = Config()
        result = config.summary()
        assert "Provider" in result
        assert "Model" in result

    def test_missing_api_key(self):
        # Temporarily move .env out of the way
        import shutil
        env_path = Path(__file__).parent.parent / ".env"
        env_bak = Path(__file__).parent.parent / ".env.test_bak"
        if env_path.exists():
            shutil.move(str(env_path), str(env_bak))
        try:
            os.environ.pop("DEEPSEEK_API_KEY", None)
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            from config import Config as Cfg2
            c = Cfg2()
            with pytest.raises(RuntimeError, match="Missing API key"):
                c.get_api_key()
        finally:
            if env_bak.exists():
                shutil.move(str(env_bak), str(env_path))

    def test_memory_scope_default(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        config = Config()
        assert config.memory_scope == "workspace"

    def test_memory_scope_from_env(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        os.environ["MEMORY_SCOPE"] = "global"
        config = Config()
        assert config.memory_scope == "global"
        os.environ["MEMORY_SCOPE"] = "workspace"
