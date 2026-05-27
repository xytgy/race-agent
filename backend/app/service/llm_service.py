import json
import time
from typing import Any

import requests

from app.config.settings import settings
from app.utils.logger import get_logger


class LLMService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)

    def _build_payload(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": 0.3,
        }

    def chat_messages(self, messages: list[dict[str, str]], request_id: str = "-") -> str:
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(messages)

        last_error: Exception | None = None
        for attempt in range(settings.llm_max_retries + 1):
            started = time.perf_counter()
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=settings.llm_timeout_seconds,
                )
                latency_ms = int((time.perf_counter() - started) * 1000)
                resp.raise_for_status()
                raw = resp.text
                data = resp.json()
                answer = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                self.logger.info(
                    "llm_call",
                    extra={
                        "request_id": request_id,
                        "status_code": resp.status_code,
                        "latency_ms": latency_ms,
                        "attempt": attempt,
                        "llm_raw_output": raw[:2000],
                    },
                )
                return answer or "(empty response)"
            except Exception as exc:
                last_error = exc
                self.logger.error(
                    "llm_call_failed",
                    extra={
                        "request_id": request_id,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )

        raise RuntimeError(f"llm_call_failed: {last_error}")

    def chat(self, message: str, request_id: str = "-") -> str:
        return self.chat_messages([{"role": "user", "content": message}], request_id=request_id)

    def chat_stream(self, messages: list[dict[str, str]], request_id: str = "-"):
        """
        流式输出接口，使用 OpenAI 兼容 API 的 stream=True 参数。
        逐个 yield 每个 token 字符串。
        """
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(messages)
        payload["stream"] = True

        last_error: Exception | None = None
        for attempt in range(settings.llm_max_retries + 1):
            started = time.perf_counter()
            try:
                with requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=settings.llm_timeout_seconds,
                    stream=True,
                ) as resp:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    resp.raise_for_status()
                    # 确保使用 UTF-8 编码，避免中文乱码
                    resp.encoding = 'utf-8'
                    for line in resp.iter_lines(decode_unicode=True):
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[len("data: "):]
                        if data_str.strip() == "[DONE]":
                            self.logger.info(
                                "llm_stream_done",
                                extra={"request_id": request_id, "latency_ms": latency_ms, "attempt": attempt},
                            )
                            return
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                yield token
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
                    return
            except Exception as exc:
                last_error = exc
                self.logger.error(
                    "llm_stream_failed",
                    extra={
                        "request_id": request_id,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
        raise RuntimeError(f"llm_stream_failed: {last_error}")
