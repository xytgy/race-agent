def map_llm_error(message: str) -> tuple[int, str]:
    text = message.lower()
    if "401" in text or "unauthorized" in text:
        return 401, "llm_unauthorized"
    if "429" in text or "rate limit" in text:
        return 429, "llm_rate_limited"
    if "timed out" in text or "timeout" in text:
        return 504, "llm_timeout"
    return 502, "llm_upstream_error"

