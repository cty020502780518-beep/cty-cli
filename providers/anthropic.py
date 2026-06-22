"""Anthropic native provider — Messages API with tool_use.

Claude's native format has tool_use blocks in the content array alongside text blocks.
The streaming protocol sends content_block_start/delta/stop events that we reassemble
into complete ToolUseChunks.
"""
import json
from typing import Iterator, Optional

from anthropic import Anthropic
from anthropic.types import MessageStreamEvent

from .base import BaseProvider, Chunk, TextChunk, ToolUseChunk


class AnthropicProvider(BaseProvider):
    def __init__(self, api_key: str, model: str, base_url: str = ""):
        super().__init__(api_key, model, base_url)
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = Anthropic(**kwargs)

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list] = None,
        max_turns: int = 20,
    ) -> Iterator[Chunk]:
        # Convert tools to Anthropic format
        anthropic_tools = None
        if tools:
            anthropic_tools = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("input_schema", {"type": "object", "properties": {}}),
                }
                for t in tools
            ]

        # Separate system from messages
        system_msg = ""
        chat_messages: list[dict] = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg += ("\n\n" if system_msg else "") + (
                    msg["content"] if isinstance(msg["content"], str) else str(msg["content"])
                )
            else:
                chat_messages.append(msg)

        kwargs = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": 8192,
            "stream": True,
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
        if system_msg:
            kwargs["system"] = system_msg

        # Streaming read loop
        stream = self.client.messages.create(**kwargs)

        # State for rebuilding tool_use blocks
        current_tool_id: Optional[str] = None
        current_tool_name: Optional[str] = None
        current_tool_input: str = ""

        for event in stream:
            if event.type == "content_block_delta":
                delta = event.delta
                if delta.type == "text_delta":
                    yield TextChunk(text=delta.text)
                elif delta.type == "input_json_delta":
                    current_tool_input += delta.partial_json

            elif event.type == "content_block_start":
                block = event.content_block
                if block.type == "tool_use":
                    current_tool_id = block.id
                    current_tool_name = block.name
                    current_tool_input = ""

            elif event.type == "content_block_stop":
                if current_tool_id is not None and current_tool_input:
                    try:
                        params = json.loads(current_tool_input)
                    except json.JSONDecodeError:
                        params = {"_raw": current_tool_input}
                    yield ToolUseChunk(
                        id=current_tool_id,
                        name=current_tool_name or "unknown",
                        params=params,
                    )
                    current_tool_id = None
                    current_tool_name = None
                    current_tool_input = ""

    def make_system_message(self, content: str) -> dict:
        return {"role": "system", "content": content}

    def make_user_message(self, content: str) -> dict:
        return {"role": "user", "content": content}

    def make_assistant_message(self, content: str) -> dict:
        return {"role": "assistant", "content": content}

    def make_tool_use_message(self, tool_id: str, tool_name: str, params: dict) -> dict:
        return {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": tool_id, "name": tool_name, "input": params}
            ],
        }

    def make_tool_result_message(self, tool_use_id: str, content: str) -> dict:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                }
            ],
        }

    def supports_thinking(self) -> bool:
        return True
