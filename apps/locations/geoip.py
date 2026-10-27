"""GeoLite2 download (weekly). The database only powers a region *hint* in the picker."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import requests
from django.conf import settings
from django.utils import timezone

from apps.sitesettings.models import IntegrationSettings


def update_geolite2() -> Path:
    integ = IntegrationSettings.load()
    if not (integ.geolite2_account_id and integ.geolite2_license_key):
        raise RuntimeError("Set the GeoLite2 account ID and licence key in Integrations first.")
    resp = requests.get(
        settings.GEOIP_DOWNLOAD_URL,
        auth=(integ.geolite2_account_id, integ.geolite2_license_key),
        headers={"User-Agent": settings.DATA_IMPORT_USER_AGENT},
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"MaxMind download failed with HTTP {resp.status_code}")
    target_dir = Path(settings.GEOIP_PATH)
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        member = next((m for m in tar.getmembers() if m.name.endswith("GeoLite2-City.mmdb")), None)
        if member is None:
            raise RuntimeError("Archive did not contain GeoLite2-City.mmdb")
        data = tar.extractfile(member).read()
    path = target_dir / "GeoLite2-City.mmdb"
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    integ.geolite2_last_updated = timezone.now()
    integ.save()
    return path
