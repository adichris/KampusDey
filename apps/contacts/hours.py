"""'Best time to contact' as a day choice plus a time range.

Stored compactly on ContactCard.preferred_time as e.g. ``"weekdays 17:00-20:00"`` so it
renders in the viewer's language. Older free-text values are shown as typed.
"""

import re
from datetime import time

from django.utils.formats import time_format
from django.utils.translation import gettext_lazy as _

DAY_CHOICES = [
    ("any", _("Any day")),
    ("weekdays", _("Weekdays")),
    ("weekends", _("Weekends")),
    ("mon-sat", _("Monday to Saturday")),
]
DAY_LABELS = dict(DAY_CHOICES)

_STORED = re.compile(r"^(any|weekdays|weekends|mon-sat)(?: (\d\d:\d\d)-(\d\d:\d\d))?$")


def _label(hhmm: str) -> str:
    return time_format(time.fromisoformat(hhmm), "g:i A")


def time_choices(start_hour=5, end_hour=23):
    """Half-hour steps from 5:00 AM to 11:00 PM."""
    out = []
    for hour in range(start_hour, end_hour + 1):
        for minute in (0, 30):
            if hour == end_hour and minute:
                break
            value = f"{hour:02d}:{minute:02d}"
            out.append((value, _label(value)))
    return out


def compose(days: str, start: str, end: str) -> str:
    if not start or not end:
        return "" if days in ("", "any") else days
    return f"{days or 'any'} {start}-{end}"


def parse(stored: str) -> dict | None:
    """Split a stored value into form fields; None when it is old free text."""
    match = _STORED.match(stored or "")
    if not match:
        return None
    days, start, end = match.groups()
    return {"contact_days": days, "contact_from": start or "", "contact_to": end or ""}


def display(stored: str) -> str:
    parts = parse(stored)
    if parts is None:
        return stored or ""
    days = parts["contact_days"]
    text = (
        f"{_label(parts['contact_from'])} – {_label(parts['contact_to'])}"
        if parts["contact_from"]
        else ""
    )
    if days == "any":
        return text
    return f"{DAY_LABELS[days]}, {text}" if text else str(DAY_LABELS[days])
