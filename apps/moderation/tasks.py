from celery import shared_task


@shared_task(name="moderation.suggest_price_ranges")
def suggest_price_ranges():
    from .services import suggest_price_ranges as run

    return run()
