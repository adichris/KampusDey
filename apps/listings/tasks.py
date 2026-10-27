from celery import shared_task


@shared_task(name="listings.recompute_scores")
def recompute_scores():
    from .services import recompute_scores as run

    return run()


@shared_task(name="listings.run_lifecycle")
def run_lifecycle():
    from apps.boosts.services import notify_ended

    from .services import run_lifecycle as run

    stats = run()
    stats["boost_end_notices"] = notify_ended()
    return stats
