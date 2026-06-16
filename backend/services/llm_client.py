"""
Unified LLM client with retry.
Providers:
  - openai   → OpenAI API           (gpt-4o, gpt-4o-mini …)
  - groq     → Groq API             (llama3-70b-8192 …)      [OpenAI-compatible]
  - gemini   → Google Gemini API    (gemini-2.0-flash …)     [OpenAI-compatible]
  - anthropic → Anthropic API       (claude-opus-4-5 …)      [native SDK]
"""
import asyncio
import logging
from backend.config import get_settings

settings = get_settings()
log = logging.getLogger(__name__)

# Order to try providers when the requested one fails (free/strong first).
# A default model per provider is used for fallback hops.
_FALLBACK_ORDER = ["groq", "gemini", "anthropic", "openai"]
_DEFAULT_MODELS = {
    "groq":      "llama-3.3-70b-versatile",
    "gemini":    "gemini-2.0-flash",
    "anthropic": "claude-haiku-4-5",
    "openai":    "gpt-4o-mini",
}
# Error signatures that won't be fixed by retrying the SAME provider — fall back
# to the next provider immediately (no credits, quota, rate limit, bad/no key).
_PERMANENT_MARKERS = (
    "not configured", "invalid x-api-key", "authentication", "401", "402", "403",
    "429", "quota", "insufficient", "credit balance", "billing", "exceeded",
)


def _provider_key_attr(provider: str) -> str:
    if provider == "anthropic":
        return "anthropic_api_key"
    cfg = _OPENAI_COMPAT.get(provider)
    return cfg["key_attr"] if cfg else ""


def _has_key(provider: str) -> bool:
    attr = _provider_key_attr(provider)
    return bool(attr and (getattr(settings, attr, "") or ""))


def _is_permanent(err: Exception) -> bool:
    s = str(err).lower()
    return any(m in s for m in _PERMANENT_MARKERS)

# Providers that use the OpenAI-compatible interface
_OPENAI_COMPAT: dict[str, dict] = {
    "openai": {
        "base_url": None,
        "key_attr": "openai_api_key",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_attr": "groq_api_key",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_attr": "gemini_api_key",
    },
}

_VALID_PROVIDERS = list(_OPENAI_COMPAT.keys()) + ["anthropic"]


async def call_llm(
    provider: str,
    model: str,
    system: str,
    user: str,
    json_mode: bool = False,
    temperature: float = 0.2,
) -> str:
    # Build the provider chain: the requested one first, then the others that
    # have a key configured. If the active provider runs out of credits / hits a
    # quota or rate limit, we transparently switch to the next available one.
    chain: list[tuple[str, str]] = [(provider, model)]
    for p in _FALLBACK_ORDER:
        if p != provider and _has_key(p):
            chain.append((p, _DEFAULT_MODELS[p]))

    last_error: Exception | None = None
    for idx, (p, m) in enumerate(chain):
        for attempt in range(settings.max_retries):
            try:
                result = await _call_once(p, m, system, user, json_mode, temperature)
                if idx > 0:
                    log.warning("LLM fell back to %s/%s (requested %s/%s)", p, m, provider, model)
                return result
            except Exception as e:
                last_error = e
                # Permanent errors (no credits/quota/rate-limit/bad key) won't be
                # fixed by retrying the same provider — break to the next provider.
                if _is_permanent(e):
                    log.warning("provider %s permanent error (%s) — switching provider", p, str(e)[:80])
                    break
                if attempt < settings.max_retries - 1:
                    await asyncio.sleep(settings.retry_delay_seconds * (attempt + 1))
    raise RuntimeError(f"LLM call failed across all providers: {last_error}") from last_error


async def _call_once(provider, model, system, user, json_mode, temperature) -> str:
    if provider not in _VALID_PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Valid: {_VALID_PROVIDERS}")

    # ── Anthropic (native SDK — different API format) ──────────────────────────
    if provider == "anthropic":
        return await _call_anthropic(model, system, user, json_mode, temperature)

    # ── OpenAI-compatible providers ───────────────────────────────────────────
    from openai import AsyncOpenAI

    cfg = _OPENAI_COMPAT[provider]
    api_key = getattr(settings, cfg["key_attr"], "") or ""
    if not api_key:
        raise ValueError(f"API key for provider '{provider}' is not configured.")

    client = AsyncOpenAI(api_key=api_key, base_url=cfg["base_url"])
    kwargs: dict = dict(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


async def _call_anthropic(model: str, system: str, user: str, json_mode: bool, temperature: float) -> str:
    import anthropic

    api_key = settings.anthropic_api_key or ""
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured.")

    # When JSON mode is requested, append a hint (Anthropic has no native json_object mode)
    user_msg = user
    if json_mode:
        user_msg += "\n\nRespond with valid JSON only, no markdown fences."

    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text or ""
