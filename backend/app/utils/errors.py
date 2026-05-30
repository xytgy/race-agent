def classify_llm_error(message: str) -> str:
    text = (message or "").lower()
    if "401" in text or "unauthorized" in text:
        return "llm_unauthorized"
    if "403" in text or "forbidden" in text:
        return "llm_forbidden"
    if "429" in text or "rate limit" in text or "too many requests" in text:
        return "llm_rate_limited"
    if "ssl" in text or "ssleoferror" in text or "certificate" in text:
        return "llm_ssl_error"
    if "connect timeout" in text or "connection timed out" in text:
        return "llm_connect_timeout"
    if "read timed out" in text or "read timeout" in text:
        return "llm_read_timeout"
    if "timed out" in text or "timeout" in text:
        return "llm_timeout"
    if "502" in text or "503" in text or "504" in text or "bad gateway" in text or "service unavailable" in text:
        return "llm_bad_gateway"
    if "connection refused" in text or "failed to establish a new connection" in text or "name resolution" in text:
        return "llm_connection_error"
    if "invalid_llm_response" in text or "jsondecodeerror" in text or "invalid json" in text:
        return "llm_invalid_response"
    return "llm_upstream_error"


def map_llm_error(message: str) -> tuple[int, str]:
    error_type = classify_llm_error(message)
    status_by_type = {
        "llm_unauthorized": 401,
        "llm_forbidden": 403,
        "llm_rate_limited": 429,
        "llm_connect_timeout": 504,
        "llm_read_timeout": 504,
        "llm_timeout": 504,
        "llm_bad_gateway": 502,
        "llm_connection_error": 502,
        "llm_ssl_error": 502,
        "llm_invalid_response": 502,
        "llm_upstream_error": 502,
    }
    return status_by_type.get(error_type, 502), error_type
