from allauth.account.forms import LoginForm, SignupForm
from django import forms
from django.utils.translation import gettext_lazy as _
from phonenumber_field.formfields import PhoneNumberField

from apps.locations.models import Campus, Town

from .models import Profile, User, VerificationRequest
from .turnstile import TurnstileMixin


def _current_request():
    try:
        from allauth.core import context

        return context.request
    except (ImportError, LookupError, AttributeError):
        return None


class KDSignupForm(TurnstileMixin, SignupForm):
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None) or _current_request()
        super().__init__(*args, **kwargs)


class KDLoginForm(TurnstileMixin, LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = getattr(self, "request", None) or _current_request()


class OnboardingForm(forms.Form):
    display_name = forms.CharField(label=_("Display name"), max_length=60)
    role = forms.ChoiceField(
        label=_("I am a…"), choices=Profile.Role.choices, widget=forms.RadioSelect
    )
    seller_type = forms.ChoiceField(
        label=_("I sell as a…"),
        choices=[("", "—")] + list(Profile.SellerType.choices),
        required=False,
    )
    home_campus = forms.ModelChoiceField(
        label=_("My campus"), queryset=Campus.objects.none(), required=False
    )
    home_town = forms.ModelChoiceField(
        label=_("Or my town (not on a campus)"), queryset=Town.objects.none(), required=False
    )
    level = forms.CharField(label=_("Level / year (optional)"), max_length=40, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["home_campus"].queryset = Campus.objects.visible().select_related("town")
        self.fields["home_campus"].label_from_instance = lambda c: c.choice_label
        self.fields["home_town"].queryset = Town.objects.select_related("region")

    def clean(self):
        data = super().clean()
        if not data.get("home_campus") and not data.get("home_town"):
            raise forms.ValidationError(_("Choose your campus or your town."))
        if data.get("role") == Profile.Role.VENDOR and not data.get("seller_type"):
            self.add_error("seller_type", _("Tell buyers if you sell as a student or a business."))
        return data


class ProfileForm(forms.ModelForm):
    display_name = forms.CharField(label=_("Display name"), max_length=60)

    class Meta:
        model = Profile
        fields = ["role", "seller_type", "level", "bio", "avatar"]
        widgets = {"bio": forms.Textarea(attrs={"rows": 3})}


class PhoneForm(forms.Form):
    phone = PhoneNumberField(label=_("Phone number"), region="GH")


class OTPForm(forms.Form):
    code = forms.CharField(
        label=_("6-digit code"),
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}),
    )


class VerificationForm(forms.ModelForm):
    class Meta:
        model = VerificationRequest
        fields = ["kind", "document"]
        help_texts = {
            "document": _(
                "Student ID, admission letter or property document. Stored privately and "
                "deleted as soon as we decide."
            )
        }

    def clean_document(self):
        doc = self.cleaned_data.get("document")
        if not doc:
            raise forms.ValidationError(_("Upload a document."))
        if doc.size > 8 * 1024 * 1024:
            raise forms.ValidationError(_("Maximum 8 MB."))
        name = doc.name.lower()
        if not name.endswith((".pdf", ".jpg", ".jpeg", ".png", ".webp")):
            raise forms.ValidationError(_("Upload a PDF or an image."))
        return doc


class DeleteAccountForm(forms.Form):
    confirm = forms.CharField(label=_('Type "DELETE" to confirm'))

    def clean_confirm(self):
        if self.cleaned_data["confirm"].strip() != "DELETE":
            raise forms.ValidationError(_('Type "DELETE" in capitals.'))
        return "DELETE"


class UserAdminCreationForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email"]
