"""One place that talks to Ollama.

Every role (patient and interviewer) uses the same settings. Reasoning ("thinking") is switched
off, and as a second safeguard any thinking text that still arrives is removed here, so it can
never reach a transcript or a score. Only the fact that thinking text appeared is recorded.
"""
import re
import time

import httpx
import ollama

SETTINGS = {
    "model": "qwen3:8b",
    "think": False,
    "keep_alive": "30m",
    "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 256},
}

# The gating call returns a short JSON answer, so it gets a smaller output limit; everything else
# (model, thinking off, temperature, seed, context size) is identical.
GATE_SETTINGS = {**SETTINGS, "options": {**SETTINGS["options"], "num_predict": 120}}

_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_UNCLOSED = re.compile(r"<think>.*$", re.DOTALL | re.IGNORECASE)
_ONLY_CLOSING = re.compile(r"^.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> tuple[str, bool]:
    """Remove <think>...</think> text. Returns (clean text, whether any thinking text was found)."""
    found = bool(re.search(r"</?think>", text, re.IGNORECASE))
    text = _BLOCK.sub("", text)
    if re.search(r"</think>", text, re.IGNORECASE):  # closing tag only: everything before it is thinking
        text = _ONLY_CLOSING.sub("", text)
    text = _UNCLOSED.sub("", text)
    return text.strip(), found


def chat(messages: list[dict], *, settings: dict = SETTINGS, client=None, format=None) -> dict:
    """One model call. Returns the clean reply text plus timing and bookkeeping.
    `format` is an optional JSON schema that forces a structured reply (used by the gating step)."""
    client = client or ollama.Client()
    kwargs = dict(model=settings["model"], messages=messages, think=settings["think"],
                  options=settings["options"], keep_alive=settings["keep_alive"], stream=False)
    if format is not None:
        kwargs["format"] = format
    t0 = time.perf_counter()
    resp = client.chat(**kwargs)
    seconds = time.perf_counter() - t0
    msg = resp.message
    text, found = strip_thinking(msg.content or "")
    return {
        "text": text,
        "seconds": round(seconds, 3),
        "think_tags_in_content": found,
        # only whether a separate thinking field came back; its text is never read or stored
        "thinking_field_returned": bool(getattr(msg, "thinking", None)),
        "prompt_tokens": getattr(resp, "prompt_eval_count", None),
        "reply_tokens": getattr(resp, "eval_count", None),
        "done_reason": getattr(resp, "done_reason", None),
    }


def model_info(model: str = SETTINGS["model"], client=None) -> dict:
    """Exactly which model was used: name, digest, size, quantization."""
    client = client or ollama.Client()
    shown = client.show(model)
    listed = next((m for m in client.list().models if m.model == model), None)
    return {
        "model": model,
        "digest": listed.digest if listed else None,
        "size_bytes": listed.size if listed else None,
        "family": shown.details.family,
        "parameter_size": shown.details.parameter_size,
        "quantization": shown.details.quantization_level,
        "format": shown.details.format,
    }


def server_version(host: str = "http://localhost:11434") -> str:
    return httpx.get(f"{host}/api/version", timeout=5).json()["version"]
