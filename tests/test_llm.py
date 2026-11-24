from types import SimpleNamespace as NS

from src import llm


class FakeClient:
    """Stands in for Ollama and records what it was asked."""

    def __init__(self, content, thinking=None):
        self.content, self.thinking, self.calls = content, thinking, []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return NS(message=NS(content=self.content, thinking=self.thinking),
                  prompt_eval_count=10, eval_count=5, done_reason="stop")


def test_strip_closed_block():
    assert llm.strip_thinking("<think>plan</think>Hello") == ("Hello", True)


def test_strip_unclosed_block():
    assert llm.strip_thinking("Hello <think>plan that never ends") == ("Hello", True)


def test_strip_closing_tag_only():
    assert llm.strip_thinking("plan text</think>Hello") == ("Hello", True)


def test_plain_text_is_untouched():
    assert llm.strip_thinking("Just a reply.") == ("Just a reply.", False)


def test_thinking_text_never_comes_back_from_chat():
    client = FakeClient("<think>SECRET_TAG_TEXT</think>Fine.", thinking="SECRET_FIELD_TEXT")
    result = llm.chat([{"role": "user", "content": "hi"}], client=client)
    assert result["text"] == "Fine."
    assert "SECRET" not in repr(result)
    assert result["think_tags_in_content"] is True
    assert result["thinking_field_returned"] is True  # recorded as a flag only


def test_chat_switches_thinking_off_and_fixes_the_sampling_settings():
    client = FakeClient("ok")
    llm.chat([{"role": "user", "content": "hi"}], client=client)
    call = client.calls[0]
    assert call["think"] is False
    assert call["model"] == "qwen3:8b"
    assert call["options"]["temperature"] == 0
    assert call["options"]["seed"] == 42
