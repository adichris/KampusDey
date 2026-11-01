"""GeoLite2 download (weekly). The database only powers a region *hint* in the picker."""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

import requests
from django.conf import settings
from django.utils import timezone

from apps.sitesettings.models import IntegrationSettings


def update_geolite2() -> Path:
    """Download GeoLite2-City and swap it in atomically. Streams to disk (the archive is ~35 MB)."""
    integ = IntegrationSettings.load()
    if not (integ.geolite2_account_id and integ.geolite2_license_key):
        raise RuntimeError("Set the GeoLite2 account ID and licence key in Integrations first.")
    target_dir = Path(settings.GEOIP_PATH)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "GeoLite2-City.mmdb"
    archive = target_dir / "GeoLite2-City.tar.gz.part"
    tmp = path.with_suffix(".tmp")
    try:
        with requests.get(
            settings.GEOIP_DOWNLOAD_URL,
            auth=(integ.geolite2_account_id.strip(), integ.geolite2_license_key.strip()),
            headers={"User-Agent": settings.DATA_IMPORT_USER_AGENT},
            timeout=(15, 120),
            stream=True,
        ) as resp:
            if resp.status_code == 401:
                raise RuntimeError(
                    "MaxMind refused the account ID / licence key (HTTP 401). "
                    "Check both in Integrations; new keys can take a few minutes to work."
                )
            if resp.status_code != 200:
                raise RuntimeError(f"MaxMind download failed with HTTP {resp.status_code}")
            with archive.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
        with tarfile.open(archive, mode="r:gz") as tar:
            member = next(
                (m for m in tar.getmembers() if m.name.endswith("GeoLite2-City.mmdb")), None
            )
            if member is None or not member.isfile():
                raise RuntimeError("Archive did not contain GeoLite2-City.mmdb")
            with tar.extractfile(member) as src, tmp.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1 << 20)
        tmp.replace(path)
    finally:
        archive.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)
    integ.geolite2_last_updated = timezone.now()
    integ.save(update_fields=["geolite2_last_updated", "updated_at"])
    return path
