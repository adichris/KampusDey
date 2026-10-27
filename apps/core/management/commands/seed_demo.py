"""FAKE demo data for local development only. Refuses to run when DEBUG=False.

Everything created here is marked "[DEMO]" and uses example.test emails. It never invents
campus coordinates: listing points are only placed near campuses that already have real points.
"""

import random
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.contacts.models import ContactChannel
from apps.contacts.services import default_card
from apps.core.utils import unique_slug
from apps.listings import models as lm
from apps.listings.services import autolink_campuses, compute_score
from apps.locations.models import Campus
from apps.telemetry.models import DailyCampusStats, Event

DEMO_ITEMS = {
    "rooms": ["[DEMO] Self-contained near main gate", "[DEMO] 2 in 1 room, water flows"],
    "buy-sell": ["[DEMO] Used HP laptop", "[DEMO] Double mattress", "[DEMO] Gas cylinder 6kg"],
    "jobs": ["[DEMO] Part-time shop assistant"],
    "events": ["[DEMO] Hall week jam"],
    "services": ["[DEMO] Laptop repairs"],
    "ask": ["[DEMO] Where can I print cheaply?"],
    "notes": ["[DEMO] CSC 101 past questions"],
}


class Command(BaseCommand):
    help = "Create clearly fake demo users, listings and telemetry (dev only)."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=6)

    @transaction.atomic
    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("seed_demo refuses to run when DEBUG=False.")
        campuses = list(Campus.objects.visible()[:6])
        if not campuses:
            raise CommandError("Run `manage.py seed_locations` first.")
        users = []
        for i in range(opts["users"]):
            user, created = User.objects.get_or_create(
                email=f"demo{i}@example.test",
                defaults={"display_name": f"Demo User {i}", "onboarded": True,
                          "date_joined": timezone.now() - timedelta(days=30)},
            )
            if created:
                user.set_password("demo-password-123")
                user.save()
                EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
            user.profile.home_campus = campuses[i % len(campuses)]
            user.profile.save()
            card = default_card(user)
            ContactChannel.objects.get_or_create(card=card, kind="whatsapp", defaults={"value": "+233200000000"})
            users.append(user)
        category = lm.ItemCategory.objects.first()
        service = lm.ServiceCategory.objects.first()
        created = 0
        now = timezone.now()
        for section, titles in DEMO_ITEMS.items():
            for title in titles:
                user = random.choice(users)
                campus = user.profile.home_campus
                if lm.Listing.objects.filter(title=title, owner=user).exists():
                    continue
                listing = lm.Listing(owner=user, section=section, title=title, town=campus.town,
                                     description="Fake demo listing for development.",
                                     price=random.choice([None, 150, 900, 2500]) if section in ("rooms", "buy-sell") else None,
                                     price_period="per_year" if section == "rooms" else "total", status="active",
                                     published_at=now - timedelta(hours=random.randint(1, 200)), approved_at=now,
                                     contact_card=default_card(user), seller_type="student")
                if campus.has_point:
                    listing.lat = campus.lat + random.uniform(-0.01, 0.01)
                    listing.lng = campus.lng + random.uniform(-0.01, 0.01)
                listing.slug = unique_slug(listing, title)
                listing.save()
                lm.ListingCampus.objects.get_or_create(listing=listing, campus=campus, defaults={"is_manual": True})
                autolink_campuses(listing)
                if section == "rooms":
                    lm.RoomDetails.objects.create(listing=listing, room_type="self_contained")
                elif section == "buy-sell":
                    lm.ItemDetails.objects.create(listing=listing, category=category)
                elif section == "jobs":
                    lm.JobDetails.objects.create(listing=listing, pay_text="GH₵ 15/hr")
                elif section == "events":
                    lm.EventDetails.objects.create(listing=listing, starts_at=now + timedelta(days=3), venue="Demo hall")
                elif section == "services":
                    lm.ServiceDetails.objects.create(listing=listing, service_type=service)
                elif section == "ask":
                    lm.QuestionDetails.objects.create(listing=listing)
                elif section == "notes":
                    lm.NoteDetails.objects.create(listing=listing, course_code="CSC101")
                listing.score = compute_score(listing)
                listing.save(update_fields=["score"])
                created += 1
        events = []
        for listing in lm.Listing.objects.filter(title__startswith="[DEMO]"):
            for _ in range(random.randint(5, 30)):
                events.append(Event(kind=random.choice(["view", "view", "view", "tap", "like"]), listing=listing,
                                    campus=listing.campus_links.first().campus, section=listing.section,
                                    created_at=now - timedelta(days=random.randint(0, 20)),
                                    meta={"channel": "whatsapp"}))
        for q in ("laptop", "mattress", "hostel near gate", "printer ink"):
            events.append(Event(kind="search", campus=campuses[0], meta={"query": q, "results": random.randint(0, 3)}))
        Event.objects.bulk_create(events)
        for campus in campuses:
            for d in range(7):
                DailyCampusStats.objects.update_or_create(
                    campus=campus, date=timezone.localdate() - timedelta(days=d),
                    defaults={"views": random.randint(10, 90), "taps": random.randint(1, 20), "posts": random.randint(0, 4)},
                )
        self.stdout.write(self.style.WARNING(
            f"FAKE DEMO DATA: {len(users)} users (password demo-password-123), {created} listings, {len(events)} events."
        ))
