"""Seed banned terms (§6.8, §6.11). Idempotent; admins edit them afterwards."""

from .models import BannedTerm

WARN_TERMS = ["momo", "mobile money", "deposit", "send money", "pay first", "transfer"]
REVIEW_TERMS = [
    (r"get[\s-]*rich", True),
    (r"(buy|sell)(ing)?\s+(instagram|tiktok|facebook|twitter|x)?\s*followers", True),
    (r"(whatsapp|telegram)\s+group\s+members", True),
    ("forex signals", False),
]
BLOCK_TERMS = [(r"counterfeit|fake\s+(certificate|transcript|degree)", True)]


def seed_banned_terms():
    for term in WARN_TERMS:
        BannedTerm.objects.get_or_create(
            term=term, applies_to=BannedTerm.AppliesTo.MESSAGE, defaults={"action": BannedTerm.Action.WARN}
        )
    for term, is_regex in REVIEW_TERMS:
        BannedTerm.objects.get_or_create(
            term=term, applies_to=BannedTerm.AppliesTo.ALL,
            defaults={"action": BannedTerm.Action.REVIEW, "is_regex": is_regex},
        )
    for term, is_regex in BLOCK_TERMS:
        BannedTerm.objects.get_or_create(
            term=term, applies_to=BannedTerm.AppliesTo.ALL,
            defaults={"action": BannedTerm.Action.BLOCK, "is_regex": is_regex},
        )
