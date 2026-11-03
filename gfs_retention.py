"""
gfs_retention.py — Grandfather-Father-Son retention for backup points.

Classifies restore points (CBT chain points or legacy date folders) and returns
which point IDs / folder names to keep.
"""

import datetime
import re


POINT_ID_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$")


def parse_point_timestamp(point_id, fallback_iso=None):
    m = POINT_ID_RE.match(point_id or "")
    if m:
        y, mo, d, h, mi, s = map(int, m.groups())
        return datetime.datetime(y, mo, d, h, mi, s)
    if fallback_iso:
        try:
            return datetime.datetime.fromisoformat(fallback_iso.replace("Z", ""))
        except ValueError:
            pass
    # Legacy YYYY-MM-DD folder
    try:
        return datetime.datetime.strptime(point_id[:10], "%Y-%m-%d")
    except ValueError:
        return datetime.datetime.utcnow()


def classify_gfs_keepers(points, daily=7, weekly=4, monthly=6, now=None):
    """
    points: list of dicts with at least {id, timestamp?}
    Returns set of point ids to keep.
    """
    if now is None:
        now = datetime.datetime.utcnow()

    enriched = []
    for p in points:
        pid = p.get("id") or p.get("date") or ""
        ts = parse_point_timestamp(pid, p.get("timestamp"))
        enriched.append({"id": pid, "ts": ts})

    enriched.sort(key=lambda x: x["ts"], reverse=True)
    if not enriched:
        return set()

    kept = set()

    # Daily: latest point per calendar day for the last `daily` distinct days
    days_kept = 0
    seen_days = set()
    for p in enriched:
        day_key = p["ts"].date()
        if day_key in seen_days:
            continue
        if days_kept >= daily:
            break
        kept.add(p["id"])
        seen_days.add(day_key)
        days_kept += 1

    # Weekly: one keeper per ISO week (latest in week) for `weekly` weeks back
    weeks_kept = 0
    seen_weeks = set()
    for p in enriched:
        week_key = (p["ts"].isocalendar().year, p["ts"].isocalendar().week)
        if week_key in seen_weeks:
            continue
        age_days = (now - p["ts"]).days
        if age_days > daily + (weekly * 7):
            continue
        if weeks_kept >= weekly:
            break
        kept.add(p["id"])
        seen_weeks.add(week_key)
        weeks_kept += 1

    # Monthly: one keeper per month for `monthly` months back
    months_kept = 0
    seen_months = set()
    for p in enriched:
        month_key = (p["ts"].year, p["ts"].month)
        if month_key in seen_months:
            continue
        if months_kept >= monthly:
            break
        kept.add(p["id"])
        seen_months.add(month_key)
        months_kept += 1

    # Always keep the latest point
    if enriched:
        kept.add(enriched[0]["id"])
    return kept


