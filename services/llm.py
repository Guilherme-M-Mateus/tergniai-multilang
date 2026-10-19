"""
Language model client that spreads requests over several providers, models and API keys

Order of attempts: providers in the given order, then each provider's models in order,
then that provider's keys in rotation. A key that is rejected (401/403) or rate-limited
(429) is put on cooldown; a model that errors or returns unusable output is skipped.
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, TypeVar

import httpx
from fastapi import HTTPException

import config
from config import LLMProvider
from services.keypool import key_pool, mask, retry_after_seconds

logger = logging.getLogger(__name__)

T = TypeVar("T")
Message = Dict[str, Any]

# MORENA chat markers: single reserved tokens in its vocabulary (see the model card).
# Do not replace them with <|user|>-style strings; that produces degenerate output.
MORENA_USER, MORENA_ASSISTANT = "<reserved_0>", "<reserved_1>"


class _KeyFailed(Exception):
    """The key was rejected or rate-limited; try another key"""

    def __init__(self, cooldown: float):
        self.cooldown = cooldown


class _ModelFailed(Exception):
    """The model can't serve this request; try the next model"""


def is_configured(provider_names: Sequence[str], kind: Optional[str] = None) -> bool:
    """Whether any of the named LLM providers is usable (optionally of a given kind)"""
    return any(
        (p := config.LLM_PROVIDERS.get(name)) is not None
        and p.configured
        and (kind is None or p.kind == kind)
        for name in provider_names
    )


def render_morena_prompt(messages: List[Message]) -> str:
    """Render chat messages in MORENA's format; system text is folded into the first user turn"""
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    turns = [m for m in messages if m["role"] in ("user", "assistant") and m.get("content")]
    prompt = ""
    for i, message in enumerate(turns):
        content = message["content"]
        if i == 0 and system:
            content = f"{system}\n\n{content}"
        marker = MORENA_USER if message["role"] == "user" else MORENA_ASSISTANT
        prompt += f"{marker}\n{content}\n"
    return prompt + f"{MORENA_ASSISTANT}\n"


async def _post(url: str, headers: Dict[str, str], body: Dict[str, Any]) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            return await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as e:
        raise _ModelFailed(f"connection error: {type(e).__name__}") from e


def _check_status(response: httpx.Response, provider: str, key: Optional[str]) -> None:
    """Translate HTTP errors into key or model failures"""
    status = response.status_code
    if status == 200:
        return
    label = f"{provider} key {mask(key)}" if key else provider
    if status in (401, 403):
        logger.warning("%s was rejected (%s); skipping it for a while", label, status)
        raise _KeyFailed(config.INVALID_KEY_COOLDOWN_SECONDS)
    if status == 429:
        logger.warning("%s is rate-limited; trying the next key", label)
        raise _KeyFailed(
            retry_after_seconds(response.headers.get("retry-after"), config.KEY_COOLDOWN_SECONDS)
        )
    logger.warning("%s returned %s: %s", provider, status, response.text[:500])
    raise _ModelFailed(f"HTTP {status}")


async def _call(
    provider: LLMProvider,
    model: str,
    key: Optional[str],
    messages: List[Message],
    json_mode: bool,
    temperature: float,
    max_tokens: Optional[int],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Message:
    """Send one request to one provider/model/key and return the assistant message"""
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    if provider.kind == "morena":
        body: Dict[str, Any] = {
            "prompt": render_morena_prompt(messages),
            "n_predict": max_tokens or 512,
            "temperature": temperature,
            "stop": [MORENA_USER],
            "cache_prompt": True,
        }
        response = await _post(f"{provider.base_url}/completion", headers, body)
        _check_status(response, provider.name, key)
        try:
            return {"role": "assistant", "content": str(response.json()["content"]).strip()}
        except (ValueError, LookupError, TypeError) as e:
            raise _ModelFailed("malformed response") from e

    body = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens:
        body["max_tokens"] = max_tokens
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    response = await _post(f"{provider.base_url}/chat/completions", headers, body)
    _check_status(response, provider.name, key)
    try:
        message = response.json()["choices"][0]["message"]
    except (ValueError, LookupError, TypeError) as e:
        raise _ModelFailed("malformed response") from e
    if not isinstance(message, dict):
        raise _ModelFailed("malformed response")
    return message


async def complete(
    provider_names: Sequence[str],
    messages: List[Message],
    *,
    parse: Callable[[str], T],
    json_mode: bool = False,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
) -> T:
    """
    Generate a completion, trying providers, models and keys until one succeeds

    Args:
        provider_names: LLM provider names, in priority order
        messages: Chat messages
        parse: Turns the generated text into the result; raise ValueError if it is unusable
        json_mode: Ask OpenAI-compatible providers for a JSON object
        temperature: Sampling temperature
        max_tokens: Optional output limit

    Returns:
        The parsed result from the first provider that succeeds
    """
    return await complete_message(
        provider_names,
        messages,
        parse=lambda message: parse(message.get("content") or ""),
        json_mode=json_mode,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def complete_message(
    provider_names: Sequence[str],
    messages: List[Message],
    *,
    parse: Callable[[Message], T],
    tools: Optional[List[Dict[str, Any]]] = None,
    json_mode: bool = False,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
) -> T:
    """
    Like `complete`, but `parse` receives the whole assistant message (including any
    tool calls). When `tools` are given, only OpenAI-compatible providers are used.
    """
    attempted = False

    for name in provider_names:
        provider = config.LLM_PROVIDERS.get(name)
        if provider is None or not provider.configured:
            continue
        if tools and provider.kind != "openai":
            continue
        attempted = True

        keys: List[Optional[str]] = list(key_pool.order(f"llm:{name}", provider.api_keys))
        if not provider.api_keys:
            keys = [None]
        if not keys:
            logger.warning("All %s keys are cooling down; trying the next provider", name)
            continue

        for model in provider.models:
            for key in keys:
                try:
                    message = await _call(
                        provider, model, key, messages, json_mode, temperature, max_tokens, tools
                    )
                except _KeyFailed as e:
                    if key:
                        key_pool.cool_down(key, e.cooldown)
                    continue
                except _ModelFailed as e:
                    logger.warning("%s/%s failed (%s); trying the next model", name, model, e)
                    break
                try:
                    return parse(message)
                except ValueError as e:
                    logger.warning("%s/%s returned unusable output (%s)", name, model, e)
                    break

    if not attempted:
        raise HTTPException(status_code=503, detail="Language model service is not configured")
    raise HTTPException(status_code=502, detail="Error connecting to language model service")


def parse_json_object(text: str) -> Dict[str, Any]:
    """Parse a JSON object from model output, tolerating code fences or surrounding text"""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in output")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("output is not a JSON object")
    return data
