"""OpenRouter client: chat, vision, image generation."""
from __future__ import annotations

import base64
import re
from typing import Any

import httpx

from app.config import settings


class OpenRouterError(RuntimeError):
    pass


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_base_url or "https://avitolog.ai",
        "X-Title": "AvitologAI",
    }


async def chat_completions(
    api_key: str,
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.4,
    max_tokens: int = 2500,
) -> dict[str, Any]:
    if not api_key:
        raise OpenRouterError("OpenRouter API key не задан. Укажите ключ в Настройках.")
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers=_headers(api_key),
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        if resp.status_code >= 400:
            raise OpenRouterError(f"OpenRouter chat error {resp.status_code}: {resp.text[:800]}")
        return resp.json()


async def generate_image(
    api_key: str,
    *,
    model: str,
    prompt: str,
    n: int = 1,
) -> list[bytes]:
    """Generate images via OpenRouter Images API; fallback to chat modalities if needed."""
    if not api_key:
        raise OpenRouterError("OpenRouter API key не задан.")
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/images",
            headers=_headers(api_key),
            json={"model": model, "prompt": prompt, "n": n, "output_format": "png"},
        )
        if resp.status_code < 400:
            data = resp.json()
            out: list[bytes] = []
            for item in data.get("data") or []:
                b64 = item.get("b64_json") or item.get("b64")
                if b64:
                    out.append(base64.b64decode(b64))
                elif item.get("url") and str(item["url"]).startswith("data:"):
                    out.append(_data_url_to_bytes(item["url"]))
            if out:
                return out

        # Fallback: multimodal chat models that return images
        chat = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers=_headers(api_key),
            json={
                "model": model,
                "messages": [{"role": "user", "content": f"Generate an image: {prompt}"}],
                "modalities": ["image", "text"],
            },
        )
        if chat.status_code >= 400:
            raise OpenRouterError(
                f"Image generation failed. images={resp.status_code} {resp.text[:400]}; "
                f"chat={chat.status_code} {chat.text[:400]}"
            )
        return _extract_images_from_chat(chat.json())


async def edit_image(
    api_key: str,
    *,
    model: str,
    prompt: str,
    source_image: str,
) -> list[bytes]:
    """Edit/reference image via OpenRouter; falls back to generate_image on failure.

    source_image: data URL or https URL.
    """
    if not api_key:
        raise OpenRouterError("OpenRouter API key не задан.")
    async with httpx.AsyncClient(timeout=180.0) as client:
        # Try images API with image input (providers vary)
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "output_format": "png",
            "image": source_image,
        }
        resp = await client.post(
            f"{settings.openrouter_base_url}/images",
            headers=_headers(api_key),
            json=payload,
        )
        if resp.status_code < 400:
            data = resp.json()
            out: list[bytes] = []
            for item in data.get("data") or []:
                b64 = item.get("b64_json") or item.get("b64")
                if b64:
                    out.append(base64.b64decode(b64))
                elif item.get("url") and str(item["url"]).startswith("data:"):
                    out.append(_data_url_to_bytes(item["url"]))
            if out:
                return out

        # Multimodal chat edit
        chat = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers=_headers(api_key),
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Edit this reference photo for an Avito listing. "
                                    "Keep the real product/object; apply only the brief.\n" + prompt
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": source_image}},
                        ],
                    }
                ],
                "modalities": ["image", "text"],
            },
        )
        if chat.status_code < 400:
            extracted = _extract_images_from_chat(chat.json())
            if extracted:
                return extracted

    # Last resort: text-to-image without edit
    return await generate_image(api_key, model=model, prompt=prompt, n=1)


def _data_url_to_bytes(url: str) -> bytes:
    m = re.match(r"data:image/[^;]+;base64,(.+)", url, re.DOTALL)
    if not m:
        raise OpenRouterError("Unsupported data URL")
    return base64.b64decode(m.group(1))


def _extract_images_from_chat(payload: dict[str, Any]) -> list[bytes]:
    out: list[bytes] = []
    choices = payload.get("choices") or []
    if not choices:
        return out
    message = choices[0].get("message") or {}
    images = message.get("images") or []
    for img in images:
        url = (img.get("image_url") or {}).get("url") or img.get("url")
        if url and str(url).startswith("data:"):
            out.append(_data_url_to_bytes(url))
    content = message.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url")
                if url and str(url).startswith("data:"):
                    out.append(_data_url_to_bytes(url))
    return out


def build_vision_user_content(text: str, images: list[str]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for img in images:
        url = img
        if not url.startswith("data:") and not url.startswith("http"):
            # relative /uploads path — caller should convert; keep as-is if absolute
            continue
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts
