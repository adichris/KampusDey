"""factory_boy factories for every model. Test data only — clearly fake."""

from datetime import timedelta

import factory
from allauth.account.models import EmailAddress
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.models import PhoneOTP, Profile, User, VerificationRequest
from apps.boosts.models import Boost
from apps.chat.models import Block, Conversation, Message
from apps.contacts.models import ContactCard, ContactChannel
from apps.engagement.models import Comment, Like, Report, Review, SavedSearch
from apps.external.models import ExternalJob, ExternalRun, ExternalSource, Place, PlaceCampus, PlaceClaim
from apps.growth.models import Referral, Spotlight
from apps.hostels.models import Hostel, HostelPhoto, HostelRoomType
from apps.listings import models as lm
from apps.locations.models import Area, Campus, CampusRequest, District, ImportLog, Institution, Region, SourceRecord, Town
from apps.moderation.models import BannedTerm, ModerationItem, PriceRangeSuggestion, ScamAlert
from apps.notifications.models import Notification, NotificationPreference
from apps.sitesettings.models import SectionAvailability
from apps.telemetry.models import DailyCampusStats, DailyListingStats, Event, PendingEvent


class RegionFactory(DjangoModelFactory):
    class Meta:
        model = Region
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Test Region {n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))


class DistrictFactory(DjangoModelFactory):
    class Meta:
        model = District

    region = factory.SubFactory(RegionFactory)
    name = factory.Sequence(lambda n: f"Test District {n}")
    slug = factory.Sequence(lambda n: f"test-district-{n}")


class TownFactory(DjangoModelFactory):
    class Meta:
        model = Town

    region = factory.SubFactory(RegionFactory)
    name = factory.Sequence(lambda n: f"Testtown {n}")
    slug = factory.Sequence(lambda n: f"testtown-{n}")
    lat = 7.0
    lng = -1.0


class InstitutionFactory(DjangoModelFactory):
    class Meta:
        model = Institution

    name = factory.Sequence(lambda n: f"Test University {n}")
    slug = factory.Sequence(lambda n: f"test-university-{n}")
    kind = "university"


class CampusFactory(DjangoModelFactory):
    class Meta:
        model = Campus

    institution = factory.SubFactory(InstitutionFactory)
    town = factory.SubFactory(TownFactory)
    name = factory.Sequence(lambda n: f"Test Campus {n}")
    short_name = factory.Sequence(lambda n: f"TC{n}")
    slug = factory.Sequence(lambda n: f"test-campus-{n}")
    kind = "university"
    lat = 7.0
    lng = -1.0


class AreaFactory(DjangoModelFactory):
    class Meta:
        model = Area

    town = factory.SubFactory(TownFactory)
    name = factory.Sequence(lambda n: f"Test Area {n}")
    slug = factory.Sequence(lambda n: f"test-area-{n}")
    review_status = "verified"


class CampusRequestFactory(DjangoModelFactory):
    class Meta:
        model = CampusRequest

    name = "Test College of Testing"
    town_name = "Testville"
    region = factory.SubFactory(RegionFactory)


class SourceRecordFactory(DjangoModelFactory):
    class Meta:
        model = SourceRecord

    source = "wikidata"
    kind = "institution"
    source_id = factory.Sequence(lambda n: f"Q{n}")
    retrieved_at = factory.LazyFunction(timezone.now)


class ImportLogFactory(DjangoModelFactory):
    class Meta:
        model = ImportLog

    command = "import_test"
    source = "manual"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.test")
    display_name = factory.Sequence(lambda n: f"Test User {n}")
    password = factory.PostGenerationMethodCall("set_password", "pass12345!")
    onboarded = True
    date_joined = factory.LazyFunction(lambda: timezone.now() - timedelta(days=10))

    @factory.post_generation
    def verified(self, create, extracted, **kwargs):
        if create and extracted is not False:
            EmailAddress.objects.create(user=self, email=self.email, verified=True, primary=True)
        if create:
            self.save()


class ProfileFactory(DjangoModelFactory):
    class Meta:
        model = Profile
        django_get_or_create = ("user",)

    user = factory.SubFactory(UserFactory)


class VerificationRequestFactory(DjangoModelFactory):
    class Meta:
        model = VerificationRequest

    user = factory.SubFactory(UserFactory)
    kind = "student"
    document = factory.django.FileField(filename="id.pdf", data=b"%PDF-1.4 test")


class PhoneOTPFactory(DjangoModelFactory):
    class Meta:
        model = PhoneOTP

    user = factory.SubFactory(UserFactory)
    phone = "+233241234567"
    code_hash = "x"
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(minutes=10))


class ContactCardFactory(DjangoModelFactory):
    class Meta:
        model = ContactCard

    owner = factory.SubFactory(UserFactory)
    label = "Personal"
    is_default = True


class ContactChannelFactory(DjangoModelFactory):
    class Meta:
        model = ContactChannel

    card = factory.SubFactory(ContactCardFactory)
    kind = "phone"
    value = "+233241234567"


class ItemCategoryFactory(DjangoModelFactory):
    class Meta:
        model = lm.ItemCategory

    name = factory.Sequence(lambda n: f"Cat {n}")
    slug = factory.Sequence(lambda n: f"cat-{n}")


class ServiceCategoryFactory(DjangoModelFactory):
    class Meta:
        model = lm.ServiceCategory

    name = factory.Sequence(lambda n: f"Svc {n}")
    slug = factory.Sequence(lambda n: f"svc-{n}")


class ListingFactory(DjangoModelFactory):
    class Meta:
        model = lm.Listing

    owner = factory.SubFactory(UserFactory)
    section = "buy-sell"
    title = factory.Sequence(lambda n: f"Test item number {n}")
    slug = factory.Sequence(lambda n: f"test-item-{n}")
    description = "A test listing."
    price = 100
    town = factory.SubFactory(TownFactory)
    status = "active"
    published_at = factory.LazyFunction(timezone.now)
    approved_at = factory.LazyFunction(timezone.now)
    contact_card = factory.LazyAttribute(lambda o: ContactCardFactory(owner=o.owner))
    lat = 7.0
    lng = -1.0


class ListingCampusFactory(DjangoModelFactory):
    class Meta:
        model = lm.ListingCampus

    listing = factory.SubFactory(ListingFactory)
    campus = factory.SubFactory(CampusFactory)


class ListingPhotoFactory(DjangoModelFactory):
    class Meta:
        model = lm.ListingPhoto

    listing = factory.SubFactory(ListingFactory)
    image = factory.django.ImageField(width=40, height=30)


def _details(model, **defaults):
    return type(
        f"{model.__name__}Factory",
        (DjangoModelFactory,),
        {"Meta": type("Meta", (), {"model": model}), "listing": factory.SubFactory(ListingFactory), **defaults},
    )


RoomDetailsFactory = _details(lm.RoomDetails, listing=factory.SubFactory(ListingFactory, section="rooms"))
RoommateDetailsFactory = _details(lm.RoommateDetails, listing=factory.SubFactory(ListingFactory, section="roommates", price=None))
ShortStayDetailsFactory = _details(lm.ShortStayDetails, listing=factory.SubFactory(ListingFactory, section="short-stays"))
ItemDetailsFactory = _details(lm.ItemDetails, category=factory.SubFactory(ItemCategoryFactory))
WantedDetailsFactory = _details(lm.WantedDetails, listing=factory.SubFactory(ListingFactory, section="wanted", price=None))
ServiceDetailsFactory = _details(lm.ServiceDetails, listing=factory.SubFactory(ListingFactory, section="services"),
                                 service_type=factory.SubFactory(ServiceCategoryFactory))
JobDetailsFactory = _details(lm.JobDetails, listing=factory.SubFactory(ListingFactory, section="jobs", price=None),
                             pay_text="GH₵ 20/hr")
JobRequestDetailsFactory = _details(lm.JobRequestDetails, listing=factory.SubFactory(ListingFactory, section="job-requests", price=None))
ErrandDetailsFactory = _details(lm.ErrandDetails, listing=factory.SubFactory(ListingFactory, section="errands"))
FoodDetailsFactory = _details(lm.FoodDetails, listing=factory.SubFactory(ListingFactory, section="food", price=None),
                              available_until=factory.LazyFunction(lambda: timezone.now() + timedelta(hours=2)))
EventDetailsFactory = _details(lm.EventDetails, listing=factory.SubFactory(ListingFactory, section="events", price=None),
                               starts_at=factory.LazyFunction(lambda: timezone.now() + timedelta(days=2)), venue="Great Hall")
NoteDetailsFactory = _details(lm.NoteDetails, listing=factory.SubFactory(ListingFactory, section="notes"), course_code="CSC101")
StudyDetailsFactory = _details(lm.StudyDetails, listing=factory.SubFactory(ListingFactory, section="study", price=None))
LostFoundDetailsFactory = _details(lm.LostFoundDetails, listing=factory.SubFactory(ListingFactory, section="lost-found", price=None),
                                   item_type="ID card")
TripDetailsFactory = _details(lm.TripDetails, listing=factory.SubFactory(ListingFactory, section="trips", price=None),
                              origin_town=factory.SubFactory(TownFactory), destination_town=factory.SubFactory(TownFactory),
                              departs_at=factory.LazyFunction(lambda: timezone.now() + timedelta(days=1)))
AlertDetailsFactory = _details(lm.AlertDetails, listing=factory.SubFactory(ListingFactory, section="alerts", price=None),
                               valid_until=factory.LazyFunction(lambda: timezone.now() + timedelta(hours=5)))
QuestionDetailsFactory = _details(lm.QuestionDetails, listing=factory.SubFactory(ListingFactory, section="ask", price=None))


class HostelFactory(DjangoModelFactory):
    class Meta:
        model = Hostel

    owner = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Test Hostel {n}")
    slug = factory.Sequence(lambda n: f"test-hostel-{n}")
    town = factory.SubFactory(TownFactory)


class HostelRoomTypeFactory(DjangoModelFactory):
    class Meta:
        model = HostelRoomType

    hostel = factory.SubFactory(HostelFactory)
    name = "2 in 1"
    price = 3000
    total_rooms = 5
    available_rooms = 2


class HostelPhotoFactory(DjangoModelFactory):
    class Meta:
        model = HostelPhoto

    hostel = factory.SubFactory(HostelFactory)
    image = factory.django.ImageField(width=40, height=30)


class BoostFactory(DjangoModelFactory):
    class Meta:
        model = Boost

    listing = factory.SubFactory(ListingFactory)
    user = factory.LazyAttribute(lambda o: o.listing.owner)
    ends_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=3))


class LikeFactory(DjangoModelFactory):
    class Meta:
        model = Like

    user = factory.SubFactory(UserFactory)
    listing = factory.SubFactory(ListingFactory)


class CommentFactory(DjangoModelFactory):
    class Meta:
        model = Comment

    listing = factory.SubFactory(ListingFactory)
    author = factory.SubFactory(UserFactory)
    body = "Is it still available?"


class ReviewFactory(DjangoModelFactory):
    class Meta:
        model = Review

    reviewer = factory.SubFactory(UserFactory)
    hostel = factory.SubFactory(HostelFactory)
    rating = 4


class ReportFactory(DjangoModelFactory):
    class Meta:
        model = Report

    target = factory.SubFactory(ListingFactory)
    reporter = factory.SubFactory(UserFactory)
    reason = "spam"


class SavedSearchFactory(DjangoModelFactory):
    class Meta:
        model = SavedSearch

    user = factory.SubFactory(UserFactory)
    section = "buy-sell"


class ConversationFactory(DjangoModelFactory):
    class Meta:
        model = Conversation

    listing = factory.SubFactory(ListingFactory)
    starter = factory.SubFactory(UserFactory)
    owner = factory.LazyAttribute(lambda o: o.listing.owner)
    starter_alias = "KampusDey User #1111"
    owner_alias = "KampusDey User #2222"


class MessageFactory(DjangoModelFactory):
    class Meta:
        model = Message

    conversation = factory.SubFactory(ConversationFactory)
    sender = factory.LazyAttribute(lambda o: o.conversation.starter)
    body = "Hello"


class BlockFactory(DjangoModelFactory):
    class Meta:
        model = Block

    blocker = factory.SubFactory(UserFactory)
    blocked = factory.SubFactory(UserFactory)


class BannedTermFactory(DjangoModelFactory):
    class Meta:
        model = BannedTerm

    term = factory.Sequence(lambda n: f"badterm{n}")


class ModerationItemFactory(DjangoModelFactory):
    class Meta:
        model = ModerationItem

    target = factory.SubFactory(ListingFactory)
    reason = "test"


class ScamAlertFactory(DjangoModelFactory):
    class Meta:
        model = ScamAlert

    name = "Fake Agent (test)"
    description = "Test alert."


class PriceRangeSuggestionFactory(DjangoModelFactory):
    class Meta:
        model = PriceRangeSuggestion

    category_kind = "item"
    category_id = 1
    category_name = "Phones"
    suggested_min = 10
    suggested_max = 100
    samples = 30


class EventFactory(DjangoModelFactory):
    class Meta:
        model = Event

    kind = "view"


class PendingEventFactory(DjangoModelFactory):
    class Meta:
        model = PendingEvent

    payload = factory.LazyFunction(lambda: {"kind": "view", "meta": {}})


class DailyListingStatsFactory(DjangoModelFactory):
    class Meta:
        model = DailyListingStats

    listing = factory.SubFactory(ListingFactory)
    date = factory.LazyFunction(timezone.localdate)


class DailyCampusStatsFactory(DjangoModelFactory):
    class Meta:
        model = DailyCampusStats

    campus = factory.SubFactory(CampusFactory)
    date = factory.LazyFunction(timezone.localdate)


class NotificationFactory(DjangoModelFactory):
    class Meta:
        model = Notification

    recipient = factory.SubFactory(UserFactory)
    trigger = "message"
    title = "Test notification"


class NotificationPreferenceFactory(DjangoModelFactory):
    class Meta:
        model = NotificationPreference
        django_get_or_create = ("user",)

    user = factory.SubFactory(UserFactory)


class ReferralFactory(DjangoModelFactory):
    class Meta:
        model = Referral

    ambassador = factory.SubFactory(UserFactory)
    referred_user = factory.SubFactory(UserFactory)


class SpotlightFactory(DjangoModelFactory):
    class Meta:
        model = Spotlight

    listing = factory.SubFactory(ListingFactory)
    week_start = factory.LazyFunction(lambda: timezone.localdate() - timedelta(days=timezone.localdate().weekday()))


class SectionAvailabilityFactory(DjangoModelFactory):
    class Meta:
        model = SectionAvailability

    section = "trips"
    enabled = True


class ExternalSourceFactory(DjangoModelFactory):
    class Meta:
        model = ExternalSource
        django_get_or_create = ("slug",)

    name = "OpenStreetMap places (test)"
    slug = "osm-places"
    kind = "osm_places"
    base_url = "https://overpass-api.de/api/interpreter"
    terms_url = "https://www.openstreetmap.org/copyright"
    attribution_text = "© OpenStreetMap contributors"
    permission_status = "approved"
    terms_reviewed = True
    enabled = True
    min_interval_minutes = 60


class ExternalRunFactory(DjangoModelFactory):
    class Meta:
        model = ExternalRun

    source = factory.SubFactory(ExternalSourceFactory)


class PlaceFactory(DjangoModelFactory):
    class Meta:
        model = Place

    external_source = factory.SubFactory(ExternalSourceFactory)
    name = factory.Sequence(lambda n: f"Test Guest House {n}")
    slug = factory.Sequence(lambda n: f"test-guest-house-{n}")
    source_id = factory.Sequence(lambda n: f"node/{n}")
    kind = "guest_house"
    town = factory.SubFactory(TownFactory)
    lat = 7.001
    lng = -1.001


class PlaceCampusFactory(DjangoModelFactory):
    class Meta:
        model = PlaceCampus

    place = factory.SubFactory(PlaceFactory)
    campus = factory.SubFactory(CampusFactory)
    distance_m = 150


class PlaceClaimFactory(DjangoModelFactory):
    class Meta:
        model = PlaceClaim

    place = factory.SubFactory(PlaceFactory)
    user = factory.SubFactory(UserFactory)
    proof_kind = "photo"


class ExternalJobFactory(DjangoModelFactory):
    class Meta:
        model = ExternalJob

    external_source = factory.SubFactory(ExternalSourceFactory, slug="remotive", kind="remotive_jobs", name="Remotive (test)")
    source_id = factory.Sequence(lambda n: str(n))
    title = "Test Remote Writer"
    url = "https://remotive.com/remote-jobs/test"
    published_at = factory.LazyFunction(timezone.now)
