"""Rules engine (§6.11): price sanity, duplicates, banned terms; moderation queue actions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from constance import config
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.images import hamming
from apps.core.text import trigram_similarity

from .models import BannedTerm, ModerationItem

DUPLICATE_TITLE_SIMILARITY = 0.8
DUPLICATE_PHASH_DISTANCE = 6
SCAM_WARNING = _("Never pay before viewing the room.")


class ModerationBlocked(Exception):
    pass


@dataclass
class Verdict:
    blocked: bool = False
    review: bool = False
    warn: bool = False
    reasons: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons)

    def block(self, message, reason=None):
        self.blocked = True
        self.message = self.message or message
        self.reasons.append(reason or message)

    def send_to_review(self, reason):
        self.review = True
        self.reasons.append(reason)


def _term_matches(term: BannedTerm, text: str) -> bool:
    if term.is_regex:
        try:
            return re.search(term.term, text, re.I) is not None
        except re.error:
            return False
    return re.search(r"(?<!\w)" + re.escape(term.term.lower()) + r"(?!\w)", text.lower()) is not None


def banned_matches(text: str, applies_to: str) -> list[BannedTerm]:
    terms = BannedTerm.objects.filter(is_active=True, applies_to__in=[applies_to, BannedTerm.AppliesTo.ALL])
    return [t for t in terms if _term_matches(t, text or "")]


def apply_terms(verdict: Verdict, text: str, applies_to: str) -> Verdict:
    for term in banned_matches(text, applies_to):
        if term.action == BannedTerm.Action.BLOCK:
            verdict.block(_("This post contains content that isn't allowed on KampusDey."), f"banned term: {term.term}")
        elif term.action == BannedTerm.Action.REVIEW:
            verdict.send_to_review(f"term needs review: {term.term}")
        else:
            verdict.warn = True
    return verdict


def _category_for(listing):
    details = listing.details
    if details is None:
        return None
    return getattr(details, "category", None) or getattr(details, "service_type", None)


def check_listing(listing) -> Verdict:
    from apps.listings.models import Listing

    verdict = Verdict()
    if listing.price is not None and listing.price < 0:
        verdict.block(_("Price cannot be negative."), "negative price")
        return verdict
    category = _category_for(listing)
    if category is not None and listing.price is not None:
        if (category.min_price is not None and listing.price < category.min_price) or (
            category.max_price is not None and listing.price > category.max_price
        ):
            verdict.send_to_review(f"price outside {category.name} range")

    others = Listing.objects.filter(section=listing.section).exclude(pk=listing.pk).exclude(
        status__in=[Listing.Status.DRAFT, Listing.Status.ARCHIVED]
    )
    for other in others.filter(owner=listing.owner).only("title"):
        if trigram_similarity(listing.title, other.title) >= DUPLICATE_TITLE_SIMILARITY:
            verdict.block(
                _("You already have a similar post (“%(title)s”). Edit or renew that one instead.")
                % {"title": other.title},
                "duplicate of own listing",
            )
            return verdict
    for other in others.exclude(owner=listing.owner).filter(town=listing.town).only("title")[:500]:
        if trigram_similarity(listing.title, other.title) >= DUPLICATE_TITLE_SIMILARITY:
            verdict.send_to_review(f"near-duplicate of listing #{other.pk}")
            break
    phashes = [p for p in listing.photos.values_list("phash", flat=True) if p]
    if phashes:
        from apps.listings.models import ListingPhoto

        foreign = ListingPhoto.objects.exclude(listing=listing).exclude(listing__owner=listing.owner).exclude(phash="")
        for other_hash, other_listing in foreign.values_list("phash", "listing_id")[:5000]:
            if any(hamming(h, other_hash) <= DUPLICATE_PHASH_DISTANCE for h in phashes):
                verdict.send_to_review(f"photo matches listing #{other_listing}")
                break
    apply_terms(verdict, f"{listing.title}\n{listing.description}", BannedTerm.AppliesTo.LISTING)
    return verdict


def photo_is_duplicate(listing, phash: str) -> bool:
    """Same owner re-using a photo from another of their live listings → block."""
    from apps.listings.models import Listing, ListingPhoto

    if not phash:
        return False
    qs = ListingPhoto.objects.filter(listing__owner=listing.owner).exclude(listing=listing).exclude(
        listing__status__in=[Listing.Status.ARCHIVED, Listing.Status.DRAFT]
    )
    return any(hamming(phash, other) <= DUPLICATE_PHASH_DISTANCE for other in qs.values_list("phash", flat=True))


def check_comment(body: str) -> Verdict:
    return apply_terms(Verdict(), body, BannedTerm.AppliesTo.COMMENT)


def check_message(body: str) -> Verdict:
    return apply_terms(Verdict(), body, BannedTerm.AppliesTo.MESSAGE)


def queue_for_review(obj, reason: str, auto: bool = True) -> ModerationItem:
    ct = ContentType.objects.get_for_model(obj)
    item, _created = ModerationItem.objects.get_or_create(
        content_type=ct, object_id=obj.pk, status=ModerationItem.Status.PENDING,
        defaults={"reason": reason[:300], "auto": auto},
    )
    return item


@transaction.atomic
def decide(item: ModerationItem, approve: bool, reviewer=None) -> ModerationItem:
    from apps.engagement.models import Comment
    from apps.listings.models import Listing
    from apps.listings.services import approve as approve_listing

    target = item.target
    if isinstance(target, Listing):
        if approve:
            approve_listing(target)
        else:
            target.is_hidden = True
            target.hidden_reason = item.reason
            target.status = Listing.Status.ARCHIVED
            target.status_changed_at = timezone.now()
            target.save()
            from apps.boosts.services import end_boosts

            end_boosts(target)
    elif isinstance(target, Comment):
        target.is_hidden = not approve
        target.save(update_fields=["is_hidden", "updated_at"])
    elif target is not None and hasattr(target, "status") and hasattr(target, "reports_count"):
        # External places hidden by reports.
        target.status = "unclaimed" if approve and target.status == "hidden" else target.status
        if not approve:
            target.status = "hidden"
        target.save(update_fields=["status", "updated_at"])
    item.status = ModerationItem.Status.APPROVED if approve else ModerationItem.Status.REJECTED
    item.reviewed_by = reviewer
    item.reviewed_at = timezone.now()
    item.save()
    return item


def handle_new_report(report) -> None:
    """Auto-hide listings (and places) that reach the report threshold."""
    from apps.engagement.models import Report
    from apps.listings.models import Listing

    target = report.target
    if target is None:
        return
    open_count = Report.objects.filter(
        content_type=report.content_type, object_id=report.object_id, status=Report.Status.OPEN
    ).count()
    if isinstance(target, Listing):
        Listing.objects.filter(pk=target.pk).update(reports_count=open_count)
        if open_count >= config.REPORTS_AUTO_HIDE and not target.is_hidden:
            Listing.objects.filter(pk=target.pk).update(
                is_hidden=True, hidden_reason=_("Hidden after reports, pending review")
            )
            queue_for_review(target, f"{open_count} open reports")
    elif type(target).__name__ == "Place":
        type(target).objects.filter(pk=target.pk).update(reports_count=open_count)
        if open_count >= config.PLACE_REPORTS_AUTO_HIDE and target.status != "hidden":
            type(target).objects.filter(pk=target.pk).update(status="hidden")
            queue_for_review(target, f"{open_count} place reports")


def suggest_price_ranges(min_samples: int = 30) -> int:
    """5th–95th percentile of KampusDey's own prices per category; for admins to accept."""
    from apps.listings.models import ItemCategory, Listing, ServiceCategory

    from .models import PriceRangeSuggestion

    created = 0
    groups = [
        ("item", ItemCategory, "itemdetails__category", "price"),
        ("service", ServiceCategory, "servicedetails__service_type", "servicedetails__price_from"),
    ]
    for kind, model, path, price_field in groups:
        for category in model.objects.filter(is_active=True):
            prices = sorted(
                p
                for p in Listing.objects.filter(**{path: category}, **{f"{price_field}__isnull": False}).values_list(
                    price_field, flat=True
                )
                if p is not None and p > 0
            )
            if len(prices) < min_samples:
                continue
            lo = prices[int(0.05 * (len(prices) - 1))]
            hi = prices[int(0.95 * (len(prices) - 1))]
            PriceRangeSuggestion.objects.create(
                category_kind=kind, category_id=category.pk, category_name=category.name,
                suggested_min=lo, suggested_max=hi, samples=len(prices),
            )
            created += 1
    return created
