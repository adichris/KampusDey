"""Likes, comments (masked), reviews, reports, saved searches, shares (§6.7)."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import QueryDict
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.text import mask_contacts
from apps.listings.models import Listing

from .models import Comment, Like, Report, Review, SavedSearch


class EngagementError(Exception):
    pass


@transaction.atomic
def toggle_like(user, listing: Listing, request=None) -> bool:
    from apps.accounts.services import can_like
    from apps.telemetry.services import record

    decision = can_like(user)
    if not decision:
        raise EngagementError(decision.reason)
    deleted, _ = Like.objects.filter(user=user, listing=listing).delete()
    if deleted:
        Listing.objects.filter(pk=listing.pk, likes_count__gt=0).update(likes_count=F("likes_count") - 1)
        record("unlike", request=request, user=user, listing=listing)
        return False
    try:
        Like.objects.create(user=user, listing=listing)
    except IntegrityError:
        return True
    Listing.objects.filter(pk=listing.pk).update(likes_count=F("likes_count") + 1)
    record("like", request=request, user=user, listing=listing)
    return True


@transaction.atomic
def add_comment(user, listing: Listing, body: str, parent: Comment | None = None) -> Comment:
    from apps.accounts.services import can_comment
    from apps.moderation.services import check_comment, queue_for_review
    from apps.notifications.services import notify

    decision = can_comment(user)
    if not decision:
        raise EngagementError(decision.reason)
    body = (body or "").strip()
    if not body:
        raise EngagementError(_("Write something first."))
    if parent is not None:
        if parent.listing_id != listing.pk:
            raise EngagementError(_("Invalid reply."))
        parent = parent.parent or parent  # one level of replies only
    verdict = check_comment(body)
    if verdict.blocked:
        raise EngagementError(verdict.message)
    comment = Comment.objects.create(
        listing=listing,
        author=user,
        parent=parent,
        body=mask_contacts(body),  # masked before it reaches the database
        is_owner_reply=user.pk == listing.owner_id,
        is_hidden=verdict.review,
    )
    if verdict.review:
        queue_for_review(comment, verdict.reason)
    Listing.objects.filter(pk=listing.pk).update(comments_count=F("comments_count") + 1)
    url = listing.get_absolute_url() + "#comments"
    if user.pk != listing.owner_id:
        notify(listing.owner, "comment", _("New question on “%(t)s”") % {"t": listing.title}, comment.body[:120], url)
    if parent is not None and parent.author_id != user.pk:
        notify(parent.author, "reply", _("Someone replied to your question"), comment.body[:120], url)
    return comment


def hide_comment(user, comment: Comment) -> None:
    if user.pk != comment.listing.owner_id and not user.is_staff:
        raise EngagementError(_("Only the owner can hide comments."))
    comment.is_hidden = True
    comment.save(update_fields=["is_hidden", "updated_at"])


def visible_comments(listing: Listing):
    return (
        Comment.objects.filter(listing=listing, parent__isnull=True, is_hidden=False)
        .select_related("author__profile")
        .prefetch_related("replies__author")
        .order_by("created_at")
    )


def can_review_hostel(user, hostel) -> bool:
    from apps.chat.models import Conversation

    if not user.is_authenticated or user.pk == hostel.owner_id:
        return False
    return Conversation.objects.filter(
        starter=user, listing__roomdetails__hostel_room_type__hostel=hostel
    ).exists()


def can_review_user(user, target) -> bool:
    from apps.chat.models import Conversation

    if not user.is_authenticated or user.pk == target.pk:
        return False
    return Conversation.objects.filter(starter=user, owner=target).exists()


def add_review(user, rating: int, body: str = "", hostel=None, target_user=None) -> Review:
    if hostel is not None and not can_review_hostel(user, hostel):
        raise EngagementError(_("You can review a hostel after contacting it through KampusDey."))
    if target_user is not None and not can_review_user(user, target_user):
        raise EngagementError(_("You can review someone after contacting them through KampusDey."))
    rating = int(rating)
    if not 1 <= rating <= 5:
        raise EngagementError(_("Choose 1 to 5 stars."))
    review, _created = Review.objects.update_or_create(
        reviewer=user, hostel=hostel, target_user=target_user,
        defaults={"rating": rating, "body": mask_contacts(body)},
    )
    return review


def report(reporter, target, reason: str, details: str = "") -> Report:
    from apps.moderation.services import handle_new_report

    if reason not in Report.Reason.values:
        raise EngagementError(_("Choose a reason."))
    ct = ContentType.objects.get_for_model(target)
    existing = Report.objects.filter(
        content_type=ct, object_id=target.pk, reporter=reporter, status=Report.Status.OPEN
    ).first()
    if existing:
        return existing
    item = Report.objects.create(
        content_type=ct, object_id=target.pk, reporter=reporter, reason=reason, details=mask_contacts(details)
    )
    handle_new_report(item)
    return item


# ---------------------------------------------------------------------------
# Saved searches
# ---------------------------------------------------------------------------
IGNORED_PARAMS = {"page", "view", "csrfmiddlewaretoken"}


def save_search(user, section: str, params: QueryDict | dict, campus=None, town=None) -> SavedSearch:
    clean = {k: v for k, v in dict(params).items() if k not in IGNORED_PARAMS and v not in ("", None, [])}
    clean = {k: (v[0] if isinstance(v, list) and len(v) == 1 else v) for k, v in clean.items()}
    item, _created = SavedSearch.objects.get_or_create(
        user=user, section=section, campus=campus, town=None if campus else town, params=clean,
        defaults={"last_notified_at": timezone.now()},
    )
    if not item.is_active:
        item.is_active = True
        item.save(update_fields=["is_active"])
    return item


def matches_for(saved: SavedSearch, since):
    from apps.listings.filters import filter_for
    from apps.listings.selectors import for_campus, for_town, visible_listings

    qs = visible_listings(saved.user, [saved.section] if saved.section else None)
    if saved.campus_id:
        qs = for_campus(qs, saved.campus)
    elif saved.town_id:
        qs = for_town(qs, saved.town)
    qd = QueryDict(mutable=True)
    for key, value in (saved.params or {}).items():
        if isinstance(value, list):
            qd.setlist(key, value)
        else:
            qd[key] = value
    q = qd.pop("q", [""])[0] if "q" in qd else ""
    if saved.section:
        qs = filter_for(saved.section)(qd, queryset=qs).qs
    if q:
        from django.db.models import Q

        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    return qs.filter(published_at__gt=since).exclude(owner=saved.user)


def run_saved_search_alerts(now=None) -> int:
    """Daily: notify on listings published since the last alert. Only *new* matches fire."""
    from apps.notifications.services import notify

    now = now or timezone.now()
    sent = 0
    for saved in SavedSearch.objects.filter(is_active=True).select_related("user", "campus", "town"):
        since = saved.last_notified_at or saved.created_at
        matches = list(matches_for(saved, since)[:10])
        if matches:
            section = matches[0].section_obj.label
            notify(
                saved.user,
                "saved_search",
                _("%(n)s new %(section)s matching your alert") % {"n": len(matches), "section": section},
                ", ".join(m.title for m in matches[:3]),
                url=matches[0].get_absolute_url() if len(matches) == 1 else "/saved/",
            )
            sent += 1
        saved.last_notified_at = now
        saved.save(update_fields=["last_notified_at", "updated_at"])
    return sent


def record_share(request, listing: Listing, channel: str = "") -> None:
    from apps.telemetry.services import record

    record("share", request=request, listing=listing, meta={"channel": channel[:20]})
