from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.contacts import hours
from apps.locations.models import Area, Campus, Town

from . import models as m


class DateInput(forms.DateInput):
    input_type = "date"


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def format_value(self, value):
        if hasattr(value, "strftime"):
            return (
                timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")
                if timezone.is_aware(value)
                else value.strftime("%Y-%m-%dT%H:%M")
            )
        return value


DT_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]


def dt_field(**kwargs):
    return forms.DateTimeField(widget=DateTimeInput(), input_formats=DT_FORMATS, **kwargs)


class CommonForm(forms.ModelForm):
    lat = forms.FloatField(required=False, widget=forms.HiddenInput)
    lng = forms.FloatField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = m.Listing
        fields = ["title", "description", "price", "price_period", "negotiable", "area"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "price": forms.NumberInput(attrs={"inputmode": "decimal", "min": "0", "step": "0.01"}),
        }

    def __init__(self, *args, section=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.section = section
        self.fields["title"].widget.attrs.update({"maxlength": 120, "autocomplete": "off"})
        listing = self.instance
        self.fields["area"].queryset = (
            Area.objects.visible().filter(town=listing.town)
            if listing.town_id
            else Area.objects.none()
        )
        self.fields["area"].required = False
        if listing.has_point and not self.is_bound:
            self.initial.update(lat=listing.lat, lng=listing.lng)
        if section and not section.price_allowed:
            for name in ("price", "price_period", "negotiable"):
                self.fields.pop(name, None)
        elif section and section.slug in ("buy-sell", "services", "notes", "errands", "wanted"):
            self.fields["price_period"].initial = "total"

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if len(title) < 4:
            raise forms.ValidationError(_("Give it a clear title (at least 4 characters)."))
        return title

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is not None and price < 0:
            raise forms.ValidationError(_("Price cannot be negative."))
        return price


class RoomDetailsForm(forms.ModelForm):
    class Meta:
        model = m.RoomDetails
        exclude = ["listing", "hostel_room_type"]
        widgets = {"available_from": DateInput()}


class RoommateDetailsForm(forms.ModelForm):
    habits = forms.MultipleChoiceField(
        choices=m.RoommateDetails.HABITS, widget=forms.CheckboxSelectMultiple, required=False
    )

    class Meta:
        model = m.RoommateDetails
        exclude = ["listing"]
        widgets = {"move_in_date": DateInput()}

    def clean(self):
        data = super().clean()
        lo, hi = data.get("budget_min"), data.get("budget_max")
        if lo is not None and hi is not None and lo > hi:
            self.add_error("budget_max", _("Maximum must be above minimum."))
        return data


class ShortStayDetailsForm(forms.ModelForm):
    class Meta:
        model = m.ShortStayDetails
        exclude = ["listing"]
        widgets = {"available_from": DateInput(), "available_to": DateInput()}


class ItemDetailsForm(forms.ModelForm):
    class Meta:
        model = m.ItemDetails
        fields = ["category", "condition"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = m.ItemCategory.objects.filter(is_active=True)
        self.fields["category"].required = True


class FreeItemDetailsForm(ItemDetailsForm):
    class Meta:
        model = m.ItemDetails
        fields = ["category", "condition", "pickup_by"]
        widgets = {"pickup_by": DateInput()}


class WantedDetailsForm(forms.ModelForm):
    class Meta:
        model = m.WantedDetails
        exclude = ["listing"]
        widgets = {"needed_by": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = m.ItemCategory.objects.filter(is_active=True)


class ServiceDetailsForm(forms.ModelForm):
    class Meta:
        model = m.ServiceDetails
        exclude = ["listing", "place"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service_type"].queryset = m.ServiceCategory.objects.filter(is_active=True)
        self.fields["service_type"].required = True


class JobDetailsForm(forms.ModelForm):
    class Meta:
        model = m.JobDetails
        exclude = ["listing"]
        widgets = {"deadline": DateInput(), "how_to_apply": forms.Textarea(attrs={"rows": 3})}


class JobRequestDetailsForm(forms.ModelForm):
    class Meta:
        model = m.JobRequestDetails
        exclude = ["listing"]
        help_texts = {"skills": _("Comma separated, e.g. typing, graphic design")}


class ErrandDetailsForm(forms.ModelForm):
    deadline = dt_field(required=False)

    class Meta:
        model = m.ErrandDetails
        exclude = ["listing"]


class FoodDetailsForm(forms.ModelForm):
    available_until = dt_field(label=_("Available until"))

    class Meta:
        model = m.FoodDetails
        exclude = ["listing"]

    def clean_available_until(self):
        from datetime import timedelta

        from constance import config

        value = self.cleaned_data["available_until"]
        now = timezone.now()
        if value <= now:
            raise forms.ValidationError(_("Choose a time in the future."))
        if value > now + timedelta(hours=config.FOOD_POST_MAX_HOURS):
            raise forms.ValidationError(
                _("Food posts can stay up for at most %(h)s hours.")
                % {"h": config.FOOD_POST_MAX_HOURS}
            )
        return value


class EventDetailsForm(forms.ModelForm):
    starts_at = dt_field(label=_("Starts"))
    ends_at = dt_field(label=_("Ends"), required=False)

    class Meta:
        model = m.EventDetails
        exclude = ["listing"]

    def clean(self):
        data = super().clean()
        if data.get("ends_at") and data.get("starts_at") and data["ends_at"] < data["starts_at"]:
            self.add_error("ends_at", _("The end must be after the start."))
        return data


class NoteDetailsForm(forms.ModelForm):
    class Meta:
        model = m.NoteDetails
        exclude = ["listing"]

    def clean_file(self):
        from django.conf import settings

        upload = self.cleaned_data.get("file")
        if upload and hasattr(upload, "read"):
            if upload.size > settings.NOTES_MAX_PDF_MB * 1024 * 1024:
                raise forms.ValidationError(_("PDF is too large."))
            head = upload.read(5)
            upload.seek(0)
            if head != b"%PDF-":
                raise forms.ValidationError(_("Only PDF files are allowed."))
        return upload


class StudyDetailsForm(forms.ModelForm):
    class Meta:
        model = m.StudyDetails
        exclude = ["listing"]


class LostFoundDetailsForm(forms.ModelForm):
    happened_at = dt_field(label=_("When"), required=False)

    class Meta:
        model = m.LostFoundDetails
        exclude = ["listing"]


class TripDetailsForm(forms.ModelForm):
    departs_at = dt_field(label=_("Departs"))

    class Meta:
        model = m.TripDetails
        exclude = ["listing"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        towns = Town.objects.select_related("region")
        self.fields["origin_town"].queryset = towns
        self.fields["destination_town"].queryset = towns


class AlertDetailsForm(forms.ModelForm):
    valid_until = dt_field(label=_("Valid until"))

    class Meta:
        model = m.AlertDetails
        exclude = ["listing"]


class QuestionDetailsForm(forms.ModelForm):
    class Meta:
        model = m.QuestionDetails
        exclude = ["listing"]


DETAILS_FORMS = {
    "rooms": RoomDetailsForm,
    "roommates": RoommateDetailsForm,
    "short-stays": ShortStayDetailsForm,
    "buy-sell": ItemDetailsForm,
    "wanted": WantedDetailsForm,
    "free-leaving": FreeItemDetailsForm,
    "services": ServiceDetailsForm,
    "jobs": JobDetailsForm,
    "job-requests": JobRequestDetailsForm,
    "errands": ErrandDetailsForm,
    "food": FoodDetailsForm,
    "events": EventDetailsForm,
    "notes": NoteDetailsForm,
    "study": StudyDetailsForm,
    "lost-found": LostFoundDetailsForm,
    "trips": TripDetailsForm,
    "alerts": AlertDetailsForm,
    "ask": QuestionDetailsForm,
}


class ContactStepForm(forms.Form):
    whatsapp = forms.CharField(
        label="WhatsApp",
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={"inputmode": "tel", "placeholder": "024 000 0000"}),
    )
    phone = forms.CharField(
        label=_("Phone for calls"),
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={"inputmode": "tel"}),
    )
    telegram = forms.CharField(label=_("Telegram username"), required=False, max_length=40)
    email_relay = forms.BooleanField(
        label=_("Allow email messages (relayed, your address stays hidden)"), required=False
    )
    chat = forms.BooleanField(label=_("Allow in-app chat"), required=False, initial=True)
    preferred_channel = forms.ChoiceField(
        label=_("Main contact button"),
        help_text=_("Shown first and largest on your listing. The others stay available."),
        choices=[
            ("chat", _("In-app chat (your number stays private)")),
            ("whatsapp", "WhatsApp"),
            ("phone", _("Phone call")),
            ("telegram", "Telegram"),
            ("email", _("Email")),
        ],
        initial="chat",
        required=False,
        widget=forms.RadioSelect,
    )
    contact_days = forms.ChoiceField(
        label=_("Days"),
        choices=hours.DAY_CHOICES,
        required=False,
        widget=forms.Select(attrs={"data-no-search": ""}),
    )
    contact_from = forms.ChoiceField(label=_("From"), required=False)
    contact_to = forms.ChoiceField(label=_("To"), required=False)
    contact_visibility = forms.ChoiceField(
        label=_("Who can see contact buttons"),
        choices=m.Listing.Visibility.choices,
        widget=forms.RadioSelect,
    )
    hide_number = forms.BooleanField(label=_("Hide my number — chat only"), required=False)
    keep_campuses = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple, label=_("Show on these campuses")
    )
    add_campus = forms.ModelChoiceField(
        queryset=Campus.objects.none(), required=False, label=_("Add another campus")
    )

    def __init__(self, *args, listing=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.listing = listing
        links = list(listing.campus_links.select_related("campus")) if listing else []
        self.fields["keep_campuses"].choices = [
            (str(link.campus_id), str(link.campus)) for link in links
        ]
        if not self.is_bound:
            self.initial["keep_campuses"] = [
                str(link.campus_id) for link in links if not link.is_excluded
            ]
        times = [("", _("Any time"))] + hours.time_choices()
        for name in ("contact_from", "contact_to"):
            self.fields[name].choices = times
            self.fields[name].widget.attrs["data-no-search"] = ""
        stored = self.initial.get("preferred_time", "")
        parts = hours.parse(stored)
        self.legacy_time = stored if parts is None else ""
        if parts and not self.is_bound:
            self.initial.update(parts)
        self.fields["add_campus"].queryset = Campus.objects.visible().select_related("town")
        self.fields["add_campus"].label_from_instance = lambda c: c.choice_label
        if listing and listing.is_need_food:
            self.fields["contact_visibility"].choices = [
                ("members", m.Listing.Visibility.MEMBERS.label)
            ]

    def clean(self):
        from phonenumber_field.phonenumber import PhoneNumber

        data = super().clean()
        for name in ("whatsapp", "phone"):
            raw = (data.get(name) or "").strip()
            if raw:
                number = PhoneNumber.from_string(raw, region="GH")
                if not number.is_valid():
                    self.add_error(name, _("Enter a valid phone number."))
                else:
                    data[name] = number.as_e164
        start, end = data.get("contact_from"), data.get("contact_to")
        if bool(start) != bool(end):
            self.add_error("contact_to", _("Choose both a start and an end time."))
        elif start and end <= start:
            self.add_error("contact_to", _("The end time must be after the start time."))
        new_time = hours.compose(data.get("contact_days") or "any", start, end)
        # an older free-text answer stays until a day or range is picked
        data["preferred_time"] = new_time or self.legacy_time
        tg = (data.get("telegram") or "").strip().lstrip("@")
        if tg and not tg.replace("_", "").isalnum():
            self.add_error("telegram", _("Telegram usernames use letters, numbers and _."))
        data["telegram"] = tg
        if not any(
            [
                data.get("whatsapp"),
                data.get("phone") and not data.get("hide_number"),
                tg,
                data.get("email_relay"),
                data.get("chat"),
            ]
        ):
            raise forms.ValidationError(_("Choose at least one way to be contacted."))
        enabled = {
            "chat": data.get("chat"),
            "whatsapp": data.get("whatsapp"),
            "phone": data.get("phone") and not data.get("hide_number"),
            "telegram": tg,
            "email": data.get("email_relay"),
        }
        if not data.get("preferred_channel"):
            data["preferred_channel"] = next((k for k, on in enabled.items() if on), "")
        elif not enabled.get(data["preferred_channel"]):
            self.add_error(
                "preferred_channel", _("Turn this way of contact on, or pick another one.")
            )
        return data
