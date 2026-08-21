from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import ModelError


logger = logging.getLogger(__name__)


class LlmClient:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        if not config.get("hasApiKey"):
            raise ModelError("MODEL_CONFIG_REQUIRED", "请先在模型配置中填写 API Key。")

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_output: bool = False,
        on_delta: Callable[[str], None] | None = None,
    ) -> str:
        """Chat completion with streaming transport (stream=true) whenever enabled.

        ``on_delta`` callers receive each token as it arrives; without it the full
        text is accumulated and returned (used by structured JSON nodes, which must
        not leak raw JSON to the client).
        """
        if self.stream_enabled:
            return self._stream_chat(messages, json_output=json_output, on_delta=on_delta)
        payload = self._payload(messages, json_output=json_output, stream=False)
        last_error: Exception | None = None
        logger.info("LLM chat started provider=%s model=%s stream=false json_output=%s", self.config.get("provider"), self.config.get("modelName"), json_output)
        for attempt in range(settings.model_max_retries + 1):
            try:
                with httpx.Client(timeout=settings.model_timeout_seconds) as client:
                    response = client.post(
                        f"{self.config['baseUrl'].rstrip('/')}/chat/completions", json=payload,
                        headers={"Authorization": f"Bearer {self.config['apiKey']}"},
                    )
                    response.raise_for_status()
                text = str(response.json().get("choices", [{}])[0].get("message", {}).get("content", ""))
                if on_delta and text:
                    on_delta(text)
                logger.info("LLM chat completed provider=%s model=%s attempt=%s", self.config.get("provider"), self.config.get("modelName"), attempt + 1)
                return text
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last_error = exc
                logger.warning(
                    "LLM chat attempt failed provider=%s model=%s attempt=%s max_attempts=%s error=%s",
                    self.config.get("provider"),
                    self.config.get("modelName"),
                    attempt + 1,
                    settings.model_max_retries + 1,
                    describe_error(exc),
                )
                if attempt < settings.model_max_retries: time.sleep(0.4 * (2 ** attempt))
        logger.error("LLM chat failed provider=%s model=%s error=%s", self.config.get("provider"), self.config.get("modelName"), describe_error(last_error))
        raise ModelError("MODEL_CALL_FAILED", f"大模型调用失败：{describe_error(last_error)}")

    def json(self, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        text = self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            json_output=True,
        )
        return parse_json_object(text)

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_output: bool = False,
        on_delta: Callable[[str], None] | None = None,
    ) -> str:
        """Stream tokens to ``on_delta`` (falling back to a single callback when streaming is disabled)."""
        return self.chat(messages, json_output=json_output, on_delta=on_delta)

    def _stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_output: bool,
        on_delta: Callable[[str], None] | None,
    ) -> str:
        """Read Chat Completions SSE (OpenAI / DeepSeek) token by token; accumulate and return full content."""
        payload = self._payload(messages, json_output=json_output, stream=True)
        last_error: Exception | None = None
        logger.info("LLM stream started provider=%s model=%s json_output=%s", self.config.get("provider"), self.config.get("modelName"), json_output)
        for attempt in range(settings.model_max_retries + 1):
            pieces: list[str] = []
            try:
                with httpx.Client(timeout=settings.model_timeout_seconds) as client:
                    with client.stream(
                        "POST",
                        f"{self.config['baseUrl'].rstrip('/')}/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {self.config['apiKey']}"},
                    ) as response:
                        response.raise_for_status()
                        for line in response.iter_lines():
                            line = line.strip()
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            choices = chunk.get("choices") or []
                            delta = (choices[0].get("delta") or {}) if choices else {}
                            content = delta.get("content")
                            if content:
                                pieces.append(content)
                                if on_delta:
                                    on_delta(content)
                logger.info("LLM stream completed provider=%s model=%s attempt=%s", self.config.get("provider"), self.config.get("modelName"), attempt + 1)
                return "".join(pieces)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last_error = exc
                logger.warning(
                    "LLM stream attempt failed provider=%s model=%s attempt=%s max_attempts=%s error=%s",
                    self.config.get("provider"),
                    self.config.get("modelName"),
                    attempt + 1,
                    settings.model_max_retries + 1,
                    describe_error(exc),
                )
                if attempt < settings.model_max_retries:
                    time.sleep(0.4 * (2 ** attempt))
        logger.error("LLM stream failed provider=%s model=%s error=%s", self.config.get("provider"), self.config.get("modelName"), describe_error(last_error))
        raise ModelError("MODEL_CALL_FAILED", f"大模型流式调用失败：{describe_error(last_error)}")

    def stream_json(
        self,
        system: str,
        payload: dict[str, Any],
        *,
        on_delta: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Stream a JSON-object response; callers can progressively extract fields via on_delta."""
        text = self.stream_chat(
            [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            json_output=True,
            on_delta=on_delta,
        )
        return parse_json_object(text)

    @property
    def stream_enabled(self) -> bool:
        return bool(self.config.get("streamEnabled", True))

    def _payload(self, messages: list[dict[str, str]], *, json_output: bool, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config["modelName"], "messages": messages,
            "temperature": float(self.config["temperature"]),
            "max_tokens": int(self.config["maxOutputTokens"]), "stream": stream,
        }
        if json_output and self.config.get("provider") == "openai":
            payload["response_format"] = {"type": "json_object"}
        if self.config.get("provider") == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        return payload


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        if isinstance(value, dict): return value
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            value = json.loads(match.group(0))
            if isinstance(value, dict): return value
        except json.JSONDecodeError:
            pass
    raise ModelError("MODEL_OUTPUT_INVALID", "大模型没有返回合法的结构化 JSON。")


def describe_error(error: Exception | None) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    return str(error or "未知错误")


_ESCAPES = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
_HEX4_RE = re.compile(r"[0-9a-fA-F]{4}")


def extract_json_string_field(buffer: str, field: str) -> str:
    """Progressively decode the string value of a JSON field while the document is still streaming.

    Returns the longest complete (unescaped) prefix available so far; callers only emit the
    newly appended part of each token delta.
    """
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"', buffer)
    if not match:
        return ""
    start = match.end() - 1  # position of the value's opening quote
    index = start + 1
    out: list[str] = []
    while index < len(buffer):
        ch = buffer[index]
        if ch == '"':
            return "".join(out)
        if ch == "\\":
            if index + 1 >= len(buffer):
                break
            escaped = buffer[index + 1]
            if escaped == "u":
                if index + 5 >= len(buffer) or not _HEX4_RE.fullmatch(buffer[index + 2:index + 6]):
                    break
                out.append(chr(int(buffer[index + 2:index + 6], 16)))
                index += 6
            elif escaped in _ESCAPES or escaped in '"\\/':
                out.append(_ESCAPES.get(escaped, escaped))
                index += 2
            else:
                break
        else:
            out.append(ch)
            index += 1
    return "".join(out)
