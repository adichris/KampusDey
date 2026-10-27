"""Polite HTTP for imports: proper User-Agent, throttling, back-off, raw response caching."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)
RAW_DIR = Path(settings.BASE_DIR) / "data" / "raw"
_LAST_CALL: dict[str, float] = {}

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


class FetchError(Exception):
    pass


def _throttle(host: str, min_interval: float):
    last = _LAST_CALL.get(host)
    if last is not None:
        wait = min_interval - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _LAST_CALL[host] = time.monotonic()


def fetch(
    url,
    *,
    method="GET",
    params=None,
    data=None,
    headers=None,
    min_interval=2.0,
    retries=4,
    timeout=200,
):
    from urllib.parse import urlparse

    host = urlparse(url).netloc
    hdrs = {"User-Agent": settings.DATA_IMPORT_USER_AGENT, "Accept": "application/json"}
    hdrs.update(headers or {})
    delay = 5.0
    for attempt in range(1, retries + 1):
        _throttle(host, min_interval)
        try:
            resp = requests.request(
                method, url, params=params, data=data, headers=hdrs, timeout=timeout
            )
        except requests.RequestException as exc:
            logger.warning("fetch %s failed (%s), attempt %s", url, exc, attempt)
        else:
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504):
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                logger.warning("fetch %s → %s; backing off %ss", url, resp.status_code, wait)
                time.sleep(wait)
                delay *= 2
                continue
            raise FetchError(f"{url} returned HTTP {resp.status_code}")
        time.sleep(delay)
        delay *= 2
    raise FetchError(f"{url} failed after {retries} attempts")


def save_raw(source: str, name: str, payload) -> Path:
    folder = RAW_DIR / source
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}-{timezone.now():%Y%m%d}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def latest_raw(source: str, name: str):
    folder = RAW_DIR / source
    files = sorted(folder.glob(f"{name}-*.json")) if folder.exists() else []
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def sparql(query: str):
    resp = fetch(
        WIKIDATA_SPARQL,
        params={"query": query, "format": "json"},
        headers={"Accept": "application/sparql-results+json"},
        min_interval=1.0,
    )
    return resp.json()


def overpass(query: str):
    resp = fetch(OVERPASS_URL, method="POST", data={"data": query}, min_interval=2.0)
    return resp.json()


def load_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
