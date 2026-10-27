from celery import shared_task


@shared_task(name="telemetry.flush")
def flush():
    from .services import flush as run

    return run()


@shared_task(name="telemetry.rollup")
def rollup():
    from .services import rollup as run

    return run()
