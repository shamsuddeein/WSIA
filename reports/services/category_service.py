"""
Category service.

Keyword-based category assignment. Rule-based only — no ML.
"""

import logging

logger = logging.getLogger(__name__)

# Extend this dict as new exploit types are encountered.
CATEGORY_RULES: dict[str, str] = {
    "reentrancy": "Reentrancy",
    "oracle": "Oracle Manipulation",
    "flash loan": "Flash Loan",
    "bridge": "Bridge Exploit",
    "private key": "Key Compromise",
    "rugpull": "Rug Pull",
    "rug pull": "Rug Pull",
    "phishing": "Phishing",
    "access control": "Access Control",
    "integer overflow": "Integer Overflow",
    "price manipulation": "Oracle Manipulation",
}

SEVERITY_RULES: list[tuple[str, str]] = [
    # (keyword_in_lower_text, severity_value)
    ("drained", "critical"),
    ("100 million", "critical"),
    ("$100m", "critical"),
    ("$50m", "critical"),
    ("10 million", "high"),
    ("$10m", "high"),
    ("$1m", "high"),
    ("1 million", "high"),
    ("$100k", "medium"),
    ("100,000", "medium"),
]


def assign_category(text: str):
    """
    Return a Category instance matching the first keyword found in text,
    or None if no rule matches.
    Creates the Category if it doesn't exist yet.
    """
    from reports.models import Category  # noqa: PLC0415

    text_lower = text.lower()
    for keyword, category_name in CATEGORY_RULES.items():
        if keyword in text_lower:
            cat, created = Category.objects.get_or_create(
                name=category_name,
                defaults={"name": category_name},
            )
            if created:
                logger.info("Created new category: %s", category_name)
            return cat
    return None


def assign_severity(text: str) -> str:
    """
    Return a severity string based on keyword rules.
    Defaults to 'medium' when no rule matches.
    """
    from reports.models import HackReport  # noqa: PLC0415

    text_lower = text.lower()
    for keyword, severity in SEVERITY_RULES:
        if keyword in text_lower:
            return severity
    return HackReport.Severity.MEDIUM
