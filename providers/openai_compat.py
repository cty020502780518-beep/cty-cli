"""OpenAI-compatible provider — covers OpenAI, DeepSeek, Groq, etc.

These APIs use the chat.completions endpoint with function-calling (tools).
The streaming format has delta.tool_calls fragments that we reassemble
and convert into our standard ToolUseChunk.
"""
import json
from typing import Iterator, Optional

from openai import OpenAI

from .base import BaseProvider, Chunk, TextChunk, ToolUseChunk


class OpenAICompatProvider(BaseProvider):
    """Works with: DeepSeek, OpenAI, Groq, and any /v1/chat/completions endpoint."""

    def __init__(self, api_key: str, model: str, base_url: str = ""):
        super().__init__(api_key, model, base_url)
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url.rstrip("/")
        self.client = OpenAI(**kwargs)
        self._is_deepseek = "deepseek" in base_url.lower()
        self._last_response_msg: Optional[dict] = None  # Preserve thinking content
        self._pending_reasoning: Optional[str] = None   # reasoning_content for multi-tool turns

    @staticmethod
    def _sanitize_str(text: str) -> str:
        """Replace lone surrogates that break JSON serialization and UTF-8 output."""
        if not text:
            return text
        return text.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert our internal tool schema to OpenAI function-calling format."""
        openai_tools = []
        for t in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            })
        return openai_tools

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list] = None,
        max_turns: int = 20,
    ) -> Iterator[Chunk]:
        # Clear stale reasoning_content from previous response
        self._pending_reasoning = None
        self._last_response_msg = None

        # Convert messages to OpenAI format, sanitizing all strings
        openai_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")

            if role == "system":
                openai_messages.append({"role": "system", "content": self._sanitize_str(content) if isinstance(content, str) else content})
            elif role == "user":
                if isinstance(content, list):
                    openai_messages.append(msg)
                else:
                    openai_messages.append({"role": "user", "content": self._sanitize_str(content) if isinstance(content, str) else content})
            elif role == "tool":
                if isinstance(msg.get("content"), str):
                    msg = dict(msg)
                    msg["content"] = self._sanitize_str(msg["content"])
                openai_messages.append(msg)
            elif role == "assistant":
                if "tool_calls" in msg:
                    openai_messages.append(msg)
                elif isinstance(content, list):
                    openai_messages.append(msg)
                elif isinstance(content, str):
                    openai_messages.append({"role": "assistant", "content": self._sanitize_str(content)})

        use_stream = not bool(tools)  # DeepSeek streaming + tools is unreliable

        kwargs: dict = {
            "model": self.model,
            "messages": openai_messages,
            "stream": use_stream,
            "max_tokens": 8192,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        if use_stream:
            stream = self.client.chat.completions.create(**kwargs)
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue
                if delta.content:
                    yield TextChunk(text=delta.content)
            return

        # Non-streaming path (for reliable tool use with DeepSeek)
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        # Preserve full message for reasoning_content passthrough (DeepSeek thinking mode)
        self._last_response_msg = {"role": "assistant"}
        if msg.content:
            self._last_response_msg["content"] = self._sanitize_str(msg.content)
        if hasattr(msg, "reasoning_content") and msg.reasoning_content:
            self._last_response_msg["reasoning_content"] = self._sanitize_str(msg.reasoning_content)
        if msg.tool_calls:
            self._last_response_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]

        # Yield text first
        if msg.content:
            sanitized = self._sanitize_str(msg.content)
            for i in range(0, len(sanitized), 10):
                yield TextChunk(text=sanitized[i:i+10])

        # Yield tool calls
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    params = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    params = {"_raw": tc.function.arguments}
                yield ToolUseChunk(
                    id=tc.id,
                    name=tc.function.name,
                    params=params,
                )

    def make_system_message(self, content: str) -> dict:
        return {"role": "system", "content": content}

    def make_user_message(self, content: str) -> dict:
        return {"role": "user", "content": content}

    def make_assistant_message(self, content: str) -> dict:
        # Carry over reasoning_content from last response (DeepSeek thinking mode)
        if self._last_response_msg and self._last_response_msg.get("content") == content:
            msg = dict(self._last_response_msg)
            self._last_response_msg = None
            self._pending_reasoning = None
            return msg
        msg = {"role": "assistant", "content": self._sanitize_str(content)}
        if self._pending_reasoning:
            msg["reasoning_content"] = self._pending_reasoning
            self._pending_reasoning = None
        return msg

    def make_tool_use_message(self, tool_id: str, tool_name: str, params: dict) -> dict:
        import json
        # If _last_response_msg has exactly one tool_call matching this one,
        # use it to carry over reasoning_content (DeepSeek thinking mode).
        if self._last_response_msg:
            preserved_tool_calls = self._last_response_msg.get("tool_calls", [])
            if len(preserved_tool_calls) == 1 and preserved_tool_calls[0]["id"] == tool_id:
                msg = dict(self._last_response_msg)
                self._last_response_msg = None
                self._pending_reasoning = None
                return msg
            # Multiple tool_calls — extract reasoning_content for reuse across all tools
            if "reasoning_content" in self._last_response_msg:
                self._pending_reasoning = self._last_response_msg["reasoning_content"]
            self._last_response_msg = None

        # Build clean single-tool message
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(params, ensure_ascii=False),
                    },
                }
            ],
        }
        if self._pending_reasoning:
            msg["reasoning_content"] = self._pending_reasoning
        return msg

    def make_tool_result_message(self, tool_use_id: str, content: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_use_id,
            "content": content,
        }
