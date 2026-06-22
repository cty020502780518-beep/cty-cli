"""Provider factory — picks the right provider based on name."""

from .base import BaseProvider
from .anthropic import AnthropicProvider
from .openai_compat import OpenAICompatProvider


def create_provider(name: str, api_key: str, model: str, base_url: str = "") -> BaseProvider:
    """Factory: return the correct provider instance for the given name."""
    if name == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model, base_url=base_url)
    else:
        # OpenAI, DeepSeek, Groq, and any other openai-compatible endpoint
        return OpenAICompatProvider(api_key=api_key, model=model, base_url=base_url)
