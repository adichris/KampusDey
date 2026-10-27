import pytest
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db


def test_seed_demo_refuses_without_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG=False"):
        call_command("seed_demo")


def test_seed_demo_in_debug(settings):
    from apps.listings.models import Listing

    settings.DEBUG = True
    call_command("seed_locations")
    call_command("seed_demo", users=3)
    assert Listing.objects.filter(title__startswith="[DEMO]").exists()


def test_run_periodic_runs_named_tasks(capsys):
    call_command("run_periodic", "telemetry.flush", "listings.recompute_scores")
    out = capsys.readouterr().out
    assert "telemetry.flush" in out and "listings.recompute_scores" in out
