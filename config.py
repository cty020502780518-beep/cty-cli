"""Config management — model/provider switching, .env loading.

对应 Claude Code 的 settings.json + cc switch 机制。
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    env_key: str
    default_model: str
    models: list[str] = field(default_factory=list)


# 预定义 provider 注册表
PROVIDER_PRESETS: dict[str, ProviderConfig] = {
    "deepseek": ProviderConfig(
        name="deepseek",
        base_url="https://api.deepseek.com",
        env_key="DEEPSEEK_API_KEY",
        default_model="deepseek-v4-pro",
        models=["deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
    ),
    "anthropic": ProviderConfig(
        name="anthropic",
        base_url="https://api.anthropic.com",
        env_key="ANTHROPIC_API_KEY",
        default_model="claude-sonnet-4-6-20250514",
        models=[
            "claude-sonnet-4-6-20250514",
            "claude-opus-4-7-20251101",
            "claude-haiku-4-5-20251001",
        ],
    ),
    "openai": ProviderConfig(
        name="openai",
        base_url="https://api.openai.com/v1",
        env_key="OPENAI_API_KEY",
        default_model="gpt-4o",
        models=["gpt-4o", "gpt-4o-mini", "o4-mini"],
    ),
}


class Config:
    """Runtime configuration, mutable — supports /model /provider at runtime."""

    def __init__(self):
        load_dotenv()

        self.provider_name = os.getenv("DEFAULT_PROVIDER", "deepseek")
        self.model = os.getenv("DEFAULT_MODEL", "")
        self.working_dir = Path.cwd()

        # Resolve provider
        if self.provider_name not in PROVIDER_PRESETS:
            print(f"Unknown provider '{self.provider_name}', falling back to deepseek")
            self.provider_name = "deepseek"

        self._provider = PROVIDER_PRESETS[self.provider_name]
        if not self.model:
            self.model = self._provider.default_model

    @property
    def provider(self) -> ProviderConfig:
        return self._provider

    @property
    def api_key(self) -> str:
        return os.getenv(self._provider.env_key, "")

    def get_api_key(self) -> str:
        key = self.api_key
        if not key:
            raise RuntimeError(
                f"Missing API key. Set {self._provider.env_key} in .env or environment.\n"
                f"  Example .env line: {self._provider.env_key}=sk-..."
            )
        return key

    def switch_provider(self, name: str) -> str:
        """Switch provider and auto-select its default model."""
        if name not in PROVIDER_PRESETS:
            return f"Unknown provider: {name}. Available: {', '.join(PROVIDER_PRESETS)}"
        old = self.provider_name
        self.provider_name = name
        self._provider = PROVIDER_PRESETS[name]
        self.model = self._provider.default_model
        return f"Provider: {old} → {name}\nModel: → {self.model}"

    def switch_model(self, model: str) -> str:
        """Switch model within current provider. Accepts partial match."""
        # Exact match first
        if model in self._provider.models:
            old = self.model
            self.model = model
            return f"Model: {old} → {model}"

        # Fuzzy match
        matches = [m for m in self._provider.models if model.lower() in m.lower()]
        if len(matches) == 1:
            old = self.model
            self.model = matches[0]
            return f"Model: {old} → {matches[0]}"
        elif matches:
            return f"Ambiguous. Did you mean: {', '.join(matches)}?"
        else:
            return f"Model '{model}' not found in provider '{self.provider_name}'.\nAvailable: {', '.join(self._provider.models)}"

    def list_providers(self) -> str:
        lines = ["Available providers:"]
        for name, pc in PROVIDER_PRESETS.items():
            marker = " ● (current)" if name == self.provider_name else ""
            lines.append(f"  {name}{marker}  ({len(pc.models)} models, key={pc.env_key})")
        return "\n".join(lines)

    def list_models(self, provider_name: Optional[str] = None) -> str:
        pc = PROVIDER_PRESETS.get(provider_name or self.provider_name, self._provider)
        lines = [f"Models for {pc.name}:"]
        for m in pc.models:
            marker = " ● (current)" if m == self.model and pc.name == self.provider_name else ""
            lines.append(f"  {m}{marker}")
        return "\n".join(lines)

    def summary(self) -> str:
        return (
            f"Provider: {self.provider_name} | Model: {self.model} | "
            f"Working dir: {self.working_dir}"
        )
