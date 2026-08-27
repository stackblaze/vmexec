<h1 align="center">VMExec</h1>
<p align="center"><strong>Self-hosted, agentless VM backup for VMware ESXi and vCenter</strong></p>
<p align="center">Sponsored by <a href="https://stackblaze.com">Stackblaze.com</a></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Docker-ready-blue?logo=docker" alt="Docker">
  <img src="https://img.shields.io/badge/License-MIT-lightgrey" alt="License">
</p>

<p align="center">
  <img src="docs/screenshots/overview.png" alt="VMExec overview dashboard" width="800">
</p>

VMExec backs up VMware VMs without agents, per-VM licensing, or vendor lock-in. It runs on Docker or Windows Server and manages the full backup lifecycle: snapshot, incremental or full capture, compression, retention, and restore.

## Features

- **CBT incrementals** — changed-block capture via VMware Changed Block Tracking, with scheduled fulls and synthetic fulls to keep chains healthy
- **Multiple transports** — VDDK/NBD when installed, with automatic NFC and HTTPS fallback
- **Compression** — zlib-compressed deltas, gzip-compressed full VMDKs
- **Retention** — Grandfather-Father-Son or count-based policies
- **3-2-1 copies** — optional secondary copy of every backup to SMB, NFS, or S3-compatible storage
- **Restore** — any restore point, to any host or datastore, with a full chain timeline
- **vCenter and standalone ESXi** — one dashboard for both
- **Security** — HTTPS, mandatory TOTP MFA, role-based access (Admin / Operator / Viewer)
- **REST API** — JWT sessions, API keys, OpenAPI docs
- **Web UI** — live task progress, storage utilization, per-VM schedules, guided setup wizard

## Quick start (Docker)

```bash
git clone https://github.com/stackblaze/vmexec.git
cd vmexec

python init_db.py
docker compose up -d
```

Open **https://localhost:8000** (self-signed certificate) and log in with `admin` / `admin`. Set up MFA on first login, then change the admin password under **Users**.

### Windows Server

1. Download the latest [release](https://github.com/stackblaze/vmexec/releases)
2. Extract and run **`setup.bat`** as Administrator
3. Open **https://localhost:8000**

## Architecture

FastAPI web/API service and an APScheduler worker daemon over a shared SQLite database. Backup flow: snapshot → CBT incremental or full stream → compress → primary storage → optional secondary copy → retention cleanup.

## Configuration

All settings live in the web UI under **Settings**:

| Section | Description |
|---------|-------------|
| **Registered Hosts** | ESXi or vCenter credentials (encrypted at rest) |
| **Target Storage** | Primary backup destination (SMB / NFS / S3) |
| **Engine** | CBT, compression, retention, secondary copy, concurrency |
| **Email Alerts** | SMTP notifications per user/event |

## Requirements

- Python 3.11+ or Docker
- Network access to ESXi/vCenter on port 443
- Backup storage: SMB share, NFS export, or S3 bucket
- 2 GB+ RAM recommended

## Security notes

- Run `init_db.py` on a clean install — credentials and TLS certificates stay in `data/` (gitignored)
- Change the default credentials and enroll MFA immediately
- Use a CA-signed TLS certificate in production

## Disclaimer

VMExec is an independent open-source project. It is not affiliated with, endorsed by, or sponsored by VMware, Broadcom, Veritas/Arctera, Veeam, or any other backup vendor. VMware and ESXi are trademarks of Broadcom.

VMExec includes code from [NovaBak](https://github.com/haimtoledano/NovaBak) by [haimtoledano](https://github.com/haimtoledano), used under the [MIT License](LICENSE).

## License

MIT © VMExec · Sponsored by [Stackblaze.com](https://stackblaze.com)
