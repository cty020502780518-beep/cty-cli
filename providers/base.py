"""Provider abstraction layer — unified interface over Anthropic / OpenAI / DeepSeek.

将不同 LLM 提供商的 streaming 响应归一化为统一的 Chunk 类型，
agent loop 不需要知道底层是谁。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Optional, Union


@dataclass
class TextChunk:
    text: str


@dataclass
class ToolUseChunk:
    id: str
    name: str
    params: dict  # 已聚合完成的完整参数


@dataclass
class ToolResult:
    tool_use_id: str
    content: str


# Chunk = 流式输出的最小单元
Chunk = Union[TextChunk, ToolUseChunk]


class BaseProvider(ABC):
    """所有 provider 的统一接口。

    核心设计决策：
    - chat() 返回 Iterator[Chunk]，下游统一消费
    - 各子类负责将原生 streaming 格式转成标准 Chunk
    - Anthropic 的 content_block_start/delta/stop 和 OpenAI 的
      chat.completions.chunk 都被屏蔽在这一层之下
    """

    def __init__(self, api_key: str, model: str, base_url: str = ""):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        tools: Optional[list] = None,
        max_turns: int = 20,
    ) -> Iterator[Chunk]:
        """Send messages + tools, yield normalized Chunks."""
        ...

    @abstractmethod
    def make_system_message(self, content: str) -> dict:
        """Each provider has its own system-message format."""
        ...

    @abstractmethod
    def make_user_message(self, content: str) -> dict:
        ...

    @abstractmethod
    def make_assistant_message(self, content: str) -> dict:
        ...

    @abstractmethod
    def make_tool_use_message(self, tool_id: str, tool_name: str, params: dict) -> dict:
        """Build an assistant message containing a tool call."""
        ...

    @abstractmethod
    def make_tool_result_message(self, tool_use_id: str, content: str) -> dict:
        ...

    def supports_thinking(self) -> bool:
        return False
