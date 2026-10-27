"""KampusDey template tags and filters (loaded as builtins)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from apps.core.geo import walking_minutes

register = template.Library()
ICON_DIR = Path(__file__).resolve().parent.parent / "icons"


@register.filter
def ghs(value, decimals: int = 0):
    """Format an amount as Ghana cedis: GH₵ 1,200."""
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    decimals = int(decimals)
    if decimals == 0 and amount != amount.to_integral_value():
        decimals = 2
    return f"GH₵ {amount:,.{decimals}f}"


@lru_cache(maxsize=256)
def _icon_body(name: str) -> str:
    path = ICON_DIR / f"{name}.svg"
    if not path.exists():
        path = ICON_DIR / "circle-help.svg"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"<svg[^>]*>(.*)</svg>", text, re.S)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


@register.simple_tag
def icon(name: str, cls: str = "size-5", label: str = ""):
    """Inline a Lucide icon. Decorative unless a label is given."""
    aria = format_html('role="img" aria-label="{}"', label) if label else 'aria-hidden="true"'
    return mark_safe(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'class="{cls}" {aria}>{_icon_body(name)}</svg>'
    )


@register.filter
def walk_minutes(distance_m):
    from constance import config

    minutes = walking_minutes(distance_m, config.WALKING_M_PER_MIN)
    if minutes is None:
        return ""
    return _("%(n)s min walk") % {"n": minutes}


@register.filter
def distance(distance_m):
    if distance_m is None:
        return ""
    if distance_m < 1000:
        return f"{int(round(distance_m, -1))} m"
    return f"{distance_m / 1000:.1f} km"


@register.filter
def ago(value):
    """Compact age for cards: 'now', '5m', '3h', '2d', '4w', '7 Mar'."""
    if not value:
        return ""
    from django.utils import timezone
    from django.utils.formats import date_format

    seconds = (timezone.now() - value).total_seconds()
    if seconds < 60:
        return _("now")
    for limit, size, unit in ((3600, 60, _("m")), (86400, 3600, _("h")), (604800, 86400, _("d"))):
        if seconds < limit:
            return f"{int(seconds // size)}{unit}"
    if seconds < 8 * 604800:
        return f"{int(seconds // 604800)}{_('w')}"
    return date_format(timezone.localtime(value), "j M")


@register.simple_tag
def cfg(key: str):
    from constance import config

    return getattr(config, key)


@register.simple_tag(takes_context=True)
def qs(context, **kwargs):
    """Return the current query string with the given keys replaced (None removes)."""
    request = context["request"]
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    params.pop("page", None) if "page" not in kwargs else None
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def split(value: str, sep: str = ","):
    return [part.strip() for part in (value or "").split(sep) if part.strip()]


@register.filter
def initials(value: str):
    parts = [p for p in (value or "").split() if p]
    return "".join(p[0].upper() for p in parts[:2]) or "K"


@register.filter
def absolute(path: str):
    from django.conf import settings

    if not path:
        return settings.SITE_URL
    if path.startswith("http"):
        return path
    return f"{settings.SITE_URL}{path}"


WIDGET_CLASSES = {
    "checkbox": "checkbox checkbox-primary",
    "radio": "radio radio-primary",
    "select": "select select-bordered w-full",
    "selectmultiple": "select select-bordered w-full",
    "textarea": "textarea textarea-bordered w-full",
    "file": "file-input file-input-bordered w-full",
    "clearablefile": "file-input file-input-bordered w-full",
}


@register.simple_tag
def widget(field, extra: str = ""):
    """Render a form field's widget with daisyUI classes."""
    name = type(field.field.widget).__name__.lower().replace("input", "").replace("widget", "")
    if name in ("checkboxselectmultiple", "radioselect"):
        return field.as_widget()
    css = WIDGET_CLASSES.get(name, "input input-bordered w-full")
    attrs = {"class": f"{css} {extra}".strip()}
    if field.errors:
        attrs["aria-invalid"] = "true"
        attrs["class"] += " input-error" if css.startswith("input") else ""
    if field.help_text:
        attrs["aria-describedby"] = f"{field.auto_id}_help"
    return field.as_widget(attrs=attrs)


@register.filter
def is_checkbox(field):
    return type(field.field.widget).__name__ == "CheckboxInput"


@register.filter
def is_multi(field):
    return type(field.field.widget).__name__ in ("CheckboxSelectMultiple", "RadioSelect")


@register.filter
def json_attr(value):
    import json

    return json.dumps(value)


SKIP_FACT_FIELDS = {"id", "listing", "hostel_room_type", "file", "place"}


@register.filter
def detail_facts(details):
    """[(label, value)] for a section details object, for the 'key facts' chips."""
    from django.db import models as dj_models
    from django.utils import formats, timezone

    if details is None:
        return []
    facts = []
    for field in details._meta.get_fields():
        if not getattr(field, "concrete", False) or field.name in SKIP_FACT_FIELDS:
            continue
        if isinstance(field, dj_models.BooleanField):
            if getattr(details, field.name):
                facts.append(("", str(field.verbose_name).capitalize()))
            continue
        value = getattr(details, field.name, None)
        if value in (None, "", []):
            continue
        if field.choices:
            value = getattr(details, f"get_{field.name}_display")()
        elif isinstance(field, dj_models.DateTimeField):
            value = formats.date_format(timezone.localtime(value), "D j M, H:i")
        elif isinstance(field, dj_models.DateField):
            value = formats.date_format(value, "j M Y")
        elif isinstance(field, dj_models.DecimalField):
            value = ghs(value)
        elif isinstance(field, dj_models.JSONField) and field.name == "habits":
            value = ", ".join(str(v) for v in details.get_habits_display())
        facts.append((str(field.verbose_name).capitalize(), value))
    for m2m in ("skills", "tags"):
        manager = getattr(details, m2m, None)
        if manager is not None and hasattr(manager, "names"):
            names = list(manager.names())
            if names:
                facts.append((m2m.capitalize(), ", ".join(names)))
    return facts


@register.filter
def alias_other(conversation, user):
    return (
        conversation.owner_alias
        if conversation.starter_id == user.pk
        else conversation.starter_alias
    )
