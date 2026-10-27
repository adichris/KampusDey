def campus_context(request):
    location = getattr(request, "location", None)
    if location is None:
        return {"current_campus": None, "current_town": None, "location": None}
    return {
        "location": location,
        "current_campus": location.campus,
        "current_town": location.effective_town,
    }
