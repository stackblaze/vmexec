<h1 align="center">VMExec</h1>
<p align="center"><strong>Enterprise-grade VM backup & disaster recovery for VMware ESXi</strong></p>
<p align="center">Sponsored by <a href="https://stackblaze.com">Stackblaze.com</a></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.110-green?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Docker-ready-blue?logo=docker" alt="Docker">
  <img src="https://img.shields.io/badge/HTTPS-self--signed-brightgreen" alt="HTTPS">
  <img src="https://img.shields.io/badge/MFA-required-orange" alt="MFA">
  <img src="https://img.shields.io/badge/License-MIT-lightgrey" alt="License">
</p>

<p align="center">
  <img src="docs/screenshots/overview.png" alt="VMExec overview dashboard" width="800">
</p>

---

## Protect every VM. Recover in minutes.

**VMExec** is a self-hosted backup platform for **VMware ESXi and vCenter** — no agents, no per-VM licensing, no vendor lock-in. Deploy on Docker or Windows Server, point it at your hosts, and start protecting workloads in minutes.

Agentless snapshots. Incremental backups. One-click restore. Built for teams who want Veeam-class capability without the enterprise price tag.

---

## Features

### 🔄 Incremental backups that save time and space
Capture only changed blocks with **VMware Changed Block Tracking (CBT)**. Full backups when you need them, fast incrementals every day — with automatic synthetic fulls to keep chains healthy.

### 📦 Compression built in
Shrink backup storage costs with **zlib-compressed deltas** and **gzip-compressed VMDKs**. Less disk, less bandwidth, same recovery confidence.

### 📅 Smart retention with GFS
Set it and forget it with **Grandfather-Father-Son** policies — keep daily, weekly, and monthly restore points automatically. Or use simple count-based retention if you prefer.

### 🛡️ True 3-2-1 backup strategy
Every backup can be **copied to a secondary target** — SMB share, NFS export, or S3 bucket. Your data lives in two places without a second product or manual scripts.

### ⚡ Fast, flexible storage
Write backups to **SMB/CIFS, NFS, or S3-compatible** storage (AWS, Wasabi, MinIO). Primary and secondary targets — your infrastructure, your rules.

### 🔁 Disaster recovery, simplified
Browse backups by VM, pick any restore point, and deploy to **any host or datastore**. See your full **backup chain timeline** before you restore — no guessing which incremental you need.

### 🖥️ vCenter & ESXi — both supported
Connect a **standalone ESXi host or vCenter Server**. One dashboard for your entire VMware estate.

### 🔐 Security by default
**HTTPS**, mandatory **MFA (TOTP)**, and **role-based access** (Admin / Operator / Viewer). Every user authenticated, every action auditable.

### 🔌 REST API for automation
Integrate with your stack via **REST API v1** — JWT sessions, long-lived API keys, and OpenAPI docs. Automate backups, triggers, and monitoring from CI/CD or scripts.

### 📊 Operations dashboard
Real-time **task progress**, **storage utilization**, and **backup health** at a glance. Pause all jobs globally when you need a maintenance window.

### 🎨 Modern web UI
Light, Dark, and Cyberpunk themes. Guided **setup wizard** for first-run. Schedule backups with flexible daily, weekly, and monthly rules — per VM.

---

## Install (one line)

On a fresh **Ubuntu 22.04 or 24.04** VM (x86_64, 2+ CPUs, 4 GB+ RAM, 20 GB free on `/`, plus a blank disk of 100 GB+ for the cache):

```bash
curl -fsSL https://raw.githubusercontent.com/stackblaze/vmexec/main/install.sh | sudo bash
```

The installer checks the VM and installs everything VMExec needs (Docker, Python, kernel 9P support). It first asks what you want to do: start a **new appliance**, or **connect to existing backups** (see below). For a new appliance it then asks:

1. **S3 storage:** endpoint, region, bucket, folder and key. The key is checked against the bucket straight away.
2. **Cache disk:** pick a blank disk. It is formatted and used as a local cache. Backups live in S3, so this disk never fills up.
3. **VMware VDDK:** the path to `VMware-vix-disklib-*.x86_64.tar.gz`. VMware does not allow it to be redistributed, so download it from [Broadcom](https://developer.broadcom.com/sdks/vmware-virtual-disk-development-kit-vddk/latest) and copy it to the VM first.
4. **vCenter:** address and a backup account (optional, or later in Settings).
5. **A name** for alerts.
6. **Public URL (optional):** a hostname, the addresses allowed in, and a Bunny API key. The UI is then served at `https://<hostname>` with a Let's Encrypt certificate (DNS-01, so no inbound access is needed), SSH and HTTPS are open only to those addresses, and port 8000 is closed from outside. The VM's address itself comes from how you build the VM.

It shows a summary and only changes things after you confirm. Backups are stored through [ZeroFS](https://github.com/Barre/ZeroFS), encrypted with a password the installer generates. It writes **`/root/vmexec-recovery.env`**: the password plus everything a new VM needs to take over the backups (S3 location and key, public URL settings). **Put that file in your password manager:** without the password the backups cannot be read. Write a fresh copy at any time with `sudo /opt/vmexec/deploy/install.sh --write-recovery-file FILE`.

Re-running the installer is safe: it changes only what is different.

### Connect a new VM to existing backups

When an appliance is lost, build a new VM (same requirements), copy the recovery file and the VDDK tarball to it, run the one-line installer and choose **Connect to existing backups**. It asks only for the recovery file (or the S3 location, key and encryption password, typed in), the cache disk, the VDDK, and whether to set up the public URL. The backups, jobs, policies, protected VMs, the vCenter connection, the users with their MFA and the appliance's settings come back from the copy the appliance makes every hour. At the end it lists what came back.

The old appliance must be **off**: ZeroFS allows one appliance per repository. The installer refuses while the backups were written in the last 15 minutes (a running appliance writes every few minutes even when idle).

Without questions: `curl -fsSL …/install.sh | sudo bash -s -- --recovery-file F --vddk TARBALL --cache-dev /dev/sdb --yes`.

Without questions, for a new appliance: `curl -fsSL …/install.sh | sudo bash -s -- --bucket B --s3-endpoint URL --s3-region R --credentials-file F --vddk TARBALL`. See `deploy/install.sh --help` for all options.

Open **https://&lt;vm-ip&gt;:8000**. The first login is `admin` / `admin`; you are asked to set up MFA, then change the password under **Settings → Users**.

### Windows Server (legacy, without ZeroFS)

1. Download the latest release from [Releases](https://github.com/stackblaze-adam/vmexec/releases)
2. Extract and run **`setup.bat`** as Administrator
3. Open **https://localhost:8000**

---

## Screenshots

<table>
  <tr>
    <td><img src="docs/screenshots/overview.png" alt="Overview" width="400"></td>
    <td><img src="docs/screenshots/tasks.png" alt="Tasks" width="400"></td>
  </tr>
  <tr>
    <td align="center"><em>Overview — backup health, storage & activity</em></td>
    <td align="center"><em>Tasks — schedules, CBT, and one-click runs</em></td>
  </tr>
  <tr>
    <td colspan="2"><img src="docs/screenshots/recovery.png" alt="Recovery" width="820"></td>
  </tr>
  <tr>
    <td colspan="2" align="center"><em>Recovery — pick a VM, version, and deploy anywhere</em></td>
  </tr>
</table>

---

## Architecture

```
┌──────────────────────────────────────────────┐
│                   VMExec                      │
│  ┌─────────────────┐   ┌──────────────────┐  │
│  │  Web + REST API │   │  Worker daemon   │  │
│  │  (FastAPI :8000)│   │  (APScheduler)   │  │
│  └────────┬────────┘   └────────┬─────────┘  │
│           └──────────┬──────────┘            │
│                ┌─────▼─────┐                 │
│                │ SQLite DB │                 │
│                └─────┬─────┘                 │
└──────────────────────┼───────────────────────┘
                       │
     ┌─────────────────┼─────────────────┐
     │                 │                 │
┌────▼─────┐   ┌───────▼────────┐   ┌────▼──────┐
│ ESXi /   │   │ Primary storage│   │ Secondary │
│ vCenter  │   │ SMB / NFS / S3 │   │ copy tgt  │
└──────────┘   └────────────────┘   └───────────┘
```

Backup flow: snapshot → CBT incremental or full stream → compress → write to primary storage → optional secondary copy (3-2-1) → GFS retention cleanup.

---

## Configuration

All settings are in the web UI under **Settings**:

| Section | Description |
|---------|-------------|
| **Registered Hosts** | ESXi or vCenter credentials |
| **Target Storage** | Primary backup destination (SMB / NFS / S3) |
| **Engine** | CBT, compression, GFS retention, secondary copy, concurrency |
| **Email Alerts** | SMTP notifications per user/event |

---

## Requirements

- Python **3.11+** or Docker
- Network access to ESXi/vCenter on port **443**
- Backup storage: SMB share, NFS export, or S3 bucket
- **2 GB+ RAM** recommended

---

## Security

- Run `init_db.py` for a clean install — credentials and TLS certs stay in `data/` (gitignored)
- Change default credentials and enable MFA immediately
- Use a CA-signed TLS certificate in production

---

## Disclaimer

VMExec is an **independent** open-source project. It is not affiliated with, endorsed by, or sponsored by VMware, Broadcom, Veritas/Arctera (Backup Exec), Veeam, or any other backup vendor. VMware and ESXi are trademarks of Broadcom.

VMExec includes code from [NovaBak](https://github.com/haimtoledano/NovaBak) by [haimtoledano](https://github.com/haimtoledano), used under the [MIT License](LICENSE).

---

## License

MIT © VMExec · Sponsored by [Stackblaze.com](https://stackblaze.com)
