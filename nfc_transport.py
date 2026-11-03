"""
nfc_transport.py — Live VM backup via Snapshot ExportSnapshot + HttpNfcLease

Streams snapshot-backed disks over HTTPS (VMware NFC / streamVmdk) without
CopyVirtualDisk temp folders on ESXi. No VDDK required.

Flow: snapshot → ExportSnapshot → stream device URLs → remove snapshot
"""

import os
import threading
import time

import requests
from pyVmomi import vim

from logger_util import log_info, log_warn
import vsphere_context

CHUNK_SIZE = 1024 * 1024


class _LeaseProgressUpdater(threading.Thread):
    """Keeps HttpNfcLease alive by reporting progress periodically."""

    def __init__(self, lease, interval_sec=15):
        super().__init__(daemon=True)
        self._lease = lease
        self._interval = interval_sec
        self._running = True
        self.progress_pct = 0

    def set_progress(self, pct):
        self.progress_pct = min(max(int(pct), 0), 99)

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                state = self._lease.state
                if state in (vim.HttpNfcLease.State.done, vim.HttpNfcLease.State.error):
                    return
                self._lease.HttpNfcLeaseProgress(self.progress_pct)
            except Exception as e:
                log_warn(f"[NFC] Lease progress update: {e}")
                return
            time.sleep(self._interval)


def _nfc_headers():
    return {"Accept": "application/x-vnd.vmware-streamVmdk"}


def _wait_lease_ready(lease, timeout_sec=600, is_cancelled_func=None):
    """Block until lease is ready, done, or error."""
    start = time.time()
    while True:
        if is_cancelled_func and is_cancelled_func():
            raise RuntimeError("Backup cancelled by user")
        state = lease.state
        if state == vim.HttpNfcLease.State.ready:
            return
        if state == vim.HttpNfcLease.State.done:
            return
        if state == vim.HttpNfcLease.State.error:
            err = getattr(lease.info, "error", None) or lease.state
            raise RuntimeError(f"HttpNfcLease error: {err}")
        if time.time() - start > timeout_sec:
            raise RuntimeError(f"HttpNfcLease timeout after {timeout_sec}s (state={state})")
        time.sleep(2)


def _stream_url_to_storage(url, storage, dest_rel_path, cookies, total_size_hint=0,
                           progress_callback=None, progress_base=0, progress_total=100,
                           speed_callback=None, is_cancelled_func=None, lease_updater=None):
    """Stream an NFC device URL into StorageProvider."""
    log_info(f"[NFC] Streaming {url[:80]}... → {dest_rel_path}")
    resp = requests.get(
        url, stream=True, cookies=cookies, headers=_nfc_headers(), verify=False, timeout=7200,
    )
    if resp.status_code != 200:
        body = (resp.text or "")[:300]
        raise RuntimeError(f"NFC HTTP {resp.status_code}: {body}")

    total_size = int(resp.headers.get("Content-Length", 0)) or total_size_hint
    bytes_written = 0
    speed_window_bytes = 0
    speed_window_start = time.time()

    storage.makedirs(os.path.dirname(dest_rel_path) or dest_rel_path)

    with storage.open_write(dest_rel_path) as f:
        is_local = hasattr(storage, "base_path")
        zero_chunk = b"\x00" * CHUNK_SIZE if is_local else None

        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if is_cancelled_func and is_cancelled_func():
                raise RuntimeError("Backup cancelled by user")
            if not chunk:
                continue

            if is_local and len(chunk) == CHUNK_SIZE and chunk == zero_chunk and hasattr(f, "seek"):
                f.seek(CHUNK_SIZE, os.SEEK_CUR)
            elif is_local and not chunk.strip(b"\x00") and hasattr(f, "seek"):
                f.seek(len(chunk), os.SEEK_CUR)
            else:
                f.write(chunk)

            bytes_written += len(chunk)
            speed_window_bytes += len(chunk)

            now = time.time()
            if now - speed_window_start >= 2.0:
                if speed_callback and speed_window_bytes:
                    mbps = (speed_window_bytes / (1024 * 1024)) / (now - speed_window_start)
                    speed_callback(round(mbps, 1))
                speed_window_bytes = 0
                speed_window_start = now

            if total_size > 0 and progress_callback:
                pct = progress_base + (bytes_written * progress_total / total_size)
                progress_callback(min(int(pct), 99))
            if lease_updater and total_size > 0:
                lease_updater.set_progress(
                    progress_base + (bytes_written * progress_total / max(total_size, 1))
                )

        if is_local and bytes_written > 0 and hasattr(f, "truncate"):
            try:
                f.truncate(bytes_written)
            except Exception:
                pass

    log_info(f"[NFC] Wrote {bytes_written / (1024 * 1024):.1f} MB → {dest_rel_path}")
    return bytes_written


def _disk_export_names(disk):
    """Names ExportSnapshot may use in device targetId for this disk."""
    import re
    base = os.path.basename(disk["rel_path"])
    names = {base, base.replace(".vmdk", "-flat.vmdk")}
    plain = re.sub(r"-\d+\.vmdk$", ".vmdk", base)
    names.add(plain)
    names.add(plain.replace(".vmdk", "-flat.vmdk"))
    return names


def _list_stream_devices(lease):
    devices = []
    for device in getattr(lease.info, "deviceUrl", None) or []:
        target_id = getattr(device, "targetId", None)
        url = getattr(device, "url", None)
        if target_id and url:
            devices.append(device)
    return devices


def _find_device_url(lease, disk, disk_index=0):
    """Return (url, file_size) for disk in an ExportSnapshot lease."""
    names = _disk_export_names(disk)
    devices = _list_stream_devices(lease)

    for device in devices:
        target_id = getattr(device, "targetId", None) or ""
        url = getattr(device, "url", None)
        tid_base = os.path.basename(str(target_id))
        if tid_base in names or target_id in names:
            return url, int(getattr(device, "fileSize", 0) or 0)

    expected = f"disk-{disk_index}"
    for device in devices:
        if getattr(device, "targetId", None) == expected:
            return device.url, int(getattr(device, "fileSize", 0) or 0)

    if disk_index < len(devices):
        device = devices[disk_index]
        return device.url, int(getattr(device, "fileSize", 0) or 0)

    if len(devices) == 1:
        device = devices[0]
        return device.url, int(getattr(device, "fileSize", 0) or 0)

    log_warn(
        f"[NFC] No device URL for {os.path.basename(disk['rel_path'])} "
        f"(index={disk_index}); lease devices="
        f"{[getattr(d, 'targetId', None) for d in devices]}"
    )
    return None, 0


class NfcSnapshotLeaseSession:
    """Keeps an ExportSnapshot HttpNfcLease open for range reads or disk streaming."""

    def __init__(self, snap_obj, is_cancelled_func=None):
        self._snap_obj = snap_obj
        self._is_cancelled_func = is_cancelled_func
        self.lease = None
        self._updater = None

    def __enter__(self):
        self.lease = self._snap_obj.ExportSnapshot()
        # From here on the lease exists on the server; if anything below
        # raises (including a user cancel inside _wait_lease_ready), __exit__
        # never runs, so abort here or the orphaned lease keeps the export
        # LRO alive and blocks snapshot removal until vCenter times it out.
        try:
            _wait_lease_ready(self.lease, is_cancelled_func=self._is_cancelled_func)
            if self.lease.state != vim.HttpNfcLease.State.ready:
                raise RuntimeError(f"ExportSnapshot lease not ready: {self.lease.state}")
            self._updater = _LeaseProgressUpdater(self.lease, interval_sec=15)
            self._updater.start()
        except BaseException:
            self.abort()
            raise
        return self

    def complete(self):
        if not self.lease:
            return
        if self._updater:
            self._updater.set_progress(100)
            self._updater.stop()
        try:
            if self.lease.state == vim.HttpNfcLease.State.ready:
                self.lease.HttpNfcLeaseProgress(100)
                self.lease.HttpNfcLeaseComplete()
        except Exception as e:
            log_warn(f"[NFC] Lease complete: {e}")

    def abort(self):
        if not self.lease:
            return
        if self._updater:
            self._updater.stop()
        try:
            if self.lease.state not in (vim.HttpNfcLease.State.done, vim.HttpNfcLease.State.error):
                self.lease.HttpNfcLeaseAbort()
        except Exception:
            pass

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.abort()
        else:
            self.complete()
        self.lease = None
        self._updater = None
        return False


def stream_snapshot_disk_nfc(
    si,
    snap_obj,
    disk,
    storage,
    dest_rel_path,
    disk_index=0,
    progress_callback=None,
    progress_base=0,
    progress_total=100,
    speed_callback=None,
    is_cancelled_func=None,
    lease_session=None,
    connection_type=vsphere_context.CONN_AUTO,
):
    """Stream one snapshot disk via ExportSnapshot NFC (existing snapshot)."""
    from backup_engine import _get_session_cookies

    own_session = lease_session is None
    session = lease_session
    if own_session:
        session = NfcSnapshotLeaseSession(snap_obj, is_cancelled_func=is_cancelled_func)
        session.__enter__()

    try:
        url, file_size = _find_device_url(session.lease, disk, disk_index=disk_index)
        if not url:
            raise RuntimeError(
                f"No ExportSnapshot device URL for {os.path.basename(disk['rel_path'])}"
            )
        # ExportSnapshot leases frequently report fileSize=0 and send no
        # Content-Length, which leaves progress stuck at 0%. Fall back to the
        # disk's known capacity so the percentage can advance.
        if not file_size:
            file_size = int(disk.get("capacity_bytes", 0) or 0)
        log_info(
            f"[NFC] Streaming snapshot disk {os.path.basename(disk['rel_path'])} "
            f"→ {dest_rel_path}"
        )
        cookies = _get_session_cookies(si)
        return _stream_url_to_storage(
            url, storage, dest_rel_path, cookies,
            total_size_hint=file_size,
            progress_callback=progress_callback,
            progress_base=progress_base,
            progress_total=progress_total,
            speed_callback=speed_callback,
            is_cancelled_func=is_cancelled_func,
            lease_updater=session._updater if session else None,
        )
    finally:
        if own_session and session:
            session.__exit__(None, None, None)


