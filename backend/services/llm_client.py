"""
Unified LLM client with retry. Supports OpenAI and Groq (OpenAI-compatible).
"""
import asyncio
from backend.config import get_settings

settings = get_settings()


async def call_llm(
    provider: str,
    model: str,
    system: str,
    user: str,
    json_mode: bool = False,
    temperature: float = 0.2,
) -> str:
    last_error: Exception | None = None
    for attempt in range(settings.max_retries):
        try:
            return await _call_once(provider, model, system, user, json_mode, temperature)
        except Exception as e:
            last_error = e
            if attempt < settings.max_retries - 1:
                await asyncio.sleep(settings.retry_delay_seconds * (attempt + 1))
    raise RuntimeError(f"LLM call failed after {settings.max_retries} attempts: {last_error}") from last_error


async def _call_once(provider, model, system, user, json_mode, temperature) -> str:
    from openai import AsyncOpenAI

    base_url = None
    api_key  = settings.openai_api_key

    if provider == "groq":
        base_url = "https://api.groq.com/openai/v1"
        api_key  = settings.groq_api_key

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    kwargs: dict = dict(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""
