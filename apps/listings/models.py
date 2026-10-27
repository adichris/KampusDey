from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFit
from taggit.managers import TaggableManager

from apps.core.models import GeoPointMixin, TimeStampedModel
from apps.core.utils import random_filename

from .sections import SECTION_CHOICES, SECTIONS, SENSITIVE_SECTIONS


def listing_photo_upload_to(instance, filename):
    return random_filename(instance, filename, "listings")


def notes_upload_to(instance, filename):
    return random_filename(instance, filename, "notes")


class Category(TimeStampedModel):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    icon = models.CharField(max_length=40, default="package", help_text=_("Lucide icon name"))
    min_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class ItemCategory(Category):
    class Meta(Category.Meta):
        verbose_name_plural = _("item categories")


class ServiceCategory(Category):
    class Meta(Category.Meta):
        verbose_name_plural = _("service categories")


class Listing(GeoPointMixin, TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PENDING_REVIEW = "pending_review", _("Pending review")
        ACTIVE = "active", _("Active")
        NEEDS_CHECK = "needs_check", _("Needs check")
        EXPIRED = "expired", _("Expired")
        ARCHIVED = "archived", _("Archived")
        TAKEN = "taken", _("Taken")

    class PricePeriod(models.TextChoices):
        TOTAL = "total", _("total")
        PER_YEAR = "per_year", _("per year")
        PER_SEMESTER = "per_semester", _("per semester")
        PER_MONTH = "per_month", _("per month")
        PER_NIGHT = "per_night", _("per night")
        PER_HOUR = "per_hour", _("per hour")

    class Visibility(models.TextChoices):
        PUBLIC = "public", _("Anyone can see my contact buttons")
        MEMBERS = "members", _("Only logged-in members")

    VISIBLE_STATUSES = (Status.ACTIVE, Status.NEEDS_CHECK)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listings")
    section = models.CharField(max_length=20, choices=SECTION_CHOICES, db_index=True)
    title = models.CharField(_("title"), max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(_("description"), blank=True, max_length=5000)
    price = models.DecimalField(_("price"), max_digits=12, decimal_places=2, null=True, blank=True)
    price_period = models.CharField(
        max_length=14, choices=PricePeriod.choices, default=PricePeriod.TOTAL, blank=True
    )
    negotiable = models.BooleanField(_("negotiable"), default=False)
    is_free = models.BooleanField(_("free"), default=False)
    town = models.ForeignKey("locations.Town", on_delete=models.PROTECT, related_name="listings")
    area = models.ForeignKey(
        "locations.Area", on_delete=models.SET_NULL, null=True, blank=True, related_name="listings"
    )
    campuses = models.ManyToManyField(
        "locations.Campus", through="ListingCampus", related_name="listings", blank=True
    )
    contact_card = models.ForeignKey(
        "contacts.ContactCard", on_delete=models.SET_NULL, null=True, blank=True, related_name="listings"
    )
    contact_visibility = models.CharField(
        max_length=8, choices=Visibility.choices, default=Visibility.PUBLIC
    )
    hide_number = models.BooleanField(_("hide my phone number (chat only)"), default=False)
    seller_type = models.CharField(max_length=10, blank=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    is_hidden = models.BooleanField(default=False, help_text=_("Hidden pending moderator review"))
    hidden_reason = models.CharField(max_length=200, blank=True)
    wizard_step = models.PositiveSmallIntegerField(default=1)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    needs_check_sent_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(default=0, db_index=True)
    views_7d = models.PositiveIntegerField(default=0)
    taps_7d = models.PositiveIntegerField(default=0)
    likes_7d = models.PositiveIntegerField(default=0)
    likes_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    reports_count = models.PositiveIntegerField(default=0)
    search_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [
            GinIndex(fields=["search_vector"], name="listing_search_gin"),
            models.Index(fields=["section", "status", "-score"], name="listing_section_rank"),
            models.Index(fields=["town", "section", "status"], name="listing_town_section"),
            models.Index(fields=["lat", "lng"], name="listing_latlng"),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("listings:detail", args=[self.slug])

    @property
    def section_obj(self):
        return SECTIONS[self.section]

    @property
    def is_sensitive(self) -> bool:
        return self.section in SENSITIVE_SECTIONS

    @property
    def is_visible(self) -> bool:
        return self.status in self.VISIBLE_STATUSES and not self.is_hidden

    @cached_property
    def details(self):
        section = SECTIONS.get(self.section)
        if not section:
            return None
        try:
            return getattr(self, section.model_name)
        except section.model.DoesNotExist:
            return None

    @property
    def card_info(self) -> str:
        fn = self.section_obj.card_info
        return fn(self, self.details) if fn else ""

    @property
    def first_photo(self):
        photos = getattr(self, "_prefetched_objects_cache", {}).get("photos")
        if photos is not None:
            return photos[0] if photos else None
        return self.photos.order_by("order", "id").first()

    @property
    def is_need_food(self) -> bool:
        details = self.details
        return self.section == "food" and details is not None and details.post_kind == "need_food"

    @property
    def effective_visibility(self) -> str:
        if self.is_need_food:
            return self.Visibility.MEMBERS
        return self.contact_visibility

    def get_price_period_short(self):
        return {
            "per_year": _("yr"),
            "per_semester": _("sem"),
            "per_month": _("mo"),
            "per_night": _("night"),
            "per_hour": _("hr"),
        }.get(self.price_period, "")

    def set_status(self, status, save=True):
        self.status = status
        self.status_changed_at = timezone.now()
        if save:
            self.save(update_fields=["status", "status_changed_at", "updated_at"])


class ListingCampus(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="campus_links")
    campus = models.ForeignKey("locations.Campus", on_delete=models.CASCADE, related_name="listing_links")
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    is_manual = models.BooleanField(default=False)
    is_excluded = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["listing", "campus"], name="uniq_listing_campus")]
        indexes = [models.Index(fields=["campus", "is_excluded"])]

    def __str__(self):
        return f"{self.listing_id} ↔ {self.campus_id}"


class PhotoBase(TimeStampedModel):
    image = models.ImageField(upload_to=listing_photo_upload_to, width_field="width", height_field="height")
    order = models.PositiveSmallIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    phash = models.CharField(max_length=16, blank=True, db_index=True)
    thumb = ImageSpecField(source="image", processors=[ResizeToFit(400, 400)], format="WEBP", options={"quality": 75})
    card = ImageSpecField(source="image", processors=[ResizeToFit(800, 800)], format="WEBP", options={"quality": 78})
    full = ImageSpecField(source="image", processors=[ResizeToFit(1600, 1600)], format="WEBP", options={"quality": 82})

    class Meta:
        abstract = True
        ordering = ["order", "id"]

    def srcset(self):
        try:
            return f"{self.thumb.url} 400w, {self.card.url} 800w, {self.full.url} 1600w"
        except Exception:  # missing source file
            return ""


class ListingPhoto(PhotoBase):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="photos")

    def __str__(self):
        return f"Photo {self.order} of {self.listing_id}"


# ---------------------------------------------------------------------------
# Section details models
# ---------------------------------------------------------------------------
class Gender(models.TextChoices):
    MALE = "male", _("Male")
    FEMALE = "female", _("Female")
    MIXED = "mixed", _("Mixed / any")


class RoomType(models.TextChoices):
    SINGLE = "single", _("Single room")
    TWO_IN_1 = "2_in_1", _("2 in 1")
    THREE_IN_1 = "3_in_1", _("3 in 1")
    FOUR_IN_1 = "4_in_1", _("4 in 1")
    SELF_CONTAINED = "self_contained", _("Self-contained")
    CHAMBER_HALL = "chamber_hall", _("Chamber & hall")


class Details(models.Model):
    listing = models.OneToOneField(Listing, on_delete=models.CASCADE, related_name="%(class)s")

    class Meta:
        abstract = True

    def __str__(self):
        return f"{type(self).__name__} for {self.listing_id}"


class RoomDetails(Details):
    class Water(models.TextChoices):
        FLOWING = "flowing", _("Flowing water")
        TANK = "tank", _("Tank / polytank")
        INTERMITTENT = "intermittent", _("Sometimes")
        NONE = "none", _("No water on site")

    class Washroom(models.TextChoices):
        IN_ROOM = "in_room", _("In room")
        SHARED = "shared", _("Shared")

    room_type = models.CharField(max_length=16, choices=RoomType.choices, default=RoomType.SINGLE)
    gender = models.CharField(max_length=8, choices=Gender.choices, default=Gender.MIXED)
    rooms_per_meter = models.PositiveSmallIntegerField(
        _("rooms sharing one electricity meter"), null=True, blank=True
    )
    water_supply = models.CharField(max_length=14, choices=Water.choices, default=Water.FLOWING)
    washroom = models.CharField(max_length=8, choices=Washroom.choices, default=Washroom.SHARED)
    kitchen = models.BooleanField(_("kitchen"), default=False)
    wifi = models.BooleanField(_("Wi-Fi"), default=False)
    security = models.BooleanField(_("security / gated"), default=False)
    furnished = models.BooleanField(_("furnished"), default=False)
    mattress_included = models.BooleanField(_("mattress included"), default=False)
    available_from = models.DateField(_("available from"), null=True, blank=True)
    hostel_room_type = models.ForeignKey(
        "hostels.HostelRoomType", on_delete=models.SET_NULL, null=True, blank=True, related_name="listings"
    )


class RoommateDetails(Details):
    class Kind(models.TextChoices):
        HAVE_ROOM = "have_room", _("I have a room")
        NEED_ROOM = "need_room", _("I need a room")

    HABITS = [
        ("quiet", _("Quiet")),
        ("social", _("Social")),
        ("early_sleeper", _("Early sleeper")),
        ("late_sleeper", _("Late sleeper")),
        ("very_tidy", _("Very tidy")),
        ("relaxed", _("Relaxed")),
        ("non_smoker", _("Non-smoker")),
    ]

    post_kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.NEED_ROOM)
    gender_pref = models.CharField(max_length=8, choices=Gender.choices, default=Gender.MIXED)
    budget_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    budget_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    level = models.CharField(max_length=40, blank=True)
    move_in_date = models.DateField(null=True, blank=True)
    habits = models.JSONField(default=list, blank=True)

    def get_habits_display(self):
        labels = dict(self.HABITS)
        return [labels.get(h, h) for h in self.habits or []]


class ShortStayDetails(Details):
    room_type = models.CharField(max_length=16, choices=RoomType.choices, default=RoomType.SINGLE)
    available_from = models.DateField(null=True, blank=True)
    available_to = models.DateField(null=True, blank=True)


class Condition(models.TextChoices):
    NEW = "new", _("New")
    LIKE_NEW = "like_new", _("Like new")
    USED = "used", _("Used")


class ItemDetails(Details):
    category = models.ForeignKey(ItemCategory, on_delete=models.SET_NULL, null=True, blank=True)
    condition = models.CharField(max_length=10, choices=Condition.choices, default=Condition.USED)
    pickup_by = models.DateField(_("pick up by"), null=True, blank=True)


class WantedDetails(Details):
    category = models.ForeignKey(ItemCategory, on_delete=models.SET_NULL, null=True, blank=True)
    budget_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    needed_by = models.DateField(null=True, blank=True)


class ServiceDetails(Details):
    service_type = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, null=True, blank=True)
    price_from = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    hours_text = models.CharField(_("opening hours"), max_length=120, blank=True)
    area_served = models.CharField(max_length=120, blank=True)
    place = models.ForeignKey(
        "external.Place", on_delete=models.SET_NULL, null=True, blank=True, related_name="service_listings"
    )


class JobDetails(Details):
    class JobType(models.TextChoices):
        PART_TIME = "part_time", _("Part-time")
        INTERNSHIP = "internship", _("Internship")
        ATTACHMENT = "attachment", _("Attachment")
        GIG = "gig", _("Gig")
        FULL_TIME = "full_time", _("Full-time")

    job_type = models.CharField(max_length=12, choices=JobType.choices, default=JobType.PART_TIME)
    pay_text = models.CharField(_("pay"), max_length=80, blank=True)
    hours_text = models.CharField(_("hours"), max_length=80, blank=True)
    deadline = models.DateField(null=True, blank=True)
    how_to_apply = models.TextField(blank=True, max_length=1000)
    apply_url = models.URLField(blank=True)


class JobRequestDetails(Details):
    skills = TaggableManager(blank=True)
    availability = models.CharField(max_length=120, blank=True)
    expected_pay = models.CharField(max_length=80, blank=True)


class ErrandDetails(Details):
    deadline = models.DateTimeField(null=True, blank=True)
    pickup_area = models.CharField(max_length=120, blank=True)
    dropoff_area = models.CharField(max_length=120, blank=True)


class FoodDetails(Details):
    class Kind(models.TextChoices):
        EXTRA_FOOD = "extra_food", _("I have extra food")
        NEED_FOOD = "need_food", _("I need food")

    post_kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.EXTRA_FOOD)
    pickup_from = models.CharField(max_length=120, blank=True)
    available_until = models.DateTimeField()
    food_note = models.CharField(max_length=200, blank=True)


class EventDetails(Details):
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    venue = models.CharField(max_length=160)
    organiser = models.CharField(max_length=120, blank=True)
    ticket_info = models.CharField(max_length=160, blank=True)


class NoteDetails(Details):
    class Format(models.TextChoices):
        FILE = "file", _("File (PDF)")
        PHYSICAL = "physical", _("Physical copy")
        BOTH = "both", _("Both")

    course_code = models.CharField(max_length=20)
    course_title = models.CharField(max_length=160, blank=True)
    level = models.CharField(max_length=40, blank=True)
    format = models.CharField(max_length=10, choices=Format.choices, default=Format.PHYSICAL)
    file = models.FileField(
        upload_to=notes_upload_to, null=True, blank=True, validators=[FileExtensionValidator(["pdf"])]
    )


class StudyDetails(Details):
    class Kind(models.TextChoices):
        STUDY_PARTNER = "study_partner", _("Study partner")
        TUTOR = "tutor", _("Tutor")

    class Mode(models.TextChoices):
        ONLINE = "online", _("Online")
        IN_PERSON = "in_person", _("In person")

    kind = models.CharField(max_length=14, choices=Kind.choices, default=Kind.STUDY_PARTNER)
    course_code = models.CharField(max_length=20, blank=True)
    level = models.CharField(max_length=40, blank=True)
    schedule_text = models.CharField(max_length=120, blank=True)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.IN_PERSON)


class LostFoundDetails(Details):
    class Kind(models.TextChoices):
        LOST = "lost", _("Lost")
        FOUND = "found", _("Found")

    kind = models.CharField(max_length=6, choices=Kind.choices, default=Kind.LOST)
    item_type = models.CharField(max_length=80)
    happened_at = models.DateTimeField(null=True, blank=True)


class TripDetails(Details):
    origin_town = models.ForeignKey("locations.Town", on_delete=models.PROTECT, related_name="+")
    destination_town = models.ForeignKey("locations.Town", on_delete=models.PROTECT, related_name="+")
    departs_at = models.DateTimeField()
    seats_available = models.PositiveSmallIntegerField(default=1)
    cost_share = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)


class AlertDetails(Details):
    class AlertType(models.TextChoices):
        WATER = "water", _("Water")
        POWER = "power", _("Power")
        SECURITY = "security", _("Security")
        VENUE_CHANGE = "venue_change", _("Venue change")
        OTHER = "other", _("Other")

    alert_type = models.CharField(max_length=14, choices=AlertType.choices, default=AlertType.OTHER)
    valid_until = models.DateTimeField()


class QuestionDetails(Details):
    tags = TaggableManager(blank=True)
