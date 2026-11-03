#!/usr/bin/env bash
# VMExec appliance installer: backups on ZeroFS (S3), one appliance per region.
#
# Run as root from a checkout of this repo (the appliance runs that checkout):
#
#   sudo deploy/install.sh --bucket central-vm-backups --s3-endpoint https://s3.us-central-1.idrivee2.com \
#        --s3-region us-central-1 --instance-name us-central-1 \
#        --credentials-file /root/s3.env --vddk /root/VMware-vix-disklib-9.1.0.0-25379531.x86_64.tar.gz
#
# What it sets up, each step only if needed (re-running changes nothing):
#   Docker, ZeroFS (pinned, checksum-verified), the cache disk (LABEL=vmexec-data
#   -> /var/lib/zerofs), zerofs.service, /mnt/backups (9P over a Unix socket),
#   Docker waiting for that mount, the S3 usage and daily database-copy timers,
#   .env, VDDK, the containers, and the app's storage setting.
#
# Options
#   --bucket B --s3-endpoint URL --s3-region R   S3 location (required)
#   --prefix P            folder in the bucket (default: vmexec)
#   --instance-name N     shown in alerts, e.g. the region slug (default: hostname)
#   --credentials-file F  KEY=VALUE file with AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
#                         (otherwise asked for, unless already installed)
#   --vddk TARBALL        VMware-vix-disklib-*.tar.gz (required unless one is in vendor/vddk/)
#   --cache-dev DEV       blank disk to format as the cache (default: the disk labelled vmexec-data)
#   --cache-gb N          ZeroFS cache budget in GB (default: 400)
#   --password-file F     ZeroFS encryption password (required with --recover on a new VM)
#   --recover             attach an existing ZeroFS repository (new VM, same bucket and password)
#   --recover-if-present  recover when the prefix already holds a repository, else create one
#                         (for automation, which cannot know in advance)
#   --change-location     move this appliance to a different bucket/prefix (fresh repository there)
#   --rotate-s3-key       replace the S3 key (with --credentials-file or asked for)
#   --yes                 do not ask before formatting the cache disk
#   --check               only run the checks and install the prerequisites, then stop
#
# The encryption password is generated once and never overwritten. Without it the
# backups in S3 cannot be read: on a fresh install it is written to
# /root/vmexec-zerofs-password.txt (0600) to put in your password manager and the vault.
set -euo pipefail

ZEROFS_VERSION=2.3.5
ZEROFS_URL="https://github.com/Barre/ZeroFS/releases/download/v${ZEROFS_VERSION}/zerofs-pgo-multiplatform.tar.gz"
ZEROFS_TARBALL_SHA256=367b2e79e05167af8409b28322f21b1ae5de033fc40820a3c27684a9974a56f2
ZEROFS_BINARY=zerofs-linux-amd64-pgo
ZEROFS_BINARY_SHA256=91651cb1894f77f6892d224bc119ac4a9bccabf1207d739f4ec71ff8c4e99e21

APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
MOUNT=/mnt/backups
CACHE_MNT=/var/lib/zerofs
CACHE_LABEL=vmexec-data
ZDIR=/etc/zerofs
ZENV=$ZDIR/zerofs.env
ZCONF=$ZDIR/config.toml
PASSWORD_OUT=/root/vmexec-zerofs-password.txt

BUCKET="" PREFIX=vmexec ENDPOINT="" REGION="" INSTANCE="" CRED_FILE="" VDDK="" CACHE_DEV=""
CACHE_GB=400 PASSWORD_FILE="" RECOVER=0 RECOVER_IF_PRESENT=0 CHANGE_LOCATION=0 ROTATE_KEY=0 YES=0 CHECK_ONLY=0

log() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf 'install.sh: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --bucket) BUCKET=$2; shift 2 ;;
    --prefix) PREFIX=${2%/}; PREFIX=${PREFIX#/}; shift 2 ;;
    --s3-endpoint) ENDPOINT=${2%/}; shift 2 ;;
    --s3-region) REGION=$2; shift 2 ;;
    --instance-name) INSTANCE=$2; shift 2 ;;
    --credentials-file) CRED_FILE=$2; shift 2 ;;
    --vddk) VDDK=$2; shift 2 ;;
    --cache-dev) CACHE_DEV=$2; shift 2 ;;
    --cache-gb) CACHE_GB=$2; shift 2 ;;
    --password-file) PASSWORD_FILE=$2; shift 2 ;;
    --recover) RECOVER=1; shift ;;
    --recover-if-present) RECOVER_IF_PRESENT=1; shift ;;
    --change-location) CHANGE_LOCATION=1; shift ;;
    --rotate-s3-key) ROTATE_KEY=1; shift ;;
    --yes) YES=1; shift ;;
    --check) CHECK_ONLY=1; shift ;;
    -h|--help) sed -n '2,39p' "$0"; exit 0 ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
done

[ "$(id -u)" = 0 ] || die "run as root"

# ---------------------------------------------------------------- 0. checks and prerequisites
# Everything VMExec needs is checked or installed here, before anything else changes.
warn() { printf '  \033[33mwarning:\033[0m %s\n' "$*"; }
ok() { printf '  ok   %s\n' "$*"; }
preflight() {
  log "Checks"
  . /etc/os-release
  [ "${ID:-}" = ubuntu ] || die "Ubuntu 22.04 or 24.04 is required (found ${PRETTY_NAME:-unknown})"
  case "${VERSION_ID:-}" in 22.04|24.04) ok "$PRETTY_NAME" ;; *) die "Ubuntu 22.04 or 24.04 is required (found $PRETTY_NAME)" ;; esac
  [ "$(uname -m)" = x86_64 ] || die "x86_64 is required (VDDK is x86_64 only; found $(uname -m))"
  [ "$(ps -p 1 -o comm=)" = systemd ] || die "systemd is required"
  cpus=$(nproc); [ "$cpus" -ge 2 ] || die "at least 2 CPUs are required (found $cpus)"
  mem_mb=$(( $(sed -n 's/^MemTotal: *\([0-9]*\) kB/\1/p' /proc/meminfo) / 1024 ))
  [ "$mem_mb" -ge 3500 ] || die "at least 4 GB of RAM is required (found $mem_mb MB)"
  [ "$mem_mb" -ge 7500 ] || warn "8 GB of RAM is recommended (found $mem_mb MB)"
  ok "$cpus CPUs, $mem_mb MB RAM"
  root_free=$(( $(df --output=avail -k / | tail -1) / 1024 / 1024 ))
  [ "$root_free" -ge 20 ] || die "at least 20 GB free on / is required for the containers (found ${root_free} GB)"
  ok "${root_free} GB free on /"

  log "Prerequisites"
  export DEBIAN_FRONTEND=noninteractive
  pkgs=(ca-certificates curl git python3 e2fsprogs util-linux kmod iproute2 procps)
  need=(); for p in "${pkgs[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || need+=("$p"); done
  if [ ${#need[@]} -gt 0 ]; then apt-get update -qq && apt-get install -y -qq "${need[@]}" >/dev/null; fi
  ok "packages: ${pkgs[*]}"

  # ZeroFS is mounted over 9P on a Unix socket. Kernels before 6.x carry the
  # socket transport inside 9pnet; newer ones split it out as 9pnet_fd.
  load_9p() {
    modprobe 9p 2>/dev/null || return 1
    if modinfo 9pnet_fd >/dev/null 2>&1; then modprobe 9pnet_fd 2>/dev/null || return 1; fi
    grep -qw 9p /proc/filesystems
  }
  if ! load_9p; then
    apt-get install -y -qq "linux-modules-extra-$(uname -r)" >/dev/null 2>&1 || true
    load_9p || die "the kernel has no 9P support. Install linux-modules-extra-$(uname -r) or use the generic kernel."
  fi
  { echo 9p; modinfo 9pnet_fd >/dev/null 2>&1 && echo 9pnet_fd; } > /etc/modules-load.d/vmexec-9p.conf
  ok "kernel 9P support"

  # S3 rejects signed requests when the clock is off by more than 15 minutes.
  if [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" != yes ]; then
    timedatectl set-ntp true 2>/dev/null || true
    for _ in $(seq 1 30); do [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = yes ] && break; sleep 1; done
  fi
  if [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = yes ]; then ok "clock synchronised (NTP)"
  else warn "the clock is not NTP-synchronised; S3 requests fail if it drifts more than 15 minutes"; fi

  for url in https://github.com https://download.docker.com ${ENDPOINT:+"$ENDPOINT"}; do
    host=${url#https://}; host=${host%%/*}
    getent hosts "$host" >/dev/null || die "cannot resolve $host (DNS)"
    curl -s -o /dev/null --max-time 20 "$url" || die "no HTTPS connection to $host (firewall or proxy?)"
  done
  ok "DNS and HTTPS to github.com, download.docker.com${ENDPOINT:+, ${ENDPOINT#https://}}"

  if ss -ltnH 'sport = :8000' | grep -q .; then
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx vmexec_web; then ok "port 8000 (VMExec)"
    else die "port 8000 is in use by something else ($(ss -ltnpH 'sport = :8000' | sed 's/.*users:((\("[^"]*"\).*/\1/' | head -1))"; fi
  else
    ok "port 8000 free"
  fi

  if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
    log "Docker"
    install -d -m 0755 /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  fi
  systemctl enable --now docker >/dev/null 2>&1 || true
  ok "$(docker --version | cut -d, -f1), $(docker compose version --short 2>/dev/null | sed 's/^/compose /')"
}
preflight
[ "$CHECK_ONLY" = 1 ] && { log "Checks passed"; exit 0; }

[ -n "$BUCKET" ] && [ -n "$ENDPOINT" ] && [ -n "$REGION" ] || die "--bucket, --s3-endpoint and --s3-region are required"
case "$ENDPOINT" in https://*) ;; *) die "--s3-endpoint must be https://" ;; esac
[[ "$CACHE_GB" =~ ^[0-9]+$ ]] && [ "$CACHE_GB" -ge 10 ] || die "--cache-gb must be a whole number >= 10"
INSTANCE=${INSTANCE:-$(hostname -s)}
URL="s3://$BUCKET/$PREFIX"

# KEY=VALUE reader that never sources (values may contain shell characters).
get_kv() { # file key
  [ -f "$1" ] || return 0
  python3 - "$1" "$2" <<'PY'
import sys
for line in open(sys.argv[1]):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    if k.strip().removeprefix("export ").strip() == sys.argv[2]:
        print(v.strip().strip("'\""), end="")
        break
PY
}

current_url() { [ -f "$ZCONF" ] && sed -n 's/^url = "\(.*\)"$/\1/p' "$ZCONF" || true; }

# ---------------------------------------------------------------- 2. ZeroFS binary
if ! echo "$ZEROFS_BINARY_SHA256  /usr/local/bin/zerofs" | sha256sum -c --status 2>/dev/null; then
  log "ZeroFS $ZEROFS_VERSION"
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  curl -fsSL "$ZEROFS_URL" -o "$tmp/zerofs.tar.gz"
  echo "$ZEROFS_TARBALL_SHA256  $tmp/zerofs.tar.gz" | sha256sum -c --status || die "ZeroFS download checksum mismatch"
  tar -xzf "$tmp/zerofs.tar.gz" -C "$tmp" "$ZEROFS_BINARY"
  echo "$ZEROFS_BINARY_SHA256  $tmp/$ZEROFS_BINARY" | sha256sum -c --status || die "ZeroFS binary checksum mismatch"
  install -m 0755 "$tmp/$ZEROFS_BINARY" /usr/local/bin/zerofs
fi

# ---------------------------------------------------------------- 3. location checks
OLD_URL=$(current_url)
if [ -n "$OLD_URL" ] && [ "$OLD_URL" != "$URL" ] && [ "$CHANGE_LOCATION" != 1 ]; then
  die "this appliance uses $OLD_URL; to move it to $URL run again with --change-location"
fi

# ---------------------------------------------------------------- 4. secrets
log "Credentials and encryption password"
install -d -m 0700 "$ZDIR"
AK=$(get_kv "$ZENV" AWS_ACCESS_KEY_ID); SK=$(get_kv "$ZENV" AWS_SECRET_ACCESS_KEY)
PW=$(get_kv "$ZENV" ZEROFS_PASSWORD)
if [ -n "$CRED_FILE" ]; then
  AK=$(get_kv "$CRED_FILE" AWS_ACCESS_KEY_ID); SK=$(get_kv "$CRED_FILE" AWS_SECRET_ACCESS_KEY)
  [ -n "$AK" ] && [ -n "$SK" ] || die "$CRED_FILE needs AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
elif [ -z "$AK" ] || [ "$ROTATE_KEY" = 1 ]; then
  [ -t 0 ] || die "no S3 key: pass --credentials-file"
  read -r -p "S3 access key ID: " AK
  read -r -s -p "S3 secret access key: " SK; echo
fi
NEW_PASSWORD=0
if [ -n "$PASSWORD_FILE" ]; then
  given=$(tr -d '\r\n' < "$PASSWORD_FILE")
  [ -n "$given" ] || die "$PASSWORD_FILE is empty"
  if [ -n "$PW" ] && [ "$PW" != "$given" ]; then die "--password-file differs from this appliance's password; refusing to replace it"; fi
  PW=$given
fi

# ---------------------------------------------------------------- 5. what is in S3
log "Checking $URL"
probe=$(mktemp)
AWS_ACCESS_KEY_ID=$AK AWS_SECRET_ACCESS_KEY=$SK \
  python3 "$APP_DIR/deploy/s3-usage.py" "$ENDPOINT" "$REGION" "$BUCKET" "$PREFIX" "$probe" >/dev/null \
  || die "cannot list s3://$BUCKET/$PREFIX/ with this key (wrong key, bucket or endpoint?)"
OBJECTS=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["objects"])' "$probe"); rm -f "$probe"
if [ "$RECOVER_IF_PRESENT" = 1 ] && [ "$OBJECTS" != 0 ] && [ "$OLD_URL" != "$URL" ]; then RECOVER=1; fi
if [ "$RECOVER" = 1 ] && [ "$OBJECTS" = 0 ]; then die "--recover: $URL is empty, nothing to recover"; fi
if [ "$OBJECTS" != 0 ] && [ "$RECOVER" != 1 ] && [ "$OLD_URL" != "$URL" ]; then
  die "$URL already holds $OBJECTS objects; use --recover to attach that repository, or pick an empty prefix"
fi

# Only now, knowing whether this is a recovery: a recovery must never get a
# freshly generated password (it could not open the repository).
if [ -z "$PW" ]; then
  [ "$RECOVER" = 1 ] && die "--recover needs --password-file (the password the backups were written with)"
  PW=$(python3 -c 'import secrets, string; a = string.ascii_letters + string.digits; print("".join(secrets.choice(a) for _ in range(64)))')
  NEW_PASSWORD=1
fi
umask 077
cat > "$ZENV.tmp" <<EOF
# ZeroFS for VMExec (deploy/install.sh). Root only. Never print.
ZEROFS_PASSWORD=$PW
AWS_ACCESS_KEY_ID=$AK
AWS_SECRET_ACCESS_KEY=$SK
EOF
mv "$ZENV.tmp" "$ZENV"; chmod 0600 "$ZENV"
umask 022
if [ "$NEW_PASSWORD" = 1 ]; then
  ( umask 077; printf '%s\n' "$PW" > "$PASSWORD_OUT" )
fi


# ---------------------------------------------------------------- 6. stop for a location change
if [ -n "$OLD_URL" ] && [ "$OLD_URL" != "$URL" ]; then
  log "Moving from $OLD_URL to $URL (the old repository stays in S3 until you delete it)"
  (cd "$APP_DIR" && docker compose stop) || true
  systemctl stop mnt-backups.mount 2>/dev/null || true
  systemctl stop zerofs 2>/dev/null || true
  cp -p "$ZCONF" "$ZCONF.before-$(date -u +%Y%m%dT%H%M%SZ)"
  # cache entries of the old repository (encrypted with the same password, useless now)
  find "$CACHE_MNT/cache" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
fi

# ---------------------------------------------------------------- 7. cache disk
if ! mountpoint -q "$CACHE_MNT"; then
  log "Cache disk"
  if ! blkid -L "$CACHE_LABEL" >/dev/null 2>&1; then
    [ -n "$CACHE_DEV" ] || die "no disk labelled $CACHE_LABEL: pass --cache-dev /dev/sdX (a blank disk)"
    [ -b "$CACHE_DEV" ] || die "$CACHE_DEV is not a block device"
    [ "$(lsblk -npo NAME "$CACHE_DEV" | wc -l)" = 1 ] || die "$CACHE_DEV has partitions; refusing to format it"
    [ -z "$(blkid -p -o value -s TYPE "$CACHE_DEV" 2>/dev/null)" ] || die "$CACHE_DEV has a filesystem; refusing to format it"
    if [ "$YES" != 1 ]; then
      read -r -p "Format $CACHE_DEV ($(lsblk -dno SIZE "$CACHE_DEV")) as the ZeroFS cache? [y/N] " a
      [ "$a" = y ] || die "not formatting"
    fi
    mkfs.ext4 -q -L "$CACHE_LABEL" -m 0 "$CACHE_DEV"
  fi
  grep -q "^LABEL=$CACHE_LABEL " /etc/fstab || echo "LABEL=$CACHE_LABEL $CACHE_MNT ext4 defaults 0 2" >> /etc/fstab
  mkdir -p "$CACHE_MNT"; systemctl daemon-reload; mount "$CACHE_MNT"
fi
install -d -m 0700 "$CACHE_MNT/cache"

# ---------------------------------------------------------------- 8. ZeroFS config and units
log "ZeroFS service and /mnt/backups"
host=${ENDPOINT#https://}
conf_before=$(sha256sum "$ZCONF" 2>/dev/null | cut -d' ' -f1 || true)
units_before=$(cat /etc/systemd/system/zerofs.service /etc/systemd/system/mnt-backups.mount \
  /etc/systemd/system/docker.service.d/vmexec-backups.conf 2>/dev/null | sha256sum | cut -d' ' -f1)
MOUNT_CHANGED=0
cat > "$ZCONF" <<EOF
# ZeroFS for VMExec (deploy/install.sh). Backups live in S3 at $URL;
# the cache disk only speeds things up. 9P on a local Unix socket only: no NFS
# (it acknowledges writes before they are durable), nothing on the network.
[cache]
dir = "$CACHE_MNT/cache"
disk_size_gb = $CACHE_GB.0
memory_size_gb = 2.0

[storage]
url = "$URL"
encryption_password = "\${ZEROFS_PASSWORD}"

[filesystem]
compression = "zstd-3"

[servers.ninep]
addresses = []
unix_socket = "/run/zerofs/9p.sock"

[servers.rpc]
addresses = ["127.0.0.1:7000"]

[aws]
access_key_id = "\${AWS_ACCESS_KEY_ID}"
secret_access_key = "\${AWS_SECRET_ACCESS_KEY}"
endpoint = "https://$host"
default_region = "$REGION"
EOF
chmod 0600 "$ZCONF"

cat > /etc/systemd/system/zerofs.service <<'EOF'
[Unit]
Description=ZeroFS (S3-backed filesystem for VMExec backups)
After=network-online.target
Wants=network-online.target
RequiresMountsFor=/var/lib/zerofs

[Service]
EnvironmentFile=/etc/zerofs/zerofs.env
RuntimeDirectory=zerofs
RuntimeDirectoryMode=0750
ExecStart=/usr/local/bin/zerofs run -c /etc/zerofs/config.toml
ExecStartPost=/bin/sh -c 'for i in $(seq 1 120); do [ -S /run/zerofs/9p.sock ] && exit 0; sleep 1; done; exit 1'
Restart=on-failure
RestartSec=5
# Give in-flight writes time to reach S3 on stop.
TimeoutStopSec=300
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/mnt-backups.mount <<'EOF'
[Unit]
Description=VMExec backup repository (ZeroFS over 9P)
Requires=zerofs.service
After=zerofs.service
BindsTo=zerofs.service

[Mount]
What=/run/zerofs/9p.sock
Where=/mnt/backups
Type=9p
Options=trans=unix,version=9p2000.L,cache=mmap,access=user,msize=1048576

[Install]
WantedBy=multi-user.target
EOF
# Docker (so the containers) never starts against an empty /mnt/backups on the root disk.
install -d /etc/systemd/system/docker.service.d
printf '[Unit]\nRequiresMountsFor=/mnt/backups\n' > /etc/systemd/system/docker.service.d/vmexec-backups.conf

# Bucket usage for the Storage tab (key stays on the host; only totals are written).
install -d -m 0755 /etc/vmexec
cat > /etc/vmexec/s3-usage.env <<EOF
# Non-secret settings for vmexec-s3-usage.service (keys come from $ZENV)
S3_ENDPOINT=$ENDPOINT
S3_REGION=$REGION
S3_BUCKET=$BUCKET
S3_PREFIX=$PREFIX
EOF
sed "s#/opt/vmexec#$APP_DIR#g" "$APP_DIR/deploy/vmexec-s3-usage.service" > /etc/systemd/system/vmexec-s3-usage.service
cp "$APP_DIR/deploy/vmexec-s3-usage.timer" /etc/systemd/system/
# Daily copy of the app database into backup storage, for --recover.
cat > /etc/systemd/system/vmexec-db-copy.service <<'EOF'
[Unit]
Description=VMExec: copy the database into backup storage (for install.sh --recover)
Requires=docker.service mnt-backups.mount
After=docker.service mnt-backups.mount

[Service]
Type=oneshot
ExecStart=/usr/bin/docker exec vmexec_worker python -m services.appliance_setup copy-db /mnt/backups/_appliance
EOF
cat > /etc/systemd/system/vmexec-db-copy.timer <<'EOF'
[Unit]
Description=VMExec: daily database copy into backup storage

[Timer]
OnCalendar=*-*-* 12:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable zerofs.service mnt-backups.mount vmexec-s3-usage.timer vmexec-db-copy.timer >/dev/null 2>&1
units_after=$(cat /etc/systemd/system/zerofs.service /etc/systemd/system/mnt-backups.mount \
  /etc/systemd/system/docker.service.d/vmexec-backups.conf | sha256sum | cut -d' ' -f1)
if [ "$conf_before" != "$(sha256sum "$ZCONF" | cut -d' ' -f1)" ] || [ "$units_before" != "$units_after" ] \
   || [ "$CHANGE_LOCATION" = 1 ] || [ "$ROTATE_KEY" = 1 ] || ! findmnt -n "$MOUNT" >/dev/null; then
  MOUNT_CHANGED=1
  systemctl stop mnt-backups.mount 2>/dev/null || true
  systemctl restart zerofs
fi
systemctl start zerofs mnt-backups.mount
findmnt -n "$MOUNT" >/dev/null || die "$MOUNT did not mount"
probe_file="$MOUNT/.install-probe-$$"
dd if=/dev/urandom of="$probe_file" bs=1M count=4 conv=fsync status=none && rm -f "$probe_file" \
  || die "write check on $MOUNT failed"

# ---------------------------------------------------------------- 9. app: .env, VDDK, recover
log "VMExec ($APP_DIR)"
ENVF="$APP_DIR/.env"
touch "$ENVF"
set_env() { # key value
  if grep -q "^$1=" "$ENVF"; then sed -i "s#^$1=.*#$1=$2#" "$ENVF"; else echo "$1=$2" >> "$ENVF"; fi
}
grep -q '^COMPOSE_PROJECT_NAME=' "$ENVF" || echo "COMPOSE_PROJECT_NAME=vmexec" >> "$ENVF"
set_env VMEXEC_BACKUP_DIR "$MOUNT"
set_env VMEXEC_INSTANCE_NAME "$INSTANCE"
set_env VMEXEC_REPO_LOCATION "$BUCKET/$PREFIX"
set_env VMEXEC_REPO_ENCRYPTED 1
set_env VMEXEC_ZEROFS_CACHE_LIMIT_GB "$CACHE_GB"

install -d -m 0755 "$APP_DIR/vendor/vddk"
if [ -n "$VDDK" ]; then
  [ -f "$VDDK" ] || die "$VDDK not found"
  case "$(basename "$VDDK")" in VMware-vix-disklib-*.tar.gz) ;; *) die "--vddk must be a VMware-vix-disklib-*.tar.gz" ;; esac
  install -m 0644 "$VDDK" "$APP_DIR/vendor/vddk/"
fi
ls "$APP_DIR"/vendor/vddk/VMware-vix-disklib-*.tar.gz >/dev/null 2>&1 \
  || die "VDDK is required: pass --vddk VMware-vix-disklib-*.tar.gz (from Broadcom; never bundled)"

project=$(get_kv "$ENVF" COMPOSE_PROJECT_NAME)
volume="${project}_novabak_data"
if [ "$RECOVER" = 1 ] && [ -f "$MOUNT/_appliance/backup_system.db" ]; then
  vol_dir=$(docker volume inspect -f '{{.Mountpoint}}' "$volume" 2>/dev/null || true)
  if [ -z "$vol_dir" ] || [ ! -f "$vol_dir/backup_system.db" ]; then
    log "Restoring the database copy from $MOUNT/_appliance"
    docker volume create "$volume" >/dev/null
    vol_dir=$(docker volume inspect -f '{{.Mountpoint}}' "$volume")
    for f in backup_system.db secret.key session.key; do
      [ -f "$MOUNT/_appliance/$f" ] && install -m 0600 "$MOUNT/_appliance/$f" "$vol_dir/$f"
    done
  else
    log "Keeping this VM's own database (it already has one)"
  fi
fi

# ---------------------------------------------------------------- 10. containers
log "Containers"
# Containers bind /mnt/backups when they start: restart Docker (and so them)
# only when the mount or Docker's mount dependency changed.
if [ "$MOUNT_CHANGED" = 1 ]; then systemctl restart docker; fi
(cd "$APP_DIR" && docker compose up -d --build)
for _ in $(seq 1 60); do
  curl -sk -o /dev/null https://127.0.0.1:8000/ && break
  sleep 2
done
curl -sk -o /dev/null https://127.0.0.1:8000/ || die "the web UI did not come up (docker compose logs)"
docker exec vmexec_worker python -m services.appliance_setup storage "$MOUNT"
systemctl start vmexec-s3-usage.service || true

# ---------------------------------------------------------------- done
log "Done"
echo "  Backups:  $URL (ZeroFS, encrypted), mounted at $MOUNT"
echo "  Cache:    $CACHE_MNT ($CACHE_GB GB budget)"
echo "  UI:       https://$(hostname -I | awk '{print $1}'):8000"
if [ "$NEW_PASSWORD" = 1 ]; then
  echo
  echo "  NEW encryption password written to $PASSWORD_OUT (root only)."
  echo "  Without it the backups in S3 cannot be read. Put it in your password manager"
  echo "  and the region vault, then delete that file."
fi
