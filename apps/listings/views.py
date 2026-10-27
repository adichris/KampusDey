"""Listing views: thin wrappers over services/selectors."""

from __future__ import annotations

from constance import config
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.accounts.services import can_post
from apps.contacts.channels import buttons_for
from apps.contacts.services import apply_contact_step, default_card, initial_from_card
from apps.locations.models import Campus, Town
from apps.locations.services import LocationContext
from apps.moderation.services import ModerationBlocked
from apps.sitesettings.services import enabled_section_slugs, enabled_sections, section_enabled
from apps.telemetry.services import record

from . import selectors, services
from .filters import filter_for
from .forms import DETAILS_FORMS, CommonForm, ContactStepForm
from .models import Listing, ListingPhoto
from .sections import SECTIONS

PAGE_SIZE = 18


def _point_from_request(request, location):
    lat, lng = request.GET.get("lat"), request.GET.get("lng")
    try:
        if lat and lng:
            return float(lat), float(lng)
    except ValueError:
        pass
    return location.point if location else None


# ---------------------------------------------------------------------------
# Home & campus/town landing pages
# ---------------------------------------------------------------------------
def home(request):
    return _home(request, request.location)


def campus_home(request, campus_slug):
    campus = get_object_or_404(
        Campus.objects.visible().select_related("town__region"), slug=campus_slug
    )
    return _home(request, LocationContext(campus=campus), landing=campus)


def town_home(request, town_slug):
    town = get_object_or_404(Town.objects.select_related("region"), slug=town_slug)
    return _home(request, LocationContext(town=town), landing=town)


def _home(request, location, landing=None):
    from apps.growth.services import current_spotlight

    campus = location.campus if location else None
    sections = enabled_sections(campus)
    slugs = {s.slug for s in sections}
    feeds = selectors.home_feeds(location, request.user, slugs) if location.is_set else {}
    return render(
        request,
        "listings/home.html",
        {
            "sections": sections,
            "feeds": feeds,
            "page_location": location,
            "landing": landing,
            "spotlight": current_spotlight(campus),
        },
    )


# ---------------------------------------------------------------------------
# Section pages
# ---------------------------------------------------------------------------
def section_campus(request, campus_slug, section):
    campus = get_object_or_404(
        Campus.objects.visible().select_related("town__region"), slug=campus_slug
    )
    return _section(request, LocationContext(campus=campus), section)


def section_town(request, town_slug, section):
    town = get_object_or_404(Town.objects.select_related("region"), slug=town_slug)
    return _section(request, LocationContext(town=town), section)


def _section(request, location, section_slug):
    section = SECTIONS.get(section_slug)
    if section is None or not section_enabled(section_slug, location.campus):
        raise Http404
    tab = request.GET.get("tab", "")
    if section_slug == "jobs" and tab == "remote":
        return _remote_jobs(request, location, section)
    qs = selectors.for_location(selectors.visible_listings(request.user, [section_slug]), location)
    filterset = filter_for(section_slug)(request.GET or None, queryset=qs)
    qs = filterset.qs if filterset.is_bound and filterset.is_valid() else qs
    sort = request.GET.get("sort", "recommended")
    point = _point_from_request(request, location)
    view_mode = request.GET.get("view", "list")
    page_number = request.GET.get("page") or 1
    boosted = (
        selectors.boosted_slots(qs) if str(page_number) == "1" and sort == "recommended" else []
    )
    ordered = selectors.sort_listings(qs.exclude(pk__in=[b.pk for b in boosted]), sort, point)
    if point and sort != "distance":
        ordered = selectors.annotate_point_distance(ordered, point)  # for display only
    paginator = Paginator(ordered, PAGE_SIZE)
    page = paginator.get_page(page_number)
    next_url = ""
    if page.has_next():
        params = request.GET.copy()
        params["page"] = page.next_page_number()
        next_url = f"{request.path}?{params.urlencode()}"
    other_places = []
    if location.campus and section_slug in ("rooms", "short-stays", "services"):
        from apps.external.services import accommodation_places, service_places

        if section_slug == "services":
            service = request.GET.get("service_type")
            slug = None
            if service:
                from .models import ServiceCategory

                slug = (
                    ServiceCategory.objects.filter(pk=service)
                    .values_list("slug", flat=True)
                    .first()
                )
            other_places = list(service_places(location.campus, slug)[:12])
        else:
            other_places = list(accommodation_places(location.campus)[:12])
    context = {
        "section": section,
        "page_location": location,
        "filterset": filterset,
        "page": page,
        "boosted": boosted,
        "sort": sort,
        "view_mode": view_mode,
        "next_url": next_url,
        "point": point,
        "other_places": other_places,
        "sections": enabled_sections(location.campus),
        "map_items": selectors.for_map(ordered) if view_mode == "map" else [],
        "tab": tab,
    }
    if request.htmx and request.GET.get("page"):
        return render(request, "listings/partials/results.html", context)
    return render(request, "listings/section.html", context)


def _remote_jobs(request, location, section):
    from apps.external.models import ExternalJob, ExternalSource

    source = ExternalSource.objects.filter(kind=ExternalSource.Kind.REMOTIVE_JOBS).first()
    jobs = ExternalJob.objects.visible().select_related("external_source")
    category = request.GET.get("category")
    if category:
        jobs = jobs.filter(category__iexact=category)
    page = Paginator(jobs.order_by("-published_at"), 20).get_page(request.GET.get("p"))
    categories = sorted(set(ExternalJob.objects.visible().values_list("category", flat=True)))
    return render(
        request,
        "listings/remote_jobs.html",
        {
            "section": section,
            "page_location": location,
            "page": page,
            "source": source,
            "categories": categories,
            "tab": "remote",
            "sections": enabled_sections(location.campus),
        },
    )


def section_redirect(request, section):
    """/s/<section>/ → the section page for the current campus/town."""
    location = request.location
    if location.campus:
        return redirect(
            "listings:section_campus", campus_slug=location.campus.slug, section=section
        )
    if location.town:
        return redirect("listings:section_town", town_slug=location.town.slug, section=section)
    messages.info(request, _("Choose your campus first."))
    return redirect("locations:picker_page")


# ---------------------------------------------------------------------------
# Search & nearby
# ---------------------------------------------------------------------------
def search(request):
    location = request.location
    query = request.GET.get("q", "").strip()
    section = request.GET.get("section") or None
    slugs = enabled_section_slugs(location.campus)
    results, facets, page = None, [], None
    if query:
        results, facets = selectors.search(query, location, request.user, slugs, section)
        page = Paginator(results, PAGE_SIZE).get_page(request.GET.get("page"))
        record(
            "search",
            request=request,
            meta={"query": query[:120], "results": page.paginator.count, "section": section or ""},
        )
    return render(
        request,
        "listings/search.html",
        {"query": query, "facets": facets, "page": page, "active_section": section},
    )


def nearby(request):
    location = request.location
    point = _point_from_request(request, location)
    section = request.GET.get("section") or ""
    radii = [int(r) for r in config.NEARBY_RADII.split(",") if r.strip().isdigit()]
    max_radius = max(radii) if radii else 2000
    sections = enabled_sections(location.campus)
    items = []
    listings = []
    if point:
        from apps.core import geo

        qs = selectors.visible_listings(
            request.user, [section] if section else [s.slug for s in sections]
        )
        qs = geo.nearby(qs.filter(lat__isnull=False), point[0], point[1], max_radius).order_by(
            "distance_m"
        )
        listings = list(qs[:60])
        items = [
            {
                "id": item.pk,
                "title": item.title,
                "url": item.get_absolute_url(),
                "lat": item.lat,
                "lng": item.lng,
                "approx": item.is_sensitive,
                "info": f"{item.card_info} · {round(item.distance_m)} m",
            }
            for item in listings
        ]
    return render(
        request,
        "listings/nearby.html",
        {
            "point": point,
            "items": items,
            "listings": listings,
            "radii": ",".join(map(str, radii)),
            "sections": sections,
            "active_section": section,
            "from_device": bool(request.GET.get("lat")),
        },
    )


# ---------------------------------------------------------------------------
# Listing detail
# ---------------------------------------------------------------------------
def _get_visible_listing(request, slug):
    listing = get_object_or_404(
        Listing.objects.select_related(
            "owner__profile", "town__region", "area", "contact_card"
        ).prefetch_related(
            Prefetch("photos", queryset=ListingPhoto.objects.order_by("order", "id")),
            "contact_card__channels",
        ),
        slug=slug,
    )
    is_owner = request.user.is_authenticated and request.user.pk == listing.owner_id
    if not (is_owner or request.user.is_staff):
        if not listing.is_visible and listing.status != Listing.Status.TAKEN:
            raise Http404
        if listing.is_need_food and not request.user.is_authenticated:
            raise Http404  # never shown to guests
        if not section_enabled(listing.section, None) and not listing.campus_links.exists():
            raise Http404
    return listing, is_owner


def detail(request, slug):
    from apps.engagement.models import Like
    from apps.engagement.services import visible_comments

    listing, is_owner = _get_visible_listing(request, slug)
    if not is_owner:
        record("view", request=request, listing=listing)
    liked = (
        request.user.is_authenticated
        and Like.objects.filter(user=request.user, listing=listing).exists()
    )
    from apps.boosts.services import boosts_left, can_boost

    context = {
        "listing": listing,
        "details": listing.details,
        "photos": list(listing.photos.all()),
        "is_owner": is_owner,
        "liked": liked,
        "contact": buttons_for(listing, request.user),
        "comments": visible_comments(listing),
        "related": selectors.related_listings(listing, request.user),
        "campus_links": listing.campus_links.filter(is_excluded=False).select_related("campus"),
        "boost_decision": can_boost(request.user, listing) if is_owner else None,
        "boosts_left": boosts_left(request.user) if is_owner else None,
        "show_alias_only": listing.is_need_food,
    }
    return render(request, "listings/detail.html", context)


# ---------------------------------------------------------------------------
# Post wizard (§6.3)
# ---------------------------------------------------------------------------
@login_required
def post_picker(request):
    decision = can_post(request.user)
    location = request.location
    if not location.is_set:
        messages.info(request, _("Choose your campus or town first."))
        return redirect(f"{reverse('locations:picker_page')}?next={reverse('listings:post')}")
    drafts = Listing.objects.filter(owner=request.user, status=Listing.Status.DRAFT).order_by(
        "-updated_at"
    )[:5]
    return render(
        request,
        "listings/post_picker.html",
        {"sections": enabled_sections(location.campus), "decision": decision, "drafts": drafts},
    )


@login_required
@require_POST
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def post_start(request, section):
    decision = can_post(request.user)
    if not decision:
        messages.error(request, decision.reason)
        return redirect("listings:post")
    if section not in enabled_section_slugs(request.location.campus):
        raise Http404
    try:
        listing = services.create_draft(request.user, section, request.location)
    except services.ListingError as exc:
        messages.error(request, str(exc))
        return redirect("listings:post")
    return redirect("listings:wizard", pk=listing.pk, step=1)


def _owned_draft(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    if listing.status not in (
        Listing.Status.DRAFT,
        Listing.Status.ACTIVE,
        Listing.Status.PENDING_REVIEW,
        Listing.Status.NEEDS_CHECK,
    ):
        raise Http404
    return listing


@login_required
def wizard(request, pk, step):
    listing = _owned_draft(request, pk)
    section = listing.section_obj
    if step not in (1, 2, 3):
        raise Http404
    ctx = {
        "listing": listing,
        "section": section,
        "step": step,
        "is_edit": listing.status != Listing.Status.DRAFT,
    }

    if step == 1:
        if request.method == "POST":
            _save_step(listing, 2)
            return redirect("listings:wizard", pk=pk, step=2)
        ctx.update(photos=listing.photos.all(), max_photos=config.MAX_PHOTOS)
        return render(request, "listings/wizard_photos.html", ctx)

    details_form_cls = DETAILS_FORMS[listing.section]
    if step == 2:
        common = CommonForm(request.POST or None, instance=listing, section=section)
        details_form = details_form_cls(
            request.POST or None, request.FILES or None, instance=listing.details, prefix="d"
        )
        if request.method == "POST" and common.is_valid() and details_form.is_valid():
            try:
                obj = common.save(commit=False)
                services.set_point(
                    obj, common.cleaned_data.get("lat"), common.cleaned_data.get("lng")
                )
                obj.wizard_step = max(obj.wizard_step, 3)
                obj.save()
                services.save_details(obj, details_form)
                services.autolink_campuses(obj)
            except services.ListingError as exc:
                common.add_error(None, str(exc))
            else:
                if listing.status != Listing.Status.DRAFT:
                    services.update_search_vector(obj)
                return redirect("listings:wizard", pk=pk, step=3)
        ctx.update(common=common, details_form=details_form)
        return render(request, "listings/wizard_details.html", ctx)

    # step 3: contact & visibility + campus links
    if listing.details is None:
        return redirect("listings:wizard", pk=pk, step=2)
    card = listing.contact_card or default_card(request.user)
    initial = initial_from_card(card) | {
        "contact_visibility": listing.contact_visibility,
        "hide_number": listing.hide_number,
    }
    form = ContactStepForm(request.POST or None, initial=initial, listing=listing)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        apply_contact_step(card, data)
        listing.contact_card = card
        listing.contact_visibility = (
            "members" if listing.is_need_food else data["contact_visibility"]
        )
        listing.hide_number = data["hide_number"]
        listing.save(
            update_fields=["contact_card", "contact_visibility", "hide_number", "updated_at"]
        )
        services.update_campus_links(
            listing,
            data.get("keep_campuses"),
            [data["add_campus"].pk] if data.get("add_campus") else [],
        )
        if "save_draft" in request.POST:
            messages.success(request, _("Draft saved."))
            return redirect("dashboard:home")
        if listing.status != Listing.Status.DRAFT:
            messages.success(request, _("Listing updated."))
            return redirect(listing)
        try:
            services.publish(listing, request)
        except (services.ListingError, ModerationBlocked) as exc:
            form.add_error(None, str(exc))
        else:
            if listing.status == Listing.Status.PENDING_REVIEW:
                messages.info(request, _("Thanks! Your post will appear after a quick review."))
            else:
                messages.success(request, _("Your post is live."))
            return redirect(listing)
    ctx.update(form=form, card=card)
    return render(request, "listings/wizard_contact.html", ctx)


def _save_step(listing, step):
    if listing.wizard_step < step:
        listing.wizard_step = step
        listing.save(update_fields=["wizard_step", "updated_at"])


@login_required
@require_POST
@ratelimit(key="user", rate="60/h", method="POST", block=True)
def photo_upload(request, pk):
    listing = _owned_draft(request, pk)
    upload = request.FILES.get("photo")
    if not upload:
        return HttpResponseBadRequest(_("No photo received."))
    try:
        services.add_photo(listing, upload)
    except services.ListingError as exc:
        return HttpResponse(str(exc), status=400)
    return render(
        request,
        "listings/partials/photo_list.html",
        {"listing": listing, "photos": listing.photos.all()},
    )


@login_required
@require_POST
def photo_delete(request, pk, photo_id):
    listing = _owned_draft(request, pk)
    photo = get_object_or_404(ListingPhoto, pk=photo_id, listing=listing)
    photo.image.delete(save=False)
    photo.delete()
    return render(
        request,
        "listings/partials/photo_list.html",
        {"listing": listing, "photos": listing.photos.all()},
    )


@login_required
@require_POST
def photo_move(request, pk, photo_id, direction):
    listing = _owned_draft(request, pk)
    ids = list(listing.photos.order_by("order", "id").values_list("pk", flat=True))
    if photo_id in ids:
        i = ids.index(photo_id)
        j = i - 1 if direction == "up" else i + 1
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            services.reorder_photos(listing, ids)
    return render(
        request,
        "listings/partials/photo_list.html",
        {"listing": listing, "photos": listing.photos.all()},
    )


@login_required
def delete_draft(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user, status=Listing.Status.DRAFT)
    if request.method == "POST":
        services.delete_photos(listing)
        listing.delete()
        messages.success(request, _("Draft deleted."))
        return redirect("dashboard:home")
    return render(request, "listings/confirm_delete.html", {"listing": listing})


# ---------------------------------------------------------------------------
# Lifecycle actions
# ---------------------------------------------------------------------------
def one_tap(request, token):
    """Signed 'Still available?' link from email — no login required."""
    try:
        listing, action = services.read_check_token(token)
    except (signing.BadSignature, signing.SignatureExpired, Listing.DoesNotExist):
        return render(
            request,
            "errors/simple.html",
            {"title": _("This link has expired"), "code": 410},
            status=410,
        )
    if request.method == "POST":
        if action == "confirm":
            services.confirm_available(listing)
            message = _("Thanks! Your listing stays up.")
        else:
            services.mark_taken(listing)
            message = _("Marked as taken. Congratulations!")
        return render(
            request, "listings/one_tap_done.html", {"listing": listing, "message": message}
        )
    # GET shows a confirmation button so link scanners can't change anything.
    return render(request, "listings/one_tap.html", {"listing": listing, "action": action})


@login_required
def check(request, slug):
    listing = get_object_or_404(Listing, slug=slug, owner=request.user)
    return render(
        request,
        "listings/check.html",
        {
            "listing": listing,
            "confirm_token": services.check_token(listing, "confirm"),
            "taken_token": services.check_token(listing, "taken"),
        },
    )
