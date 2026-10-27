import secrets

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.models import TimeStampedModel
from apps.core.utils import random_filename


def _alias_number():
    return secrets.randbelow(9000) + 1000


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra)


def avatar_upload_to(instance, filename):
    return random_filename(instance, filename, "avatars")


class User(AbstractUser):
    username = None
    first_name = None
    last_name = None
    email = models.EmailField(_("email address"), unique=True)
    display_name = models.CharField(_("display name"), max_length=60, blank=True)
    phone = PhoneNumberField(_("phone"), null=True, blank=True, unique=True)
    phone_verified = models.BooleanField(default=False)
    theme = models.CharField(max_length=30, default="system")
    alias_number = models.PositiveSmallIntegerField(default=_alias_number)
    onboarded = models.BooleanField(default=False)
    is_anonymised = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.display_name or self.email

    @property
    def public_name(self):
        return self.display_name or _("KampusDey user")

    @property
    def email_verified(self) -> bool:
        from allauth.account.models import EmailAddress

        return EmailAddress.objects.filter(user=self, verified=True).exists()

    @property
    def account_age_hours(self) -> float:
        return (timezone.now() - self.date_joined).total_seconds() / 3600


class Profile(TimeStampedModel):
    class Role(models.TextChoices):
        STUDENT = "student", _("Student")
        LANDLORD = "landlord", _("Landlord")
        AGENT = "agent", _("Agent")
        VENDOR = "vendor", _("Vendor / business")
        EMPLOYER = "employer", _("Employer")
        OTHER = "other", _("Other")

    class SellerType(models.TextChoices):
        STUDENT = "student", _("Student seller")
        BUSINESS = "business", _("Business")

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    seller_type = models.CharField(max_length=10, choices=SellerType.choices, null=True, blank=True)
    home_campus = models.ForeignKey(
        "locations.Campus", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    home_town = models.ForeignKey(
        "locations.Town", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    followed_campuses = models.ManyToManyField(
        "locations.Campus", blank=True, related_name="followers"
    )
    level = models.CharField(_("level / year"), max_length=40, blank=True)
    bio = models.TextField(blank=True, max_length=600)
    avatar = models.ImageField(upload_to=avatar_upload_to, null=True, blank=True)
    is_ambassador = models.BooleanField(default=False)
    referral_code = models.CharField(max_length=12, unique=True, null=True, blank=True)
    bonus_boosts = models.PositiveSmallIntegerField(default=0)
    verified_student = models.BooleanField(default=False)
    verified_student_at = models.DateTimeField(null=True, blank=True)
    verified_landlord = models.BooleanField(default=False)
    verified_landlord_at = models.DateTimeField(null=True, blank=True)
    verified_agent = models.BooleanField(default=False)
    verified_agent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Profile of {self.user}"

    @property
    def is_verified(self) -> bool:
        return self.verified_student or self.verified_landlord or self.verified_agent

    @property
    def effective_seller_type(self):
        if self.seller_type:
            return self.seller_type
        return (
            self.SellerType.STUDENT if self.role == self.Role.STUDENT else self.SellerType.BUSINESS
        )


def verification_upload_to(instance, filename):
    return random_filename(instance, filename, "verification")


def private_storage():
    from django.core.files.storage import storages

    return storages["private"]


class VerificationRequest(TimeStampedModel):
    class Kind(models.TextChoices):
        STUDENT = "student", _("Student")
        LANDLORD = "landlord", _("Landlord")
        AGENT = "agent", _("Agent")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="verification_requests")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    document = models.FileField(
        storage=private_storage,
        upload_to=verification_upload_to,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} verification for {self.user}"


class PhoneOTP(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="phone_otps")
    phone = PhoneNumberField()
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.phone}"
