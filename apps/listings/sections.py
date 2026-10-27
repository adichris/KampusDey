"""Section registry: the single place that describes each of the 18 sections."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from django.apps import apps
from django.utils.formats import date_format
from django.utils.timezone import localtime
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Section:
    slug: str
    label: str
    icon: str
    details_model: str
    blurb: str = ""
    sensitive: bool = False  # approximate circle only, never an exact pin
    default_enabled: bool = True
    price_allowed: bool = True
    students_only_filter: bool = False
    expiry_field: str | None = None  # details field after which the listing expires
    card_info: Callable | None = field(default=None, compare=False)

    @property
    def model(self):
        return apps.get_model("listings", self.details_model)

    @property
    def model_name(self) -> str:
        return self.details_model.lower()


def _dt(value, fmt="D j M, H:i"):
    return date_format(localtime(value), fmt) if value else ""


def _d(value, fmt="j M"):
    return date_format(value, fmt) if value else ""


def _price(listing):
    from apps.core.templatetags.kd import ghs

    if listing.is_free:
        return str(_("Free"))
    if listing.price is None:
        return ""
    text = ghs(listing.price)
    if listing.price_period and listing.price_period != "total":
        text += f" / {listing.get_price_period_short()}"
    return text


def _join(*parts):
    return " · ".join(str(p) for p in parts if p)


def info_rooms(listing, d):
    return _join(_price(listing), d and d.get_room_type_display(), d and d.get_gender_display())


def info_roommates(listing, d):
    if not d:
        return ""
    budget = ""
    if d.budget_max:
        from apps.core.templatetags.kd import ghs

        budget = f"≤ {ghs(d.budget_max)}"
    return _join(d.get_post_kind_display(), budget, d.move_in_date and _d(d.move_in_date))


def info_short_stays(listing, d):
    span = ""
    if d and d.available_from:
        span = (
            f"{_d(d.available_from)}–{_d(d.available_to)}"
            if d.available_to
            else _d(d.available_from)
        )
    return _join(_price(listing), span)


def info_items(listing, d):
    return _join(_price(listing), d and d.get_condition_display())


def info_wanted(listing, d):
    from apps.core.templatetags.kd import ghs

    return _join(
        d and d.budget_max and f"≤ {ghs(d.budget_max)}", d and d.needed_by and _d(d.needed_by)
    )


def info_free(listing, d):
    return _join(_("Free"), d and d.pickup_by and _("pick up by %s") % _d(d.pickup_by))


def info_services(listing, d):
    from apps.core.templatetags.kd import ghs

    return _join(d and d.service_type, d and d.price_from and _("from %s") % ghs(d.price_from))


def info_jobs(listing, d):
    return _join(d and d.pay_text, d and d.get_job_type_display())


def info_job_requests(listing, d):
    return _join(d and d.availability, d and d.expected_pay)


def info_errands(listing, d):
    return _join(_price(listing), d and d.deadline and _("by %s") % _dt(d.deadline))


def info_food(listing, d):
    return _join(
        d and d.get_post_kind_display(),
        d and d.available_until and _("until %s") % _dt(d.available_until, "H:i"),
    )


def info_events(listing, d):
    return _join(d and _dt(d.starts_at), d and d.venue)


def info_notes(listing, d):
    return _join(d and d.course_code, _price(listing), d and d.get_format_display())


def info_study(listing, d):
    return _join(d and d.get_kind_display(), d and d.course_code, d and d.get_mode_display())


def info_lost_found(listing, d):
    return _join(
        d and d.get_kind_display(),
        d and d.item_type,
        d and _d(d.happened_at and d.happened_at.date()),
    )


def info_trips(listing, d):
    if not d:
        return ""
    route = f"{d.origin_town.name} → {d.destination_town.name}" if d.origin_town_id else ""
    return _join(route, _dt(d.departs_at))


def info_alerts(listing, d):
    return _join(
        d and d.get_alert_type_display(), d and d.valid_until and _("until %s") % _dt(d.valid_until)
    )


def info_ask(listing, d):
    return _join(_("%(n)s answers") % {"n": listing.comments_count})


SECTIONS: dict[str, Section] = {
    s.slug: s
    for s in [
        Section(
            "rooms",
            _("Rooms & Hostels"),
            "bed",
            "RoomDetails",
            _("Rooms, hostels and apartments"),
            sensitive=True,
            card_info=info_rooms,
        ),
        Section(
            "roommates",
            _("Roommates"),
            "users",
            "RoommateDetails",
            _("Find or offer a roommate"),
            sensitive=True,
            price_allowed=False,
            card_info=info_roommates,
        ),
        Section(
            "short-stays",
            _("Short stays"),
            "hotel",
            "ShortStayDetails",
            _("Nights and short lets"),
            card_info=info_short_stays,
        ),
        Section(
            "buy-sell",
            _("Buy & Sell"),
            "shopping-bag",
            "ItemDetails",
            _("Phones, laptops, furniture…"),
            students_only_filter=True,
            card_info=info_items,
        ),
        Section(
            "wanted",
            _("Wanted"),
            "search-check",
            "WantedDetails",
            _("Ask for what you need"),
            price_allowed=False,
            card_info=info_wanted,
        ),
        Section(
            "free-leaving",
            _("Free & Leaving"),
            "gift",
            "ItemDetails",
            _("Free things from leavers"),
            price_allowed=False,
            students_only_filter=True,
            card_info=info_free,
        ),
        Section(
            "services",
            _("Services"),
            "wrench",
            "ServiceDetails",
            _("Repairs, printing, hair, laundry"),
            students_only_filter=True,
            card_info=info_services,
        ),
        Section(
            "jobs",
            _("Jobs"),
            "briefcase",
            "JobDetails",
            _("Part-time, internships, gigs"),
            price_allowed=False,
            expiry_field="deadline",
            card_info=info_jobs,
        ),
        Section(
            "job-requests",
            _("Job requests"),
            "hand-helping",
            "JobRequestDetails",
            _("Students offering their skills"),
            price_allowed=False,
            card_info=info_job_requests,
        ),
        Section(
            "errands",
            _("Errands"),
            "bike",
            "ErrandDetails",
            _("Pick-ups, deliveries, queues"),
            expiry_field="deadline",
            card_info=info_errands,
        ),
        Section(
            "food",
            _("Food"),
            "utensils",
            "FoodDetails",
            _("Share extra food, ask for a meal"),
            sensitive=True,
            price_allowed=False,
            expiry_field="available_until",
            card_info=info_food,
        ),
        Section(
            "events",
            _("Events"),
            "calendar",
            "EventDetails",
            _("What's on around campus"),
            expiry_field="ends_at",
            card_info=info_events,
        ),
        Section(
            "notes",
            _("Notes"),
            "book-open",
            "NoteDetails",
            _("Notes and past questions"),
            card_info=info_notes,
        ),
        Section(
            "study",
            _("Study"),
            "graduation-cap",
            "StudyDetails",
            _("Study partners and tutors"),
            card_info=info_study,
        ),
        Section(
            "lost-found",
            _("Lost & Found"),
            "search-x",
            "LostFoundDetails",
            _("Lost something? Found something?"),
            sensitive=True,
            price_allowed=False,
            card_info=info_lost_found,
        ),
        Section(
            "trips",
            _("Trips"),
            "car",
            "TripDetails",
            _("Share rides home"),
            default_enabled=False,
            price_allowed=False,
            expiry_field="departs_at",
            card_info=info_trips,
        ),
        Section(
            "alerts",
            _("Alerts"),
            "triangle-alert",
            "AlertDetails",
            _("Water, power and security alerts"),
            price_allowed=False,
            expiry_field="valid_until",
            card_info=info_alerts,
        ),
        Section(
            "ask",
            _("Ask"),
            "circle-help",
            "QuestionDetails",
            _("Ask other students"),
            price_allowed=False,
            card_info=info_ask,
        ),
    ]
}

SECTION_CHOICES = [(s.slug, s.label) for s in SECTIONS.values()]
SENSITIVE_SECTIONS = {s.slug for s in SECTIONS.values() if s.sensitive}


def get_section(slug: str) -> Section | None:
    return SECTIONS.get(slug)
