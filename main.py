import os
import sys
import datetime
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from models import SessionLocal, init_db, VM, User, RestoreJob
import auth
from logger_util import log_info, log_critical

app = FastAPI(title="VMExec")

from api.v1.router import router as v1_router
v1_app = FastAPI(
    title="VMExec API v1",
    version="1.1.1",
    docs_url="/docs",
    openapi_url="/openapi.json",
)
v1_app.include_router(v1_router)
app.mount("/api/v1", v1_app)

_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(_static_dir, exist_ok=True)
SPA_DIST = os.path.join(_static_dir, "dist")
SPA_INDEX = os.path.join(SPA_DIST, "index.html")


def spa_index():
    """index.html, never reused without checking: it names the current
    build's hashed assets, so a cached copy keeps running the old UI after
    a deploy (seen 2026-11-03: a removed Settings card kept showing)."""
    return FileResponse(SPA_INDEX, headers={"Cache-Control": "no-cache"})


class _HashedAssets(StaticFiles):
    """/assets/* names carry a content hash: safe to cache for a year."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if resp.status_code == 200:
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp
app.mount("/static", StaticFiles(directory=_static_dir), name="static")
if os.path.isdir(os.path.join(SPA_DIST, "assets")):
    app.mount("/assets", _HashedAssets(directory=os.path.join(SPA_DIST, "assets")), name="spa_assets")


def spa_enabled():
    return os.path.isfile(SPA_INDEX)
@app.on_event("startup")
def startup_event():
    init_db()
    # Create default admin and password = admin if no users exist
    # Cleanup: Reset any stuck jobs flag in the DB on startup
    db = SessionLocal()
    pid = os.getpid()
    log_info(f"[PID {pid}] Application starting up...")
    vms = db.query(VM).all()
    for v in vms:
        if v.current_action:
            log_info(f"[PID {pid}] Clearing stale action '{v.current_action}' for VM {v.vm_name}")
            v.progress = 0
            v.current_action = ""

    # Reconcile stale restores: the restore executor runs in this process, so an
    # "In Progress" restore cannot survive a restart — mark it Failed instead of
    # leaving it stuck forever.
    stale_restores = db.query(RestoreJob).filter(RestoreJob.status == "In Progress").all()
    for job in stale_restores:
        log_info(f"[PID {pid}] Marking interrupted restore '{job.target_name}' as Failed")
        job.status = "Failed"
        job.error_message = job.error_message or "Restore was interrupted by a service restart."
        job.end_time = datetime.datetime.utcnow()
    
    # Create default admin and password = admin if no users exist
    if not db.query(User).first():
        hashed = auth.get_password_hash("admin")
        admin = User(username="admin", hashed_password=hashed)
        db.add(admin)
        log_info(f"[PID {pid}] Created default admin user.")
        
    db.commit()
    db.close()
    
    # Keep a reference to the scheduler so it stays alive
    log_info(f"[PID {pid}] Control Plane (Web UI) active. Worker Daemon handles scheduler externally.")


@app.get("/{full_path:path}")
def spa_catchall(full_path: str):
    """The Vue app (history mode): every path that is not /api/v1, /assets or /static."""
    if not spa_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    if full_path.startswith("api/") or full_path == "api":
        raise HTTPException(status_code=404, detail="Not found")
    asset = os.path.join(SPA_DIST, full_path)
    if full_path and os.path.isfile(asset):
        return FileResponse(asset)
    return spa_index()


if __name__ == "__main__":
    lock_file = "app.lock"
    lock_fh = None
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except:
            log_critical("Another instance of VM Backup Enterprise is already running.")
            log_critical("Please stop the existing service or manual process before starting a new one.")
            sys.exit(1)
            
    try:
        # Open and keep open to hold the lock on Windows
        lock_fh = open(lock_file, "w")
        lock_fh.write(str(os.getpid()))
        lock_fh.flush()

        # Generate / verify SSL certificate
        from ssl_util import ensure_ssl_cert
        cert_file, key_file = ensure_ssl_cert()

        import uvicorn.config
        l_config = uvicorn.config.LOGGING_CONFIG
        l_config["formatters"]["access"]["fmt"] = "[%(asctime)s] %(levelprefix)s %(message)s"
        l_config["formatters"]["default"]["fmt"] = "[%(asctime)s] %(levelprefix)s %(message)s"

        log_info("=" * 55)
        log_info("  VMExec is starting on HTTPS port 8000")
        log_info("Open: https://localhost:8000")
        log_info("  (Browser will warn about self-signed cert - click Advanced -> Proceed)")
        log_info("=" * 55)

        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            ssl_certfile=cert_file,
            ssl_keyfile=key_file,
            log_config=l_config,
        )
    finally:
        if lock_fh:
            lock_fh.close()
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except:
                pass

