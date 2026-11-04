#!/usr/bin/env bash
# VMExec one-line installer. On a fresh Ubuntu 22.04/24.04 VM:
#
#   curl -fsSL https://raw.githubusercontent.com/stackblaze/vmexec/main/install.sh | sudo bash
#
# First question: a new appliance, or connect this VM to existing backups (it
# takes over from an appliance that is gone). Connecting needs the recovery file
# a new install writes (or the S3 location, key and encryption password typed
# in) plus the VDDK tarball; everything else comes back from the backups. Then
# it shows a summary and installs: it clones VMExec to /opt/vmexec and runs
# deploy/install.sh. Re-running it is safe.
#
# Without questions (automation): pass deploy/install.sh options after --:
#   curl -fsSL .../install.sh | sudo bash -s -- --recovery-file /root/vmexec-recovery.env --vddk V --cache-dev /dev/sdb --yes
#   curl -fsSL .../install.sh | sudo bash -s -- --bucket B --s3-endpoint URL --s3-region R ...
#
# Environment: VMEXEC_REF (branch or tag, default main), VMEXEC_DIR (default /opt/vmexec),
#              VMEXEC_REPO (default https://github.com/stackblaze/vmexec.git).
set -euo pipefail

REPO=${VMEXEC_REPO:-https://github.com/stackblaze/vmexec.git}
REF=${VMEXEC_REF:-main}
DIR=${VMEXEC_DIR:-/opt/vmexec}
QUIET_MIN_REQUIRED=15   # same as deploy/install.sh WRITER_QUIET_MIN

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
die() { printf '\n\033[31mVMExec installer: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root: curl -fsSL <url>/install.sh | sudo bash"
[ -r /etc/os-release ] && . /etc/os-release
[ "${ID:-}" = ubuntu ] || die "Ubuntu is required (found ${PRETTY_NAME:-unknown})"

# ------------------------------------------------------------------ get the code
fetch_code() {
  command -v git >/dev/null || { apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git ca-certificates curl python3 >/dev/null; }
  if [ -d "$DIR/.git" ]; then
    git -C "$DIR" fetch -q origin "$REF"
    git -C "$DIR" checkout -q -B "$REF" "origin/$REF" 2>/dev/null || git -C "$DIR" checkout -q "$REF"
  else
    git clone -q --branch "$REF" "$REPO" "$DIR"
  fi
  git config --system --get-all safe.directory 2>/dev/null | grep -qx "$DIR" || git config --system --add safe.directory "$DIR"
}

# ------------------------------------------------------------------ non-interactive
if [ $# -gt 0 ]; then
  fetch_code
  exec "$DIR/deploy/install.sh" "$@"
fi

# ------------------------------------------------------------------ wizard
[ -r /dev/tty ] || die "no terminal for questions: pass options after -- (see the top of this script)"
exec 3</dev/tty

ask() { # var "question" "default"
  local _v _d=${3:-}
  if [ -n "$_d" ]; then printf '  %s [%s]: ' "$2" "$_d" >/dev/tty; else printf '  %s: ' "$2" >/dev/tty; fi
  IFS= read -r _v <&3 || true
  printf -v "$1" '%s' "${_v:-$_d}"
}
ask_secret() { # var "question"
  local _v
  printf '  %s: ' "$2" >/dev/tty
  IFS= read -rs _v <&3 || true
  printf '\n' >/dev/tty
  printf -v "$1" '%s' "$_v"
}
yesno() { # "question" default(y|n)
  local _a
  ask _a "$1 (y/n)" "$2"
  [ "${_a,,}" = y ] || [ "${_a,,}" = yes ]
}
kv() { # file key: KEY=VALUE reader that never sources
  [ -f "$1" ] || return 0
  python3 - "$1" "$2" <<'PY'
import sys
for line in open(sys.argv[1]):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        if k.strip().removeprefix("export ").strip() == sys.argv[2]:
            print(v.strip().strip("'\""), end="")
            break
PY
}

clear 2>/dev/null || true
bold "VMExec installer"
info "VM backups for vCenter, stored in S3 through ZeroFS (encrypted)."
info "First it checks this VM and installs what VMExec needs (Docker, Python, kernel 9P"
info "support). Then it asks a few questions and shows a summary. Your backup setup is"
info "only changed after you confirm."
echo
fetch_code || die "could not download VMExec from $REPO ($REF)"
"$DIR/deploy/install.sh" --check || die "this VM does not meet the requirements (see above)"
echo

# Existing install: offer the current settings as defaults.
CUR_URL=$(sed -n 's/^url = "s3:\/\/\(.*\)"$/\1/p' /etc/zerofs/config.toml 2>/dev/null || true)
CUR_ENDPOINT=$(sed -n 's/^endpoint = "\(.*\)"$/\1/p' /etc/zerofs/config.toml 2>/dev/null || true)
CUR_REGION=$(sed -n 's/^default_region = "\(.*\)"$/\1/p' /etc/zerofs/config.toml 2>/dev/null || true)
CUR_CACHE=$(sed -n 's/^disk_size_gb = \([0-9]*\).*/\1/p' /etc/zerofs/config.toml 2>/dev/null || true)
CUR_NAME=$(kv "$DIR/.env" VMEXEC_INSTANCE_NAME)
CUR_DOMAIN=$(kv /etc/vmexec/public.env VMEXEC_PUBLIC_DOMAIN)
CUR_ALLOW=$(kv /etc/vmexec/public.env VMEXEC_ALLOW_FROM)
HAVE_KEY=0; [ -n "$(kv /etc/zerofs/zerofs.env AWS_ACCESS_KEY_ID)" ] && HAVE_KEY=1
HAVE_PASSWORD=0; [ -n "$(kv /etc/zerofs/zerofs.env ZEROFS_PASSWORD)" ] && HAVE_PASSWORD=1

secrets=$(mktemp -d); chmod 700 "$secrets"; trap 'rm -rf "$secrets"' EXIT

# 0. What to do
if [ -n "$CUR_URL" ]; then
  info "Existing install found: backups at s3://$CUR_URL"
  MODE=reconfigure
else
  bold "What do you want to do?"
  info "1) New appliance: start a new, empty backup repository"
  info "2) Connect to existing backups: this VM takes over from an appliance that is gone"
  info "   (needs its recovery file, or its S3 key and encryption password)"
  ask pick "Choice" 1
  case "$pick" in 1) MODE=new ;; 2) MODE=connect ;; *) die "pick 1 or 2" ;; esac
fi
echo

# 1. S3 (and, when connecting, the encryption password)
bold "1. Backup storage (S3)"
ENDPOINT="" REGION="" BUCKET="" PREFIX="" AK="" SK="" PASSWORD="" FROM_FILE=""
REC_DOMAIN="" REC_ALLOW="" REC_BUNNY=""
if [ "$MODE" = connect ]; then
  found=$(ls -t /root/vmexec-recovery*.env /home/*/vmexec-recovery*.env /tmp/vmexec-recovery*.env 2>/dev/null | head -1 || true)
  info "The recovery file holds the S3 location and key and the encryption password."
  ask FROM_FILE "Recovery file (leave empty to type the values in)" "$found"
  if [ -n "$FROM_FILE" ]; then
    [ -f "$FROM_FILE" ] || die "$FROM_FILE not found"
    ENDPOINT=$(kv "$FROM_FILE" VMEXEC_S3_ENDPOINT); REGION=$(kv "$FROM_FILE" VMEXEC_S3_REGION)
    BUCKET=$(kv "$FROM_FILE" VMEXEC_BUCKET); PREFIX=$(kv "$FROM_FILE" VMEXEC_PREFIX)
    AK=$(kv "$FROM_FILE" AWS_ACCESS_KEY_ID); SK=$(kv "$FROM_FILE" AWS_SECRET_ACCESS_KEY)
    PASSWORD=$(kv "$FROM_FILE" ZEROFS_PASSWORD)
    REC_DOMAIN=$(kv "$FROM_FILE" VMEXEC_PUBLIC_DOMAIN); REC_ALLOW=$(kv "$FROM_FILE" VMEXEC_ALLOW_FROM)
    REC_BUNNY=$(kv "$FROM_FILE" BUNNY_API_KEY)
    for v in ENDPOINT REGION BUCKET AK SK PASSWORD; do [ -n "${!v}" ] || die "$FROM_FILE is incomplete (no $v)"; done
    PREFIX=${PREFIX:-vmexec}
    info "From the file: s3://$BUCKET/$PREFIX ($ENDPOINT, $REGION), key and password"
  fi
fi
if [ -z "$BUCKET" ]; then
  while :; do
    ask ENDPOINT "S3 endpoint (https://...)" "${CUR_ENDPOINT:-}"
    ENDPOINT=${ENDPOINT%/}
    case "$ENDPOINT" in https://?*) break ;; *) info "It must start with https://" ;; esac
  done
  guess_region=$(printf '%s' "$ENDPOINT" | sed -n 's#^https://s3\.\([a-z0-9-]*\)\.\(idrivee2\.com\|amazonaws\.com\|wasabisys\.com\)$#\1#p')
  ask REGION "Region" "${CUR_REGION:-${guess_region:-us-east-1}}"
  ask BUCKET "Bucket" "${CUR_URL%%/*}"
  [ -n "$BUCKET" ] || die "a bucket is required"
  cur_prefix=""; [ -n "$CUR_URL" ] && [ "${CUR_URL%%/*}" = "$BUCKET" ] && cur_prefix=${CUR_URL#*/}
  ask PREFIX "Folder in the bucket" "${cur_prefix:-vmexec}"
  PREFIX=${PREFIX#/}; PREFIX=${PREFIX%/}
fi

USE_EXISTING_KEY=0
if [ -z "$AK" ]; then
  if [ "$HAVE_KEY" = 1 ] && ! yesno "Replace the S3 key this appliance already has?" n; then
    USE_EXISTING_KEY=1
    AK=$(kv /etc/zerofs/zerofs.env AWS_ACCESS_KEY_ID); SK=$(kv /etc/zerofs/zerofs.env AWS_SECRET_ACCESS_KEY)
  else
    ask AK "S3 access key ID" ""
    ask_secret SK "S3 secret access key (hidden)"
    [ -n "$AK" ] && [ -n "$SK" ] || die "an S3 key is required"
  fi
fi

# Check the key against the bucket now, not halfway through the install.
probe="$secrets/probe.json"
if ! AWS_ACCESS_KEY_ID=$AK AWS_SECRET_ACCESS_KEY=$SK python3 "$DIR/deploy/s3-usage.py" "$ENDPOINT" "$REGION" "$BUCKET" "$PREFIX" "$probe" >/dev/null 2>&1; then
  die "cannot list s3://$BUCKET/$PREFIX/ with that key. Check the endpoint, region, bucket and key."
fi
OBJECTS=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["objects"])' "$probe")
QUIET=$(python3 -c '
import datetime, json, sys
n = json.load(open(sys.argv[1])).get("newest")
print(-1 if not n else int((datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(n)).total_seconds() // 60))' "$probe")
info "Key works. s3://$BUCKET/$PREFIX/ holds $OBJECTS objects."

SAME_AS_NOW=0; [ "$CUR_URL" = "$BUCKET/$PREFIX" ] && SAME_AS_NOW=1
case "$MODE" in
  connect)
    [ "$OBJECTS" != 0 ] || die "s3://$BUCKET/$PREFIX/ is empty: there are no backups to connect to"
    ;;
  new)
    if [ "$OBJECTS" != 0 ]; then
      info "That folder already has a VMExec repository."
      yesno "Connect to it instead (this VM takes over its backups)?" y || die "pick an empty folder, or connect to the existing one"
      MODE=connect
    fi
    ;;
  reconfigure)
    if [ "$SAME_AS_NOW" != 1 ] && [ "$OBJECTS" != 0 ]; then
      info "That folder already has a VMExec repository."
      yesno "Connect this appliance to it (needs its encryption password)?" y || die "pick an empty folder, or connect to the existing one"
      MODE=connect
    elif [ "$SAME_AS_NOW" != 1 ]; then
      info "This appliance stores backups at s3://$CUR_URL today. The new folder starts empty;"
      info "the old one stays in S3 until you delete it."
      yesno "Move this appliance to s3://$BUCKET/$PREFIX?" n || die "nothing changed"
      MODE=move
    fi
    ;;
esac

FORCE=0
if [ "$MODE" = connect ]; then
  # ZeroFS allows one writer per repository.
  info "Last written $QUIET minutes ago."
  info "The appliance that wrote these backups must be OFF, and stay off: ZeroFS allows"
  info "only one appliance per repository."
  if [ "$QUIET" -lt "$QUIET_MIN_REQUIRED" ]; then
    info "Written less than $QUIET_MIN_REQUIRED minutes ago: another appliance is probably still running."
    yesno "Are you sure the old appliance is off? (otherwise: power it off and run this again later)" n || die "nothing changed"
    FORCE=1
  else
    yesno "Is the old appliance off?" y || die "power it off first (or stop zerofs and docker on it), then run this again"
  fi
  if [ -z "$PASSWORD" ] && [ "$HAVE_PASSWORD" != 1 ]; then
    ask_secret PASSWORD "Encryption password of these backups (hidden)"
    [ -n "$PASSWORD" ] || die "the password is required to connect"
  fi
fi
echo

# 2. Cache disk
bold "2. Cache disk"
CACHE_DEV=""
if blkid -L vmexec-data >/dev/null 2>&1; then
  info "Using the disk labelled vmexec-data ($(lsblk -dno SIZE "$(blkid -L vmexec-data)" 2>/dev/null))."
  CACHE_SIZE_GB=$(( $(lsblk -bdno SIZE "$(blkid -L vmexec-data)") / 1000000000 ))
else
  mapfile -t blanks < <(lsblk -dbnpo NAME,SIZE,TYPE | while read -r d s t; do
    [ "$t" = disk ] || continue
    [ "$(lsblk -npo NAME "$d" | wc -l)" = 1 ] || continue
    [ -z "$(blkid -p -o value -s TYPE "$d" 2>/dev/null)" ] || continue
    findmnt -rno SOURCE | grep -qx "$d" && continue
    echo "$d $((s / 1000000000))"
  done)
  [ ${#blanks[@]} -gt 0 ] || die "no blank disk found for the cache. Add a disk to this VM (100 GB or more) and run again."
  info "Blank disks (the one you pick is formatted):"
  for i in "${!blanks[@]}"; do info "  $((i + 1))) ${blanks[$i]%% *}  ${blanks[$i]##* } GB"; done
  pick=""
  ask pick "Disk number" 1
  [[ "$pick" =~ ^[0-9]+$ ]] && [ "$pick" -ge 1 ] && [ "$pick" -le ${#blanks[@]} ] || die "no such disk"
  CACHE_DEV=${blanks[$((pick - 1))]%% *}
  CACHE_SIZE_GB=${blanks[$((pick - 1))]##* }
fi
suggest=$(( CACHE_SIZE_GB * 85 / 100 )); [ "$suggest" -gt 400 ] && suggest=400; [ "$suggest" -lt 10 ] && suggest=10
ask CACHE_GB "Cache size in GB (more = faster restores)" "${CUR_CACHE:-$suggest}"
[[ "$CACHE_GB" =~ ^[0-9]+$ ]] && [ "$CACHE_GB" -ge 10 ] || die "cache size must be a whole number of GB, at least 10"
echo

# 3. VDDK
bold "3. VMware VDDK"
VDDK=""
if ls "$DIR"/vendor/vddk/VMware-vix-disklib-*.tar.gz >/dev/null 2>&1; then
  info "Already in place: $(basename "$(ls "$DIR"/vendor/vddk/VMware-vix-disklib-*.tar.gz | head -1)")"
else
  found=$(ls -t /root/VMware-vix-disklib-*.tar.gz /home/*/VMware-vix-disklib-*.tar.gz /tmp/VMware-vix-disklib-*.tar.gz "$PWD"/VMware-vix-disklib-*.tar.gz 2>/dev/null | head -1 || true)
  info "VMware does not allow VDDK to be redistributed: download the Linux tarball"
  info "(VMware-vix-disklib-*.x86_64.tar.gz) from developer.broadcom.com and copy it to this VM."
  ask VDDK "Path to the VDDK tarball" "$found"
  [ -f "$VDDK" ] || die "$VDDK not found"
fi
echo

# 4. vCenter and name: when connecting, both come back from the backups.
VC_ADDR="" VC_USER="" VC_PASS="" INSTANCE=""
if [ "$MODE" = connect ]; then
  bold "4. vCenter and name"
  info "Come back from the backups (the old appliance's database), with its jobs,"
  info "policies, protected VMs and users."
else
  bold "4. vCenter"
  if [ -f "$DIR/.env" ] && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx vmexec_worker \
     && docker exec vmexec_worker python -c "from models import SessionLocal, ESXiHost; import sys; sys.exit(0 if SessionLocal().query(ESXiHost).count() else 1)" 2>/dev/null; then
    info "Already connected (change it under Settings → vCenter)."
  elif yesno "Connect vCenter now?" y; then
    ask VC_ADDR "vCenter address (FQDN or IP)" ""
    VC_ADDR=${VC_ADDR#https://}; VC_ADDR=${VC_ADDR%%/*}
    [ -n "$VC_ADDR" ] || die "an address is required"
    code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 15 "https://$VC_ADDR/sdk" || true)
    [ "$code" != 000 ] || die "cannot reach https://$VC_ADDR (port 443) from this VM"
    ask VC_USER "vCenter user (a backup account, e.g. vmexec@vsphere.local)" ""
    ask_secret VC_PASS "Password (hidden)"
    [ -n "$VC_USER" ] && [ -n "$VC_PASS" ] || die "user and password are required"
    info "Reachable. The login is checked when it is connected, after the install."
  else
    info "Skipped: connect it later under Settings → vCenter."
  fi
  echo
  bold "5. Name"
  ask INSTANCE "Appliance name (shown in alerts)" "${CUR_NAME:-$(hostname -s)}"
fi
echo

# 6. Public URL
bold "6. Public URL (optional)"
info "Serves the UI at https://<name> with a Let's Encrypt certificate (through Bunny DNS,"
info "no inbound access needed) and opens SSH and HTTPS only to the addresses you list."
DOMAIN="" ALLOW="" BUNNY=""
def_domain=${CUR_DOMAIN:-$REC_DOMAIN}
if yesno "Set up a public URL?" "$([ -n "$def_domain" ] && echo y || echo n)"; then
  ask DOMAIN "Hostname (its A record must point at this VM)" "$def_domain"
  DOMAIN=${DOMAIN,,}; DOMAIN=${DOMAIN#https://}; DOMAIN=${DOMAIN%%/*}
  [ -n "$DOMAIN" ] || die "a hostname is required"
  ssh_peers=$(ss -tnH state established '( sport = :22 )' | awk '{print $NF}' | sed 's/:[0-9]*$//; s/^\[//; s/\]$//; s/^::ffff://' | sort -u | paste -sd, -)
  ask ALLOW "Allowed source IPs/CIDRs, comma-separated (SSH and HTTPS)" "${CUR_ALLOW:-${REC_ALLOW:-$ssh_peers}}"
  [ -n "$ALLOW" ] || die "at least one allowed address is required"
  if [ -n "$REC_BUNNY" ]; then BUNNY=$REC_BUNNY; info "Bunny API key: from the recovery file"
  elif [ -n "$(kv /etc/vmexec/caddy.env BUNNY_API_KEY)" ]; then info "Bunny API key: already on this VM"
  else
    ask_secret BUNNY "Bunny API key (hidden; for the certificate's DNS records)"
    [ -n "$BUNNY" ] || die "the Bunny API key is required for the certificate"
  fi
else
  info "Skipped: the UI stays on https://<this VM>:8000."
fi
echo

# ------------------------------------------------------------------ summary
bold "Summary"
info "Backups:     s3://$BUCKET/$PREFIX  ($ENDPOINT, $REGION)"
case "$MODE" in
  reconfigure) info "Repository:  unchanged (this appliance already uses it)" ;;
  new) if [ "$HAVE_PASSWORD" = 1 ]; then info "Repository:  new, encrypted with this appliance's existing password"
       else info "Repository:  new; an encryption password is generated and saved with a recovery file in /root"; fi ;;
  connect) info "Repository:  CONNECT to the existing one ($OBJECTS objects): backups, jobs, policies,"
           info "             vCenter connection and users come back" ;;
  move) info "Repository:  move from s3://$CUR_URL to a new, empty one (same encryption password)" ;;
esac
if [ -n "$CACHE_DEV" ]; then info "Cache disk:  $CACHE_DEV ($CACHE_SIZE_GB GB) WILL BE FORMATTED, $CACHE_GB GB budget"
else info "Cache disk:  vmexec-data, $CACHE_GB GB budget"; fi
info "VDDK:        ${VDDK:-already in place}"
[ -n "$VC_ADDR" ] && info "vCenter:     $VC_ADDR as $VC_USER"
[ -n "$INSTANCE" ] && info "Name:        $INSTANCE"
[ -n "$DOMAIN" ] && info "Public URL:  https://$DOMAIN, SSH and HTTPS from $ALLOW only"
info "Install to:  $DIR ($REF)"
echo
yesno "Install now?" y || die "cancelled, nothing changed"
echo

# ------------------------------------------------------------------ run
args=(--bucket "$BUCKET" --prefix "$PREFIX" --s3-endpoint "$ENDPOINT" --s3-region "$REGION"
      --cache-gb "$CACHE_GB" --yes)
[ -n "$INSTANCE" ] && args+=(--instance-name "$INSTANCE")
[ -n "$CACHE_DEV" ] && args+=(--cache-dev "$CACHE_DEV")
[ -n "$VDDK" ] && args+=(--vddk "$VDDK")
[ "$MODE" = connect ] && args+=(--recover)
[ "$FORCE" = 1 ] && args+=(--force-recover)
[ "$MODE" = move ] && args+=(--change-location)
if [ "$USE_EXISTING_KEY" = 0 ]; then
  ( umask 077; printf 'AWS_ACCESS_KEY_ID=%s\nAWS_SECRET_ACCESS_KEY=%s\n' "$AK" "$SK" > "$secrets/s3.env" )
  args+=(--credentials-file "$secrets/s3.env")
  [ "$HAVE_KEY" = 1 ] && args+=(--rotate-s3-key)
fi
if [ -n "$PASSWORD" ]; then
  ( umask 077; printf '%s\n' "$PASSWORD" > "$secrets/password" )
  args+=(--password-file "$secrets/password")
fi
if [ -n "$DOMAIN" ]; then
  args+=(--public-domain "$DOMAIN" --allow-from "$ALLOW")
  if [ -n "$BUNNY" ]; then
    ( umask 077; printf 'BUNNY_API_KEY=%s\n' "$BUNNY" > "$secrets/bunny.env" )
    args+=(--bunny-key-file "$secrets/bunny.env")
  fi
fi
unset AK SK PASSWORD BUNNY
if [ -n "$VC_ADDR" ]; then ( umask 077; printf '%s\n%s\n' "$VC_USER" "$VC_PASS" > "$secrets/vcenter" ); fi
unset VC_PASS
"$DIR/deploy/install.sh" "${args[@]}"

if [ -n "$VC_ADDR" ]; then
  bold "Connecting vCenter"
  docker exec -i vmexec_worker python -m services.appliance_setup add-vcenter vcenter "$VC_ADDR" < "$secrets/vcenter" \
    || info "Could not connect vCenter (see above). Connect it under Settings → vCenter."
fi
echo
if [ -n "$DOMAIN" ]; then bold "Done. Open https://$DOMAIN"
else bold "Done. Open https://$(hostname -I | awk '{print $1}'):8000"; fi
if [ "$MODE" = connect ]; then
  info "Log in with the old appliance's admin account and MFA."
  info "Check that the VMs list their restore points, then try one restore."
else
  info "First login: admin / admin. You are asked to set up MFA, then change the password under Settings → Users."
  info "Then pick the VMs to protect: Backup → Protect VMs."
fi
