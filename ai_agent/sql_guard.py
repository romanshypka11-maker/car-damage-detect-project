import logging
import re

logger = logging.getLogger(__name__)

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


def validate_sql(query: str) -> str | None:
    """Return cleaned SQL if valid, else None."""
    if not query or not query.strip():
        return None

    cleaned = query.strip().rstrip(";")

    if "```" in cleaned:
        match = re.search(r"```(?:sql)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
        if match:
            cleaned = match.group(1).strip()

    if "SELECT" not in cleaned.upper():
        logger.warning("SQL rejected: missing SELECT")
        return None

    if _FORBIDDEN_KEYWORDS.search(cleaned):
        logger.warning("SQL rejected: forbidden keyword detected")
        return None

    if ";" in cleaned:
        logger.warning("SQL rejected: multiple statements")
        return None

    return cleaned
