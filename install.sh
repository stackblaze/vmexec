#!/usr/bin/env bash
# VMExec one-line installer. On a fresh Ubuntu 22.04/24.04 VM:
#
#   curl -fsSL https://raw.githubusercontent.com/stackblaze/vmexec/main/install.sh | sudo bash
#
# It asks a few questions (S3 bucket and key, cache disk, VDDK), checks the
# answers, shows a summary, and then installs: it clones VMExec to /opt/vmexec
# and runs deploy/install.sh, which sets up ZeroFS, the backup mount and the
# containers. Re-running it is safe.
#
# Without questions (automation): pass deploy/install.sh options after --:
#   curl -fsSL .../install.sh | sudo bash -s -- --bucket B --s3-endpoint URL --s3-region R ...
#
# Environment: VMEXEC_REF (branch or tag, default main), VMEXEC_DIR (default /opt/vmexec),
#              VMEXEC_REPO (default https://github.com/stackblaze/vmexec.git).
set -euo pipefail

REPO=${VMEXEC_REPO:-https://github.com/stackblaze/vmexec.git}
REF=${VMEXEC_REF:-main}
DIR=${VMEXEC_DIR:-/opt/vmexec}

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
CUR_NAME=$(sed -n 's/^VMEXEC_INSTANCE_NAME=//p' "$DIR/.env" 2>/dev/null || true)
HAVE_KEY=0; [ -f /etc/zerofs/zerofs.env ] && grep -q '^AWS_ACCESS_KEY_ID=.' /etc/zerofs/zerofs.env && HAVE_KEY=1
[ -n "$CUR_URL" ] && { info "Existing install found: backups at s3://$CUR_URL"; echo; }

# 1. S3
bold "1. S3 storage"
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

AK="" SK=""
if [ "$HAVE_KEY" = 1 ] && ! yesno "Replace the S3 key this appliance already has?" n; then
  USE_EXISTING_KEY=1
else
  USE_EXISTING_KEY=0
  ask AK "S3 access key ID" ""
  ask_secret SK "S3 secret access key (hidden)"
  [ -n "$AK" ] && [ -n "$SK" ] || die "an S3 key is required"
fi

# Check the key against the bucket now, not halfway through the install.
probe=$(mktemp)
if [ "$USE_EXISTING_KEY" = 1 ]; then
  akx=$(python3 -c 'import sys;[print(l.split("=",1)[1].strip(),end="") for l in open(sys.argv[1]) if l.startswith("AWS_ACCESS_KEY_ID=")]' /etc/zerofs/zerofs.env)
  skx=$(python3 -c 'import sys;[print(l.split("=",1)[1].strip(),end="") for l in open(sys.argv[1]) if l.startswith("AWS_SECRET_ACCESS_KEY=")]' /etc/zerofs/zerofs.env)
else
  akx=$AK skx=$SK
fi
if ! AWS_ACCESS_KEY_ID=$akx AWS_SECRET_ACCESS_KEY=$skx python3 "$DIR/deploy/s3-usage.py" "$ENDPOINT" "$REGION" "$BUCKET" "$PREFIX" "$probe" >/dev/null 2>&1; then
  rm -f "$probe"; die "cannot list s3://$BUCKET/$PREFIX/ with that key. Check the endpoint, region, bucket and key."
fi
unset akx skx
OBJECTS=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["objects"])' "$probe"); rm -f "$probe"
info "Key works. s3://$BUCKET/$PREFIX/ holds $OBJECTS objects."

MODE=new
SAME_AS_NOW=0; [ "$CUR_URL" = "$BUCKET/$PREFIX" ] && SAME_AS_NOW=1
if [ "$OBJECTS" != 0 ] && [ "$SAME_AS_NOW" != 1 ]; then
  info "That folder already has a VMExec repository."
  if yesno "Recover it (attach its backups to this VM; needs its encryption password)?" y; then
    MODE=recover
  else
    die "pick an empty folder, or recover the existing one"
  fi
elif [ -n "$CUR_URL" ] && [ "$SAME_AS_NOW" != 1 ]; then
  info "This appliance stores backups at s3://$CUR_URL today. The new folder starts empty;"
  info "the old one stays in S3 until you delete it."
  yesno "Move this appliance to s3://$BUCKET/$PREFIX?" n || die "nothing changed"
  MODE=move
fi
PASSWORD=""
if [ "$MODE" = recover ] && ! grep -q '^ZEROFS_PASSWORD=.' /etc/zerofs/zerofs.env 2>/dev/null; then
  ask_secret PASSWORD "Encryption password of that repository (hidden)"
  [ -n "$PASSWORD" ] || die "the password is required to recover"
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

# 4. vCenter
bold "4. vCenter"
VC_ADDR="" VC_USER="" VC_PASS=""
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

# 5. Name
bold "5. Name"
ask INSTANCE "Appliance name (shown in alerts)" "${CUR_NAME:-$(hostname -s)}"
echo

# ------------------------------------------------------------------ summary
bold "Summary"
info "Backups:     s3://$BUCKET/$PREFIX  ($ENDPOINT, $REGION)"
case "$MODE" in
  new) info "Repository:  new (an encryption password is generated and saved for you)";;
  recover) info "Repository:  recover the existing one ($OBJECTS objects)";;
  move) info "Repository:  move from s3://$CUR_URL to a new, empty one";;
esac
[ "$SAME_AS_NOW" = 1 ] && info "Repository:  unchanged (this appliance already uses it)"
if [ -n "$CACHE_DEV" ]; then info "Cache disk:  $CACHE_DEV ($CACHE_SIZE_GB GB) WILL BE FORMATTED, $CACHE_GB GB budget"
else info "Cache disk:  vmexec-data, $CACHE_GB GB budget"; fi
info "VDDK:        ${VDDK:-already in place}"
[ -n "$VC_ADDR" ] && info "vCenter:     $VC_ADDR as $VC_USER"
info "Name:        $INSTANCE"
info "Install to:  $DIR ($REF)"
echo
yesno "Install now?" y || die "cancelled, nothing changed"
echo

# ------------------------------------------------------------------ run
args=(--bucket "$BUCKET" --prefix "$PREFIX" --s3-endpoint "$ENDPOINT" --s3-region "$REGION"
      --instance-name "$INSTANCE" --cache-gb "$CACHE_GB" --yes)
[ -n "$CACHE_DEV" ] && args+=(--cache-dev "$CACHE_DEV")
[ -n "$VDDK" ] && args+=(--vddk "$VDDK")
[ "$MODE" = recover ] && args+=(--recover)
[ "$MODE" = move ] && args+=(--change-location)
secrets=$(mktemp -d); chmod 700 "$secrets"; trap 'rm -rf "$secrets"' EXIT
if [ "$USE_EXISTING_KEY" = 0 ]; then
  ( umask 077; printf 'AWS_ACCESS_KEY_ID=%s\nAWS_SECRET_ACCESS_KEY=%s\n' "$AK" "$SK" > "$secrets/s3.env" )
  args+=(--credentials-file "$secrets/s3.env")
  [ "$HAVE_KEY" = 1 ] && args+=(--rotate-s3-key)
fi
if [ -n "$PASSWORD" ]; then
  ( umask 077; printf '%s\n' "$PASSWORD" > "$secrets/password" )
  args+=(--password-file "$secrets/password")
fi
unset AK SK PASSWORD
if [ -n "$VC_ADDR" ]; then ( umask 077; printf '%s\n%s\n' "$VC_USER" "$VC_PASS" > "$secrets/vcenter" ); fi
unset VC_PASS
"$DIR/deploy/install.sh" "${args[@]}"

if [ -n "$VC_ADDR" ]; then
  bold "Connecting vCenter"
  docker exec -i vmexec_worker python -m services.appliance_setup add-vcenter vcenter "$VC_ADDR" < "$secrets/vcenter" \
    || info "Could not connect vCenter (see above). Connect it under Settings → vCenter."
fi
echo
bold "Done. Open https://$(hostname -I | awk '{print $1}'):8000"
info "First login: admin / admin. You are asked to set up MFA, then change the password under Settings → Users."
info "Then pick the VMs to protect: Backup → Protect VMs."
