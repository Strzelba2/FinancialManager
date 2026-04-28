from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from openai import APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import ValidationError

from app.core.config import settings

from .ai_schema import EquityAiPayload


logger = logging.getLogger(__name__)


class OpenAIReportError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAIReportResult:
    payload: EquityAiPayload
    model: str
    usage_prompt_tokens: int | None
    usage_output_tokens: int | None


def _response_debug_summary(response: Any) -> str:
    status = getattr(response, "status", None)
    incomplete_details = getattr(response, "incomplete_details", None)
    error = getattr(response, "error", None)
    output_summary: list[str] = []

    for idx, item in enumerate(getattr(response, "output", []) or []):
        item_type = getattr(item, "type", None)
        item_status = getattr(item, "status", None)
        content_types: list[str] = []
        for content in getattr(item, "content", []) or []:
            content_types.append(str(getattr(content, "type", None)))
        output_summary.append(
            f"{idx}:{item_type}:{item_status}:{','.join(content_types) if content_types else '-'}"
        )

    return (
        f"status={status}, incomplete_details={incomplete_details}, "
        f"error={error}, output={output_summary}"
    )


def _extract_refusal(response: Any) -> str | None:
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            if getattr(content, "type", None) == "refusal":
                refusal = getattr(content, "refusal", None) or getattr(content, "text", None)
                return str(refusal or "Model refusal")
    return None


def _extract_usage(response: Any) -> tuple[int | None, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None
    return getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)


def _is_likely_truncated_json_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "json_invalid" in message and any(
        marker in message
        for marker in (
            "eof",
            "unterminated",
            "end of input",
            "parsing a string",
        )
    )


def _is_unsupported_temperature_error(exc: APIStatusError) -> bool:
    if getattr(exc, "status_code", None) != 400:
        return False
    response = getattr(exc, "response", None)
    message = getattr(response, "text", None) or str(exc)
    normalized = message.lower()
    return "unsupported parameter" in normalized and "temperature" in normalized


def _extract_parsed_payload(response: Any) -> EquityAiPayload | None:
    parsed = getattr(response, "output_parsed", None)
    if isinstance(parsed, EquityAiPayload):
        return parsed
    if parsed is not None:
        return EquityAiPayload.model_validate(parsed)

    raw_candidates: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            content_parsed = getattr(content, "parsed", None)
            if isinstance(content_parsed, EquityAiPayload):
                return content_parsed
            if content_parsed is not None:
                return EquityAiPayload.model_validate(content_parsed)

            if getattr(content, "type", None) == "output_text":
                text = getattr(content, "text", None)
                if isinstance(text, str) and text.strip():
                    raw_candidates.append(text)

    raw_output_text = getattr(response, "output_text", None)
    if isinstance(raw_output_text, str) and raw_output_text.strip():
        raw_candidates.append(raw_output_text)

    for candidate in reversed(raw_candidates):
        try:
            return EquityAiPayload.model_validate_json(candidate)
        except Exception:
            continue
    return None


class OpenAIEquityReportClient:
    _models_without_temperature: set[str] = set()

    def __init__(self) -> None:
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_REPORT_MODEL
        self.timeout_s = settings.OPENAI_REPORT_TIMEOUT_S
        self.max_retries = settings.OPENAI_REPORT_MAX_RETRIES
        self.max_output_tokens = settings.OPENAI_REPORT_MAX_OUTPUT_TOKENS
        self.temperature = settings.OPENAI_REPORT_TEMPERATURE
        self.client = (
            AsyncOpenAI(
                api_key=self.api_key,
                timeout=self.timeout_s,
                max_retries=self.max_retries,
            )
            if self.api_key
            else None
        )

    async def generate(self, system_prompt: str, user_prompt: str) -> OpenAIReportResult:
        if self.client is None:
            raise OpenAIReportError("OPENAI_API_KEY is not configured.")

        request_payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "text_format": EquityAiPayload,
            "max_output_tokens": self.max_output_tokens,
        }
        if self.temperature is not None and self.model not in self._models_without_temperature:
            request_payload["temperature"] = self.temperature
        if settings.OPENAI_REPORT_ENABLE_WEB_SEARCH:
            request_payload["tools"] = [{"type": "web_search"}]
            request_payload["tool_choice"] = "auto"
            request_payload["max_tool_calls"] = settings.OPENAI_REPORT_WEB_SEARCH_MAX_TOOL_CALLS
            request_payload["reasoning"] = {"effort": "low"}

        try:
            try:
                response = await self.client.responses.parse(**request_payload)
            except APIStatusError as exc:
                if "temperature" not in request_payload or not _is_unsupported_temperature_error(exc):
                    raise
                self._models_without_temperature.add(self.model)
                logger.warning(
                    "OpenAI model %s rejected temperature=%s; retrying without temperature.",
                    self.model,
                    self.temperature,
                )
                request_payload = {key: value for key, value in request_payload.items() if key != "temperature"}
                response = await self.client.responses.parse(**request_payload)
        except APITimeoutError as exc:
            raise OpenAIReportError(
                "OpenAI request timed out "
                f"(timeout={self.timeout_s}s, retries={self.max_retries}, "
                f"web_search={'on' if settings.OPENAI_REPORT_ENABLE_WEB_SEARCH else 'off'}, "
                f"max_output_tokens={self.max_output_tokens})."
            ) from exc
        except APIStatusError as exc:
            raise OpenAIReportError(
                f"OpenAI SDK request failed: status={exc.status_code} body={exc.response.text}"
            ) from exc
        except ValidationError as exc:
            if _is_likely_truncated_json_error(exc):
                raise OpenAIReportError(
                    "OpenAI structured response was truncated before valid JSON could be parsed "
                    f"(max_output_tokens={self.max_output_tokens}, "
                    f"web_search={'on' if settings.OPENAI_REPORT_ENABLE_WEB_SEARCH else 'off'}, "
                    f"max_tool_calls={settings.OPENAI_REPORT_WEB_SEARCH_MAX_TOOL_CALLS}). "
                    "Increase OPENAI_REPORT_MAX_OUTPUT_TOKENS or reduce generated narrative length."
                ) from exc
            raise OpenAIReportError(f"OpenAI structured response failed schema validation: {exc}") from exc
        except Exception as exc:
            raise OpenAIReportError(f"OpenAI SDK request failed: {exc}") from exc

        refusal = _extract_refusal(response)
        if refusal:
            raise OpenAIReportError(refusal)

        parsed = _extract_parsed_payload(response)
        if parsed is None:
            response_status = getattr(response, "status", None)
            if response_status == "incomplete":
                raise OpenAIReportError(
                    "OpenAI structured response was incomplete: "
                    f"{_response_debug_summary(response)}"
                )
            raise OpenAIReportError(
                "OpenAI structured response did not produce parsed output. "
                f"{_response_debug_summary(response)}"
            )

        usage_prompt_tokens, usage_output_tokens = _extract_usage(response)
        return OpenAIReportResult(
            payload=parsed,
            model=str(getattr(response, "model", None) or self.model),
            usage_prompt_tokens=usage_prompt_tokens,
            usage_output_tokens=usage_output_tokens,
        )
