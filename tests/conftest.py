"""Shared test fixtures and mock provider."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from providers.base import BaseProvider, TextChunk, ToolUseChunk


class MockProvider(BaseProvider):
    """Mock provider that returns controlled responses for testing agent loop."""

    def __init__(self, responses=None, tool_calls=None):
        super().__init__(api_key="mock-key", model="mock-model")
        self.responses = responses or ["Hello, I am a mock agent."]
        self.tool_calls = tool_calls or []
        self._response_idx = 0
        self._tool_idx = 0
        self.call_history = []
        self.last_messages = []
        self.last_tools = []

    def chat(self, messages, tools=None, max_turns=20):
        self.last_messages = messages
        self.last_tools = tools
        self.call_history.append({"messages": messages, "tools": tools})

        if self._tool_idx < len(self.tool_calls):
            tc = self.tool_calls[self._tool_idx]
            self._tool_idx += 1
            yield ToolUseChunk(id=f"tc_{self._tool_idx}", name=tc["name"], params=tc.get("params", {}))
            return

        if self._response_idx < len(self.responses):
            text = self.responses[self._response_idx]
            self._response_idx += 1
            for i in range(0, len(text), 5):
                yield TextChunk(text=text[i:i+5])

    def make_system_message(self, content):
        return {"role": "system", "content": content}

    def make_user_message(self, content):
        return {"role": "user", "content": content}

    def make_assistant_message(self, content):
        return {"role": "assistant", "content": content}

    def make_tool_use_message(self, tool_id, tool_name, params):
        return {"role": "assistant", "content": [{"type": "tool_use", "id": tool_id, "name": tool_name, "input": params}]}

    def make_tool_result_message(self, tool_use_id, content):
        return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content}]}


class MockUI:
    """Mock terminal UI that captures output."""
    def __init__(self):
        self.text_output = []
        self.system_messages = []
        self.tool_calls_shown = []
        self.tool_results = []
        self.permission_requests = []

    def agent_text(self, text):
        self.text_output.append(text)

    def system(self, text):
        self.system_messages.append(text)

    def tool_call(self, name, detail, status):
        self.tool_calls_shown.append((name, detail, status))

    def tool_result(self, summary):
        self.tool_results.append(summary)

    def ask_permission(self, tool_name, detail):
        self.permission_requests.append((tool_name, detail))
        return "y"

    def update_header(self, **kwargs):
        pass


@pytest.fixture
def mock_provider():
    return MockProvider()


@pytest.fixture
def mock_ui():
    return MockUI()


@pytest.fixture
def sample_config():
    from config import Config
    import os
    os.environ["DEEPSEEK_API_KEY"] = "test-key"
    os.environ["MEMORY_SCOPE"] = "workspace"
    c = Config()
    c.working_dir = Path(__file__).parent.parent
    return c


@pytest.fixture
def temp_workspace(tmp_path):
    """Temporary workspace for testing file tools."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "test.txt").write_text("line 1\nline 2\nline 3\n")
    return ws
