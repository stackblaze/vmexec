"""
Alerts to one webhook (Discord, Slack or any JSON endpoint).

Three alerts, each switchable in Settings > Alerts:
  failure   a backup failed                       (worker, on the failure)
  missed    a scheduled backup never started      (watchdog, 2 h after its time)
  storage   backup storage unhealthy / recovered  (watchdog, every 5 min)

Messages start with the appliance name (VMEXEC_INSTANCE_NAME, e.g. the
region slug). Sending never blocks or fails the caller.
"""
import datetime
import json
import os
import threading
import urllib.request
from urllib.parse import urlparse

from logger_util import log_info, log_warn

MISSED_AFTER = datetime.timedelta(hours=2)
STORAGE_CHECK_EVERY = datetime.timedelta(minutes=5)

_state = {"missed": set(), "storage_ok": None, "storage_checked": None}


def webhook_hint(url):
    """Shown in Settings instead of the URL (it is a secret): 'discord.com/…'."""
    if not url:
        return ""
    host = urlparse(url).hostname or ""
    return f"{host}/…" if host else "set"


def payload_for(url, text):
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("discord.com") or host.endswith("discordapp.com"):
        return {"content": text[:1900]}
    if host.endswith("slack.com"):
        return {"text": text}
    return {"text": text, "source": "vmexec"}


def _post(url, text, timeout=10):
    data = json.dumps(payload_for(url, text)).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "VMExec"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def _prefix(text):
    name = os.environ.get("VMEXEC_INSTANCE_NAME", "").strip()
    return f"[VMExec {name}] {text}" if name else f"[VMExec] {text}"


def send(config, kind, text, sync=False):
    """Send if the webhook is set and this alert kind is on. Returns True if queued/sent."""
    url = (getattr(config, "alert_webhook_url", "") or "").strip() if config else ""
    if not url or not getattr(config, f"alert_on_{kind}", True):
        return False
    msg = _prefix(text)

    def go():
        try:
            _post(url, msg)
            log_info(f"[ALERT] Sent {kind} alert")
        except Exception as e:  # noqa: BLE001 - an alert must never break a backup
            log_warn(f"[ALERT] Webhook failed ({kind}): {e}")

    if sync:
        go()
    else:
        threading.Thread(target=go, daemon=True).start()
    return True


def test(url):
    """(ok, message) for the Settings 'Send test' button."""
    try:
        status = _post(url, _prefix("Test alert. Alerts from this appliance will arrive here."))
        return True, f"Sent (HTTP {status})"
    except Exception as e:  # noqa: BLE001
        return False, f"Webhook failed: {e}"


def previous_run(vm, now):
    """The most recent scheduled start at or before now (None if none in 40 days)."""
    days = {int(d) for d in (vm.schedule_days or "0,1,2,3,4,5,6").split(",") if d.strip().isdigit()}
    freq = vm.schedule_frequency or "daily"
    for back in range(0, 40):
        day = (now - datetime.timedelta(days=back)).date()
        at = datetime.datetime.combine(day, datetime.time(vm.schedule_hour or 0, vm.schedule_minute or 0))
        if at > now:
            continue
        if freq == "weekly" and day.weekday() not in days:
            continue
        if freq == "monthly" and (day.day > 7 or day.weekday() not in days):
            continue
        return at
    return None


def check_missed(db, config, vms, now=None, utc_now=None, paused=False):
    """Alert once per VM and scheduled time that never started within MISSED_AFTER."""
    if paused:
        return []
    now = now or datetime.datetime.now()
    utc_now = utc_now or datetime.datetime.utcnow()
    offset = now - utc_now  # schedules are local time; last_backup is UTC
    missed = []
    for vm in vms:
        if not (vm.is_selected and vm.is_job_active):
            continue
        if (vm.current_action or "").strip():
            continue  # running or queued
        at = previous_run(vm, now)
        if at is None or now - at < MISSED_AFTER:
            continue
        last = vm.last_backup + offset if vm.last_backup else None
        if last and last >= at - datetime.timedelta(minutes=1):
            continue
        key = (vm.id, at.isoformat())
        if key in _state["missed"]:
            continue
        _state["missed"].add(key)
        missed.append(vm.vm_name)
        send(config, "missed", f"Scheduled backup of {vm.vm_name} at {at:%Y-%m-%d %H:%M} did not run.")
    return missed


def check_storage(config, health_fn, now=None):
    """Alert on healthy -> unhealthy and back; health_fn() -> status_ops.storage_health() dict."""
    now = now or datetime.datetime.utcnow()
    last = _state["storage_checked"]
    if last and now - last < STORAGE_CHECK_EVERY:
        return None
    _state["storage_checked"] = now
    h = health_fn()
    ok = bool(h.get("healthy"))
    before = _state["storage_ok"]
    _state["storage_ok"] = ok
    if before is None and ok:
        return None
    if before is not False and not ok:
        send(config, "storage", f"Backup storage is not available: {h.get('error') or 'unknown error'}. Backups will fail until it is fixed.")
        return "down"
    if before is False and ok:
        send(config, "storage", "Backup storage is healthy again.")
        return "up"
    return None
