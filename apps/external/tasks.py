from celery import shared_task


@shared_task(name="external.run_due_sources")
def run_due_sources():
    from .services import run_due_sources as run

    return [r.pk for r in run()]
