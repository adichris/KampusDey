"""Seed item and service categories from the build prompt (§5.3). Idempotent."""

from django.utils.text import slugify

from .models import ItemCategory, ServiceCategory

ITEM_CATEGORIES = [
    ("Phones", "smartphone"),
    ("Laptops", "laptop"),
    ("Tablets", "tablet"),
    ("Mattresses & bedding", "bed"),
    ("Furniture", "armchair"),
    ("Gas cylinders & kitchen", "cooking-pot"),
    ("Books & stationery", "book-open"),
    ("Fashion", "shirt"),
    ("Shoes", "footprints"),
    ("Bags & accessories", "shopping-bag"),
    ("Beauty", "sparkles"),
    ("Electronics", "plug"),
    ("Sports", "dumbbell"),
    ("Other", "package"),
]

SERVICE_CATEGORIES = [
    ("Laptop repair", "laptop"),
    ("Phone repair", "smartphone"),
    ("Printing", "printer"),
    ("Hair", "scissors"),
    ("Laundry", "shirt"),
    ("Photography", "camera"),
    ("Tutoring", "graduation-cap"),
    ("Vacation storage", "package"),
    ("Other", "wrench"),
]


def seed_categories():
    for order, (name, icon) in enumerate(ITEM_CATEGORIES):
        ItemCategory.objects.get_or_create(
            slug=slugify(name), defaults={"name": name, "icon": icon, "order": order}
        )
    for order, (name, icon) in enumerate(SERVICE_CATEGORIES):
        ServiceCategory.objects.get_or_create(
            slug=slugify(name), defaults={"name": name, "icon": icon, "order": order}
        )
