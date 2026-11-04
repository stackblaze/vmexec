#!/usr/bin/env bash
# Public URL for a VMExec appliance, called by deploy/install.sh --public-domain.
#
# The VM's address comes from the VM build (cloud-init/Terraform); this script
# only makes that address safe to expose and puts the UI behind a real certificate:
#   - ufw: 22 and 443 open only to ALLOW_FROM, everything else incoming denied
#   - Docker: new connections forwarded in from the public card are dropped
#     (published container ports bypass ufw)
#   - ARP answered only on the owning card (flat L2 segments with more than one card)
#   - VMware Tools reports the real card's address, not Docker's bridges
#   - Caddy on :443 with a Let's Encrypt certificate through Bunny DNS-01
#     (no inbound access needed), proxying to the UI on 127.0.0.1:8000
#
# Environment (from install.sh): APP_DIR DOMAIN ALLOW_FROM BUNNY_FILE PUBLIC_ENV CADDY_ENV
# Re-running changes nothing when nothing changed.
set -euo pipefail

: "${APP_DIR:?}" "${DOMAIN:?}" "${ALLOW_FROM:?}" "${BUNNY_FILE:?}" "${PUBLIC_ENV:?}" "${CADDY_ENV:?}"
PROXY_DIR=/opt/vmexec-proxy
RULE_TAG="vmexec allowlist"

ok() { printf '  ok   %s\n' "$*"; }
warn() { printf '  \033[33mwarning:\033[0m %s\n' "$*"; }
die() { printf 'public-access.sh: %s\n' "$*" >&2; exit 1; }

get_kv() { # file key (never sources)
  python3 - "$1" "$2" <<'PY'
import sys
for line in open(sys.argv[1]):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        if k.strip() == sys.argv[2]:
            print(v.strip().strip("'\""), end="")
            break
PY
}

# Normalised allowlist: one network per line (a.b.c.d or a.b.c.d/nn).
mapfile -t ALLOW < <(python3 -c '
import ipaddress, sys
for x in sys.argv[1].split(","):
    x = x.strip()
    if x:
        n = ipaddress.ip_network(x, strict=False)
        print(n.network_address if n.prefixlen == n.max_prefixlen else n)' "$ALLOW_FROM")
[ ${#ALLOW[@]} -gt 0 ] || die "ALLOW_FROM is empty"

# ---------------------------------------------------------------- the public card
read -r WAN_IF WAN_IP < <(ip -4 route get 1.1.1.1 | sed -n 's/.* dev \([^ ]*\).* src \([^ ]*\).*/\1 \2/p')
[ -n "${WAN_IF:-}" ] || die "no default route: cannot tell which card is public"
ok "public card $WAN_IF ($WAN_IP)"
if python3 -c 'import ipaddress,sys; sys.exit(0 if ipaddress.ip_address(sys.argv[1]).is_private else 1)' "$WAN_IP"; then
  warn "$WAN_IP is a private address: $DOMAIN must point at the public address that reaches it"
else
  resolved=$(getent ahostsv4 "$DOMAIN" | awk '{print $1; exit}' || true)
  if [ "$resolved" != "$WAN_IP" ]; then
    warn "$DOMAIN resolves to ${resolved:-nothing}, not $WAN_IP: create or fix its A record."
    warn "(Create it before anyone opens the name: resolvers cache \"not found\" for up to a day.)"
  else
    ok "$DOMAIN resolves to $WAN_IP"
  fi
fi

# ---------------------------------------------------------------- lock-out guard
# Never cut off the SSH session running this: it must come from the allowlist.
mapfile -t PEERS < <(ss -tnH state established '( sport = :22 )' | awk '{print $NF}' | sed 's/:[0-9]*$//; s/^\[//; s/\]$//; s/^::ffff://' | sort -u)
for peer in "${PEERS[@]}"; do
  [ -n "$peer" ] || continue
  if ! python3 -c '
import ipaddress, sys
ip = ipaddress.ip_address(sys.argv[1])
sys.exit(0 if ip.is_loopback or any(ip in ipaddress.ip_network(n, strict=False) for n in sys.argv[2:]) else 1)' "$peer" "${ALLOW[@]}"; then
    die "the SSH connection from $peer is not in --allow-from ($ALLOW_FROM): enabling the firewall would cut it off. Add $peer, or run this from the VM console."
  fi
done

# ---------------------------------------------------------------- ARP + VMware Tools
cat > /etc/sysctl.d/60-vmexec-arp.conf <<'EOF'
# VMExec: answer ARP only on the card that owns the address (flat L2 segments).
net.ipv4.conf.all.arp_ignore = 1
net.ipv4.conf.all.arp_announce = 2
EOF
sysctl -q -p /etc/sysctl.d/60-vmexec-arp.conf
ok "ARP answered on the owning card only"

if [ -d /etc/vmware-tools ] || dpkg -s open-vm-tools >/dev/null 2>&1; then
  tc=/etc/vmware-tools/tools.conf
  install -d /etc/vmware-tools; touch "$tc"
  before=$(sha256sum "$tc")
  python3 - "$tc" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
line = "exclude-nics=docker*,br-*,veth*"
if re.search(r"(?m)^\[guestinfo\]", s):
    if re.search(r"(?m)^exclude-nics\s*=", s):
        s = re.sub(r"(?m)^exclude-nics\s*=.*$", line, s)
    else:
        s = re.sub(r"(?m)^\[guestinfo\]\s*$", "[guestinfo]\n# Report only the real card to vCenter, not Docker bridges.\n" + line, s, count=1)
else:
    s = s.rstrip("\n") + ("\n" if s.strip() else "") + "[guestinfo]\n# Report only the real card to vCenter, not Docker bridges.\n" + line + "\n"
open(p, "w").write(s)
PY
  [ "$before" = "$(sha256sum "$tc")" ] || systemctl restart open-vm-tools 2>/dev/null || true
  ok "VMware Tools reports $WAN_IF only"
fi

# ---------------------------------------------------------------- firewall
dpkg -s ufw >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ufw >/dev/null
# Allow first, then enable, then remove stale entries: no window without access.
for net in "${ALLOW[@]}"; do
  for port in 22 443; do
    ufw allow proto tcp from "$net" to any port "$port" comment "$RULE_TAG" >/dev/null
  done
done

# Docker: published ports are forwarded past ufw. Drop new connections that come
# in on the public card; replies to the containers' own connections still pass.
after=/etc/ufw/after.rules
before_rules=$(sha256sum "$after")
python3 - "$after" "$WAN_IF" <<'PY'
import re, sys
p, wan = sys.argv[1], sys.argv[2]
s = open(p).read()
# drop any earlier DOCKER-USER section (ours, or a hand-written one)
s = re.sub(r"(?ms)^# BEGIN vmexec\n.*?^# END vmexec\n", "", s)
s = re.sub(r"(?ms)^\*filter\n(?:(?!^COMMIT$).)*?^:DOCKER-USER .*?^COMMIT\n", "", s)
s = s.rstrip("\n") + "\n\n" + f"""# BEGIN vmexec
# Docker publishes ports past ufw: refuse new connections from outside on {wan}.
*filter
:DOCKER-USER - [0:0]
-A DOCKER-USER -i {wan} -m conntrack --ctstate NEW -j DROP
-A DOCKER-USER -j RETURN
COMMIT
# END vmexec
"""
open(p, "w").write(s)
PY
ufw default deny incoming >/dev/null
if ! ufw status | grep -q '^Status: active'; then ufw --force enable >/dev/null
elif [ "$before_rules" != "$(sha256sum "$after")" ]; then ufw reload >/dev/null; fi

# Stale allowlist entries: tagged rules whose source is no longer listed, or
# that are not the plain "port to any" form this script writes.
python3 - "$RULE_TAG" "${ALLOW[@]}" <<'PY' | sort -rn | while read -r n; do ufw --force delete "$n" >/dev/null; done
import re, subprocess, sys
tag, allow = sys.argv[1], set(sys.argv[2:])
out = subprocess.run(["ufw", "status", "numbered"], capture_output=True, text=True).stdout
for line in out.splitlines():
    m = re.match(r"\[\s*(\d+)\]\s+(.+?)\s+ALLOW IN\s+(\S+)(?: \(v6\))?\s+#\s*(.*)$", line)
    if not m or not m.group(4).startswith(tag):
        continue
    num, to, src = m.group(1), m.group(2), m.group(3)
    if src not in allow or to not in ("22/tcp", "443/tcp"):
        print(num)
PY
ok "firewall: 22 and 443 from ${ALLOW[*]} only; Docker ports closed on $WAN_IF"

# ---------------------------------------------------------------- Caddy
install -d -m 0755 /etc/vmexec
if [ "$BUNNY_FILE" != "$CADDY_ENV" ]; then
  key=$(get_kv "$BUNNY_FILE" BUNNY_API_KEY)
  [ -n "$key" ] || die "$BUNNY_FILE has no BUNNY_API_KEY"
  ( umask 077; printf 'BUNNY_API_KEY=%s\n' "$key" > "$CADDY_ENV.tmp" )
  unset key
  if cmp -s "$CADDY_ENV.tmp" "$CADDY_ENV"; then rm -f "$CADDY_ENV.tmp"; else mv "$CADDY_ENV.tmp" "$CADDY_ENV"; CADDY_RESTART=1; fi
fi
chmod 0600 "$CADDY_ENV"

install -d "$PROXY_DIR/caddy"
changed=${CADDY_RESTART:-0}
put() { # src dest
  if ! cmp -s "$1" "$2"; then install -m 0644 "$1" "$2"; changed=1; fi
}
put "$APP_DIR/deploy/proxy/caddy/Dockerfile" "$PROXY_DIR/caddy/Dockerfile"
put "$APP_DIR/deploy/proxy/compose.yaml" "$PROXY_DIR/compose.yaml"
sed "s/@DOMAIN@/$DOMAIN/" "$APP_DIR/deploy/proxy/Caddyfile.tmpl" > "$PROXY_DIR/Caddyfile.new"
put "$PROXY_DIR/Caddyfile.new" "$PROXY_DIR/Caddyfile"; rm -f "$PROXY_DIR/Caddyfile.new"
(cd "$PROXY_DIR" && docker compose up -d >/dev/null 2>&1) || (cd "$PROXY_DIR" && docker compose up -d)
[ "$changed" = 0 ] || (cd "$PROXY_DIR" && docker compose up -d --force-recreate >/dev/null)

umask 022
cat > "$PUBLIC_ENV.tmp" <<EOF
# Public URL settings (deploy/public-access.sh). Not secret.
VMEXEC_PUBLIC_DOMAIN=$DOMAIN
VMEXEC_ALLOW_FROM=$(IFS=,; echo "${ALLOW[*]}")
VMEXEC_WAN_IF=$WAN_IF
EOF
mv "$PUBLIC_ENV.tmp" "$PUBLIC_ENV"

# The certificate: Caddy gets it on its own; wait a little so the result is visible.
for _ in $(seq 1 60); do
  curl -s -o /dev/null --max-time 5 --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/" && break
  sleep 3
done
if curl -s -o /dev/null --max-time 5 --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/"; then
  ok "https://$DOMAIN serves a valid certificate"
else
  warn "no valid certificate for $DOMAIN yet: docker logs vmexec-proxy-caddy-1 (Caddy keeps retrying)"
fi
