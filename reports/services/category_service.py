"""
Category service.

Keyword-based category assignment and severity scoring.
Rule-based only — no ML or AI.
"""

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category rules — first match wins, so order matters.
# More specific phrases should come before generic ones.
# ---------------------------------------------------------------------------

CATEGORY_RULES: list[tuple[str, str]] = [
    # Specific attack vectors first
    ("flash loan",         "Flash Loan"),
    ("reentrancy",         "Reentrancy"),
    ("re-entrancy",        "Reentrancy"),
    ("price manipulation", "Oracle Manipulation"),
    ("oracle manipulation","Oracle Manipulation"),
    ("oracle",             "Oracle Manipulation"),
    ("private key",        "Key Compromise"),
    ("key compromise",     "Key Compromise"),
    ("signature",          "Signature Verification"),
    ("authorization",      "Access Control"),
    ("unauthorized",       "Access Control"),
    ("access control",     "Access Control"),
    ("integer overflow",   "Integer Overflow"),
    ("arithmetic",         "Integer Overflow"),
    ("bridge",             "Bridge Exploit"),
    ("cross-chain",        "Bridge Exploit"),
    ("rug pull",           "Rug Pull"),
    ("rugpull",            "Rug Pull"),
    ("exit scam",          "Rug Pull"),
    ("phishing",           "Phishing"),
    ("social engineering", "Phishing"),
    ("supply chain",       "Supply Chain Attack"),
    ("front.run",          "MEV / Front-Running"),
    ("sandwich",           "MEV / Front-Running"),
    ("mev",                "MEV / Front-Running"),
    ("governance",         "Governance Attack"),
    ("inflation",          "Token Inflation"),
    ("logic error",        "Logic Error"),
    ("misconfiguration",   "Misconfiguration"),
    ("honeypot",           "Honeypot"),
    ("sybil",              "Sybil Attack"),
]

# ---------------------------------------------------------------------------
# Severity thresholds (dollar amounts in USD)
# ---------------------------------------------------------------------------

_SEVERITY_THRESHOLDS: list[tuple[float, str]] = [
    (50_000_000,  "critical"),  # ≥ $50M
    (10_000_000,  "high"),      # ≥ $10M
    (1_000_000,   "high"),      # ≥ $1M
    (100_000,     "medium"),    # ≥ $100k
]

# Keyword fallbacks when no dollar amount is found
_SEVERITY_KEYWORDS: list[tuple[str, str]] = [
    ("drained",       "critical"),
    ("completely drained", "critical"),
    ("fully drained", "critical"),
    ("millions",      "high"),
    ("hundreds of thousands", "medium"),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assign_category(text: str):
    """
    Return a Category instance for the first matching keyword in text,
    or None if no rule matches. Creates the Category if it doesn't exist.
    """
    from reports.models import Category  # noqa: PLC0415

    text_lower = text.lower()
    for keyword, category_name in CATEGORY_RULES:
        if keyword in text_lower:
            cat, created = Category.objects.get_or_create(name=category_name)
            if created:
                logger.info("Created new category: %s", category_name)
            return cat
    return None


def assign_severity_smart(text: str) -> str:
    """
    Dollar-amount-aware severity assignment:
      1. Extract the largest dollar amount from the text.
      2. Map to severity via thresholds.
      3. Fall back to keyword rules if no dollar amount found.
      4. Default to 'medium'.
    """
    from reports.models import HackReport  # noqa: PLC0415
    from analytics.cleaner import extract_max_dollar_amount  # noqa: PLC0415

    amount = extract_max_dollar_amount(text)
    if amount > 0:
        for threshold, severity in _SEVERITY_THRESHOLDS:
            if amount >= threshold:
                return severity

    # Keyword fallback
    text_lower = text.lower()
    for keyword, severity in _SEVERITY_KEYWORDS:
        if keyword in text_lower:
            return severity

    return HackReport.Severity.MEDIUM


# Keep old name for backward compatibility (used by Phase 1 smoke test)
def assign_severity(text: str) -> str:
    return assign_severity_smart(text)
