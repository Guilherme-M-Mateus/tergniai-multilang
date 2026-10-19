"""
Azure Translator service for the Terngi Translation API
"""

import logging
import uuid
from typing import Any, Dict, List, Tuple

import httpx
from fastapi import HTTPException

import config

logger = logging.getLogger(__name__)


async def _call_azure(path: str, params: Dict[str, str], texts: List[str]) -> Any:
    """
    Send a request to Azure Translator and return the parsed JSON body

    Args:
        path: API path, e.g. "/translate" or "/detect"
        params: Query parameters (api-version is added automatically)
        texts: Texts to send in the request body

    Returns:
        Parsed JSON response
    """
    if not config.AZURE_TRANSLATOR_KEY:
        raise HTTPException(status_code=503, detail="Translation service is not configured")

    url = config.AZURE_TRANSLATOR_ENDPOINT.rstrip("/") + path

    headers = {
        "Ocp-Apim-Subscription-Key": config.AZURE_TRANSLATOR_KEY,
        "Ocp-Apim-Subscription-Region": config.AZURE_TRANSLATOR_LOCATION,
        "Content-type": "application/json",
        "X-ClientTraceId": str(uuid.uuid4()),
    }

    body = [{"text": text} for text in texts]

    try:
        # Make the request to Azure Translator without blocking the event loop
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            response = await client.post(
                url, params={"api-version": "3.0", **params}, headers=headers, json=body
            )
    except httpx.HTTPError as e:
        logger.exception("Error connecting to Azure Translator")
        raise HTTPException(
            status_code=502, detail="Error connecting to translation service"
        ) from e

    # Upstream errors are logged but not leaked to the client
    if response.status_code != 200:
        logger.error("Azure Translator returned %s: %s", response.status_code, response.text)
        raise HTTPException(status_code=502, detail="Translation service error")

    try:
        return response.json()
    except ValueError as e:
        raise HTTPException(
            status_code=502, detail="Invalid response from translation service"
        ) from e


async def translate_batch(texts: List[str], from_language: str, to_language: str) -> List[str]:
    """
    Translate several texts in a single Azure request

    Args:
        texts: Texts to translate
        from_language: Source language code
        to_language: Target language code

    Returns:
        Translated texts, in the same order as the input
    """
    data = await _call_azure("/translate", {"from": from_language, "to": to_language}, texts)
    try:
        translated = [item["translations"][0]["text"] for item in data]
    except (LookupError, TypeError) as e:
        raise HTTPException(status_code=502, detail="No translation result received") from e
    if len(translated) != len(texts):
        raise HTTPException(status_code=502, detail="No translation result received")
    return translated


async def detect_language(content: str) -> Tuple[str, float]:
    """
    Detect the language of a piece of text

    Args:
        content: Text to inspect

    Returns:
        Tuple of (language code, confidence score between 0 and 1)
    """
    data = await _call_azure("/detect", {}, [content])
    try:
        return data[0]["language"], float(data[0].get("score", 0.0))
    except (LookupError, TypeError, ValueError) as e:
        raise HTTPException(status_code=502, detail="No detection result received") from e
