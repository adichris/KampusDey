"""Admin edits lock the edited fields so re-imports never overwrite them (DATA_SOURCES §6)."""

LOCKABLE_SKIP = {"updated_at", "created_at", "locked_fields", "admin_locked", "review_status"}


def lock_changed_fields(obj, form):
    """Called from admin save_model: add changed fields to locked_fields."""
    changed = [f for f in getattr(form, "changed_data", []) if f not in LOCKABLE_SKIP]
    if not changed:
        return
    locked = set(obj.locked_fields or [])
    locked.update(changed)
    obj.locked_fields = sorted(locked)
