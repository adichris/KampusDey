"""Run periodic jobs without Celery beat (handy on Windows / without Redis).

python manage.py run_periodic            # every scheduled task once
python manage.py run_periodic --loop     # keep running, honouring each interval
python manage.py run_periodic telemetry.flush listings.recompute_scores
"""

import time
from datetime import timedelta

from celery import current_app
from django.conf import settings
from django.core.management.base import BaseCommand


def _interval_seconds(schedule) -> float:
    if isinstance(schedule, timedelta):
        return schedule.total_seconds()
    run_every = getattr(schedule, "run_every", None)
    if isinstance(run_every, timedelta):
        return run_every.total_seconds()
    return 3600.0


class Command(BaseCommand):
    help = "Run scheduled tasks inline (without a broker)."

    def add_arguments(self, parser):
        parser.add_argument("tasks", nargs="*", help="Task names (default: all scheduled)")
        parser.add_argument(
            "--loop", action="store_true", help="Run forever on each task's interval"
        )

    def handle(self, *args, **opts):
        schedule = settings.CELERY_BEAT_SCHEDULE
        names = opts["tasks"] or [entry["task"] for entry in schedule.values()]
        intervals = {e["task"]: _interval_seconds(e["schedule"]) for e in schedule.values()}
        last: dict[str, float] = {}
        current_app.loader.import_default_modules()
        while True:
            for name in names:
                now = time.monotonic()
                if opts["loop"] and name in last and now - last[name] < intervals.get(name, 3600):
                    continue
                task = current_app.tasks.get(name)
                if task is None:
                    self.stderr.write(f"unknown task {name}")
                    continue
                try:
                    result = task.apply().get()
                    self.stdout.write(f"{name}: {result}")
                except Exception as exc:  # keep the loop alive
                    self.stderr.write(f"{name} failed: {exc}")
                last[name] = now
            if not opts["loop"]:
                break
            time.sleep(15)
