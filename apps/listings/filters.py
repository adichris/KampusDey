"""django-filter FilterSets per section."""

import django_filters as df
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import (
    AlertDetails,
    Condition,
    FoodDetails,
    Gender,
    ItemCategory,
    JobDetails,
    Listing,
    LostFoundDetails,
    NoteDetails,
    RoomDetails,
    RoommateDetails,
    RoomType,
    ServiceCategory,
    StudyDetails,
)


class CheckFilter(df.BooleanFilter):
    """Checkbox filter: ticked narrows the results, unticked means 'any'."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", forms.CheckboxInput)
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        return super().filter(qs, True) if value else qs


class BaseListingFilter(df.FilterSet):
    price_min = df.NumberFilter(field_name="price", lookup_expr="gte", label=_("Min price"))
    price_max = df.NumberFilter(field_name="price", lookup_expr="lte", label=_("Max price"))

    class Meta:
        model = Listing
        fields = []


class StudentsOnlyMixin(df.FilterSet):
    students_only = df.BooleanFilter(
        method="filter_students_only", label=_("Students only"), widget=forms.CheckboxInput
    )

    def filter_students_only(self, queryset, name, value):
        return queryset.filter(seller_type="student") if value else queryset


def _choice(field, choices, label):
    return df.ChoiceFilter(field_name=field, choices=choices, label=label, empty_label=_("Any"))


class RoomsFilter(BaseListingFilter):
    room_type = _choice("roomdetails__room_type", RoomType.choices, _("Room type"))
    gender = _choice("roomdetails__gender", Gender.choices, _("Gender"))
    water = _choice("roomdetails__water_supply", RoomDetails.Water.choices, _("Water"))
    furnished = CheckFilter(field_name="roomdetails__furnished", label=_("Furnished"))
    wifi = CheckFilter(field_name="roomdetails__wifi", label=_("Wi-Fi"))


class RoommatesFilter(df.FilterSet):
    post_kind = _choice(
        "roommatedetails__post_kind", RoommateDetails.Kind.choices, _("Looking for")
    )
    gender = _choice("roommatedetails__gender_pref", Gender.choices, _("Gender"))

    class Meta:
        model = Listing
        fields = []


class ShortStaysFilter(BaseListingFilter):
    room_type = _choice("shortstaydetails__room_type", RoomType.choices, _("Room type"))


class ItemsFilter(StudentsOnlyMixin, BaseListingFilter):
    category = df.ModelChoiceFilter(
        field_name="itemdetails__category",
        queryset=ItemCategory.objects.filter(is_active=True),
        label=_("Category"),
        empty_label=_("Any"),
    )
    condition = _choice("itemdetails__condition", Condition.choices, _("Condition"))


class FreeFilter(StudentsOnlyMixin, df.FilterSet):
    category = df.ModelChoiceFilter(
        field_name="itemdetails__category",
        queryset=ItemCategory.objects.filter(is_active=True),
        label=_("Category"),
        empty_label=_("Any"),
    )

    class Meta:
        model = Listing
        fields = []


class WantedFilter(df.FilterSet):
    category = df.ModelChoiceFilter(
        field_name="wanteddetails__category",
        queryset=ItemCategory.objects.filter(is_active=True),
        label=_("Category"),
        empty_label=_("Any"),
    )

    class Meta:
        model = Listing
        fields = []


class ServicesFilter(StudentsOnlyMixin, df.FilterSet):
    service_type = df.ModelChoiceFilter(
        field_name="servicedetails__service_type",
        queryset=ServiceCategory.objects.filter(is_active=True),
        label=_("Service"),
        empty_label=_("Any"),
    )

    class Meta:
        model = Listing
        fields = []


class JobsFilter(df.FilterSet):
    job_type = _choice("jobdetails__job_type", JobDetails.JobType.choices, _("Job type"))

    class Meta:
        model = Listing
        fields = []


class FoodFilter(df.FilterSet):
    post_kind = _choice("fooddetails__post_kind", FoodDetails.Kind.choices, _("Kind"))

    class Meta:
        model = Listing
        fields = []


class EventsFilter(df.FilterSet):
    starts_after = df.DateFilter(
        field_name="eventdetails__starts_at",
        lookup_expr="date__gte",
        label=_("From"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = Listing
        fields = []


class NotesFilter(BaseListingFilter):
    course_code = df.CharFilter(
        field_name="notedetails__course_code", lookup_expr="icontains", label=_("Course code")
    )
    format = _choice("notedetails__format", NoteDetails.Format.choices, _("Format"))


class StudyFilter(df.FilterSet):
    kind = _choice("studydetails__kind", StudyDetails.Kind.choices, _("Looking for"))
    mode = _choice("studydetails__mode", StudyDetails.Mode.choices, _("Mode"))
    course_code = df.CharFilter(
        field_name="studydetails__course_code", lookup_expr="icontains", label=_("Course code")
    )

    class Meta:
        model = Listing
        fields = []


class LostFoundFilter(df.FilterSet):
    kind = _choice("lostfounddetails__kind", LostFoundDetails.Kind.choices, _("Lost or found"))

    class Meta:
        model = Listing
        fields = []


class TripsFilter(df.FilterSet):
    destination = df.CharFilter(
        field_name="tripdetails__destination_town__name",
        lookup_expr="icontains",
        label=_("Destination"),
    )

    class Meta:
        model = Listing
        fields = []


class AlertsFilter(df.FilterSet):
    alert_type = _choice(
        "alertdetails__alert_type", AlertDetails.AlertType.choices, _("Alert type")
    )

    class Meta:
        model = Listing
        fields = []


class TagFilter(df.FilterSet):
    tag = df.CharFilter(method="filter_tag", label=_("Tag"))
    tag_path = ""

    class Meta:
        model = Listing
        fields = []

    def filter_tag(self, queryset, name, value):
        return queryset.filter(**{f"{self.tag_path}__name__iexact": value}) if value else queryset


class AskFilter(TagFilter):
    tag_path = "questiondetails__tags"


class JobRequestsFilter(TagFilter):
    tag_path = "jobrequestdetails__skills"


class ErrandsFilter(BaseListingFilter):
    pass


FILTERS = {
    "rooms": RoomsFilter,
    "roommates": RoommatesFilter,
    "short-stays": ShortStaysFilter,
    "buy-sell": ItemsFilter,
    "wanted": WantedFilter,
    "free-leaving": FreeFilter,
    "services": ServicesFilter,
    "jobs": JobsFilter,
    "job-requests": JobRequestsFilter,
    "errands": ErrandsFilter,
    "food": FoodFilter,
    "events": EventsFilter,
    "notes": NotesFilter,
    "study": StudyFilter,
    "lost-found": LostFoundFilter,
    "trips": TripsFilter,
    "alerts": AlertsFilter,
    "ask": AskFilter,
}


def filter_for(section: str):
    return FILTERS.get(section, BaseListingFilter)


def active_filters(filterset, params) -> list[tuple[str, str, str]]:
    """[(label, shown value, query string without it)] for the 'active filter' chips."""
    if not filterset.is_bound or not filterset.is_valid():
        return []
    from apps.core.templatetags.kd import ghs

    out = []
    for name, field in filterset.form.fields.items():
        value = filterset.form.cleaned_data.get(name)
        if value in (None, "", [], False) or name not in params:
            continue
        if name in ("price_min", "price_max"):
            shown = ghs(value)
        elif isinstance(value, (list, tuple)):
            choices = dict(getattr(field, "choices", []))
            shown = ", ".join(str(choices.get(v, v)) for v in value)
        elif value is True:
            shown = ""
        elif getattr(field, "choices", None) and not hasattr(value, "pk"):
            shown = str(dict(field.choices).get(value, value))
        else:
            shown = str(value)
        rest = params.copy()
        rest.pop(name, None)
        rest.pop("page", None)
        out.append((str(field.label), shown, rest.urlencode()))
    return out
