"""Kubernetes state backup — Phase 1: etcd/datastore snapshots.

Instead of imaging K8s node VMs (whose disks churn constantly and whose
state lives in etcd and PVs), VMExec snapshots the cluster state itself:
for each configured target it execs `etcdctl snapshot save` inside the
etcd pod, verifies the snapshot, streams it out through the Kubernetes
API (no agent, no in-cluster storage credentials), and stores it as a
chain point under k8s/<cluster>/<target>/ with the same retention and
secondary-copy machinery as VM backups.

Restore is the documented Kamaji/kubeadm path: rebuild nodes from
templates, restore the snapshot into a fresh datastore, let the
controllers reconcile. See docs: kamaji.clastix.io/guides/backup-and-restore.
"""

import base64
import datetime
import hashlib
import json
import shlex

import backup_manifest as bm
from logger_util import log_info, log_warn, log_error

SNAP_PATH = "/tmp/vmexec_etcd_snapshot.db"

# Target profiles: defaults for well-known etcd deployments. Any field can
# be overridden per target. "custom" requires explicit fields.
PROFILES = {
    "kubeadm": {
        "namespace": "kube-system",
        "selector": "component=etcd",
        "container": "etcd",
        "endpoint": "https://127.0.0.1:2379",
        "cacert": "/etc/kubernetes/pki/etcd/ca.crt",
        "cert": "/etc/kubernetes/pki/etcd/server.crt",
        "key": "/etc/kubernetes/pki/etcd/server.key",
    },
    # kamaji-etcd StatefulSet (multi-tenant datastore). The etcd image is
    # distroless (no shell), so the snapshot runs in a short-lived helper pod
    # that reaches etcd over its client Service with the client-certs secret —
    # the same shape as kamaji-etcd's own backup Job.
    "kamaji": {
        "mode": "pod",
        "namespace": "kamaji-system",
        "endpoint": "https://kamaji-etcd-client.kamaji-system.svc.cluster.local:2379",
        "certs_secret": "kamaji-etcd-client-certs",
        "cacert": "/etcd-certs/ca.crt",
        "cert": "/etcd-certs/tls.crt",
        "key": "/etcd-certs/tls.key",
        # Snapshot container: same etcd image the cluster already runs
        # (node-cached, no shell). Transfer container: busybox for base64.
        "helper_image": "quay.io/coreos/etcd:v3.6.12",
        "xfer_image": "busybox:stable",
    },
    # k3s embedded etcd (management cluster): no etcd pod exists, so the
    # helper pod runs with hostNetwork on an etcd node and mounts the node's
    # etcd certs read-only via hostPath. Privileged-ish for ~10s per snapshot;
    # requires no node configuration or k3s restarts.
    "k3s": {
        "mode": "pod",
        "namespace": "kube-system",
        "endpoint": "https://127.0.0.1:2379",
        "host_certs_dir": "/var/lib/rancher/k3s/server/tls/etcd",
        "cacert": "/etcd-certs/server-ca.crt",
        "cert": "/etcd-certs/server-client.crt",
        "key": "/etcd-certs/server-client.key",
        "helper_image": "quay.io/coreos/etcd:v3.6.12",
        "xfer_image": "busybox:stable",
        "node_selector": {"node-role.kubernetes.io/etcd": "true"},
        "host_network": True,
    },
    # Per-tenant resource export: auto-discovers Kamaji TenantControlPlanes,
    # connects to EACH tenant's own API server (admin kubeconfig read from its
    # Secret at runtime, never stored), and exports all API objects as a
    # per-tenant restore point. The etcd snapshot restores the whole datastore
    # (disaster); these restore one named tenant (support desk).
    "tenants": {
        "mode": "tenants",
    },
    "custom": {},
}

# Resources excluded from tenant exports: high-churn or server-derived.
EXPORT_SKIP = {
    "events", "events.k8s.io/events", "coordination.k8s.io/leases",
    "componentstatuses", "discovery.k8s.io/endpointslices", "endpoints",
    "flowcontrol.apiserver.k8s.io/flowschemas",
    "flowcontrol.apiserver.k8s.io/prioritylevelconfigurations",
    "metrics.k8s.io/nodes", "metrics.k8s.io/pods",
}


def resolve_target(target):
    """Merge a target dict over its profile defaults. Raises on gaps."""
    profile = PROFILES.get(target.get("profile", "custom"), {})
    merged = {**profile, **{k: v for k, v in target.items() if v}}
    merged.setdefault("mode", "exec")
    if merged["mode"] == "tenants":
        required = ["name"]
    elif merged["mode"] == "pod":
        required = ["name", "namespace", "endpoint",
                    "cacert", "cert", "key", "helper_image", "xfer_image"]
        if not merged.get("host_certs_dir"):
            required.append("certs_secret")
    else:
        required = ("name", "namespace", "selector", "container",
                    "endpoint", "cacert", "cert", "key")
    missing = [f for f in required if not merged.get(f)]
    if missing:
        raise ValueError(f"target {target.get('name', '?')}: missing fields {missing}")
    return merged


def chain_name(cluster_name, target_name):
    return f"k8s/{cluster_name}/{target_name}"


def _clients(kubeconfig_yaml):
    import yaml
    from kubernetes import client, config
    cfg = yaml.safe_load(kubeconfig_yaml)
    api_client = config.new_client_from_config_dict(cfg)
    return client.CoreV1Api(api_client)


def _find_pod(core, namespace, selector):
    # Explicit timeout: an unreachable API server must fail in seconds, not hang.
    pods = core.list_namespaced_pod(
        namespace, label_selector=selector, _request_timeout=15).items
    running = [p for p in pods if p.status.phase == "Running"]
    if not running:
        raise RuntimeError(f"no Running pod matches '{selector}' in {namespace}")
    return sorted(running, key=lambda p: p.metadata.name)[0].metadata.name


def _exec(core, namespace, pod, container, command, timeout=600, shell=True):
    """Exec in a pod. command is a shell string (shell=True) or an argv list
    (shell=False, for shell-less images)."""
    from kubernetes.stream import stream
    argv = ["/bin/sh", "-c", command] if shell else list(command)
    resp = stream(
        core.connect_get_namespaced_pod_exec, pod, namespace,
        container=container, command=argv,
        stderr=True, stdin=False, stdout=True, tty=False,
        _preload_content=False, _request_timeout=timeout,
    )
    out, err = [], []
    while resp.is_open():
        resp.update(timeout=5)
        if resp.peek_stdout():
            out.append(resp.read_stdout())
        if resp.peek_stderr():
            err.append(resp.read_stderr())
    resp.close()
    try:
        rc = resp.returncode
    except ValueError as e:
        # ws_client raises trying to int() a textual failure reason (e.g.
        # "OCI runtime exec failed"). Surface that reason instead of crashing.
        raise RuntimeError(f"exec failed: {str(e)[-400:]}")
    if rc not in (0, None):
        raise RuntimeError(f"exec failed (rc={rc}): {''.join(err)[-400:]}")
    return "".join(out), "".join(err)


def _snapshot_via_helper_pod(core, t):
    """Distroless etcd (kamaji-etcd): spawn a two-container pod — the cluster's
    own etcd image runs `etcdctl snapshot save` over the client Service into a
    shared emptyDir and exits; a busybox sidecar streams the file back via
    exec. Same shape as kamaji-etcd's backup Job. Returns (data, status, src).
    """
    import time as _time
    from kubernetes import client as kc
    pod_name = f"vmexec-etcd-snap-{int(_time.time())}"
    ns = t["namespace"]
    snap_cmd = ["etcdctl", f"--endpoints={t['endpoint']}",
                f"--cacert={t['cacert']}", f"--cert={t['cert']}",
                f"--key={t['key']}", "--dial-timeout=15s",
                "--command-timeout=10m", "snapshot", "save", "/backup/snapshot.db"]
    if t.get("host_certs_dir"):
        certs_volume = kc.V1Volume(name="certs", host_path=kc.V1HostPathVolumeSource(
            path=t["host_certs_dir"], type="Directory"))
    else:
        certs_volume = kc.V1Volume(name="certs", secret=kc.V1SecretVolumeSource(
            secret_name=t["certs_secret"]))
    pod = kc.V1Pod(
        metadata=kc.V1ObjectMeta(name=pod_name, labels={"app": "vmexec-etcd-snapshot"}),
        spec=kc.V1PodSpec(
            restart_policy="Never",
            host_network=bool(t.get("host_network")),
            node_selector=t.get("node_selector") or None,
            containers=[
                kc.V1Container(
                    name="snap", image=t["helper_image"], command=snap_cmd,
                    volume_mounts=[
                        kc.V1VolumeMount(name="certs", mount_path="/etcd-certs", read_only=True),
                        kc.V1VolumeMount(name="backup", mount_path="/backup"),
                    ],
                ),
                kc.V1Container(
                    name="xfer", image=t["xfer_image"], command=["sleep", "900"],
                    volume_mounts=[kc.V1VolumeMount(name="backup", mount_path="/backup")],
                ),
            ],
            volumes=[
                certs_volume,
                kc.V1Volume(name="backup", empty_dir=kc.V1EmptyDirVolumeSource()),
            ],
        ),
    )
    core.create_namespaced_pod(ns, pod, _request_timeout=15)
    try:
        # Wait until the snap container has terminated (success or failure)
        # and the xfer sidecar is up.
        deadline = _time.time() + 300
        snap_state = None
        while _time.time() < deadline:
            p = core.read_namespaced_pod(pod_name, ns, _request_timeout=15)
            statuses = {c.name: c for c in (p.status.container_statuses or [])}
            snap = statuses.get("snap")
            xfer = statuses.get("xfer")
            if snap and snap.state and snap.state.waiting and \
                    (snap.state.waiting.reason or "") in ("ErrImagePull", "ImagePullBackOff"):
                raise RuntimeError(f"image pull failed: {snap.state.waiting.message or snap.state.waiting.reason}")
            if xfer and xfer.state and xfer.state.waiting and \
                    (xfer.state.waiting.reason or "") in ("ErrImagePull", "ImagePullBackOff"):
                raise RuntimeError(f"xfer image pull failed: {xfer.state.waiting.reason}")
            if snap and snap.state and snap.state.terminated:
                snap_state = snap.state.terminated
                if xfer and xfer.state and xfer.state.running:
                    break
            _time.sleep(3)
        else:
            raise RuntimeError("snapshot container did not finish within 300s")
        if snap_state.exit_code != 0:
            logs = ""
            try:
                logs = core.read_namespaced_pod_log(
                    pod_name, ns, container="snap", tail_lines=10, _request_timeout=15)
            except Exception:
                pass
            raise RuntimeError(f"etcdctl snapshot failed (rc={snap_state.exit_code}): {logs[-300:]}")

        b64, _ = _exec(core, ns, pod_name, "xfer",
                       ["base64", "/backup/snapshot.db"], shell=False)
        data = base64.b64decode(b64)
        status = {"note": "verified by size+sha256; etcd revision not read (shell-less etcd image)"}
        return data, status, pod_name
    finally:
        try:
            core.delete_namespaced_pod(pod_name, ns, _request_timeout=15,
                                       grace_period_seconds=0)
        except Exception:
            pass


def snapshot_target(core, cluster_name, target, storage, retention_count):
    """Take, verify, fetch and store one etcd snapshot. Returns point id."""
    t = resolve_target(target)
    if t.get("mode") == "pod":
        log_info(f"[K8S] {cluster_name}/{t['name']}: snapshotting via helper pod "
                 f"({t['helper_image']} → {t['endpoint']})")
        data, status, source = _snapshot_via_helper_pod(core, t)
        return _store_snapshot(cluster_name, t, storage, retention_count,
                               data, status, source)
    pod = _find_pod(core, t["namespace"], t["selector"])
    log_info(f"[K8S] {cluster_name}/{t['name']}: snapshotting via pod {pod}")

    etcdctl = (
        f"ETCDCTL_API=3 etcdctl --endpoints={shlex.quote(t['endpoint'])} "
        f"--cacert={shlex.quote(t['cacert'])} --cert={shlex.quote(t['cert'])} "
        f"--key={shlex.quote(t['key'])}"
    )
    _exec(core, t["namespace"], pod, t["container"],
          f"{etcdctl} snapshot save {SNAP_PATH}")
    status_out, _ = _exec(core, t["namespace"], pod, t["container"],
                          f"{etcdctl} snapshot status {SNAP_PATH} -w json")
    try:
        status = json.loads(status_out.strip().splitlines()[-1])
    except Exception:
        status = {"raw": status_out.strip()[-300:]}

    # Stream the file out through the API server. base64 keeps the exec
    # channel text-safe; snapshots are typically tens of MB.
    b64, _ = _exec(core, t["namespace"], pod, t["container"], f"base64 {SNAP_PATH}")
    data = base64.b64decode(b64)
    _exec(core, t["namespace"], pod, t["container"], f"rm -f {SNAP_PATH}")
    return _store_snapshot(cluster_name, t, storage, retention_count, data, status, pod)


def _store_snapshot(cluster_name, t, storage, retention_count, data, status, pod):
    if not data:
        raise RuntimeError("snapshot transfer produced 0 bytes")
    sha256 = hashlib.sha256(data).hexdigest()

    name = chain_name(cluster_name, t["name"])
    chain = bm.load_chain(storage, name) or bm.create_empty_chain(name)
    point_id = bm.new_point_id()
    point_dir = bm.point_rel(name, point_id)
    storage.makedirs(point_dir)
    with storage.open_write(f"{point_dir}/snapshot.db") as f:
        f.write(data)
    manifest = {
        "version": 1,
        "type": "etcd_snapshot",
        "point_id": point_id,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "size_bytes": len(data),
        "sha256": sha256,
        "etcd_status": status,
        "source_pod": pod,
        "target": {k: t[k] for k in ("name", "namespace", "endpoint")},
    }
    bm.save_manifest(storage, name, point_id, manifest)
    chain = bm.add_point_to_chain(chain, {
        "id": point_id, "type": "full", "parent": None,
        "timestamp": manifest["timestamp"],
    })
    bm.save_chain(storage, name, chain)
    prune_chain(storage, name, retention_count)
    log_info(f"[K8S] {cluster_name}/{t['name']}: snapshot {point_id} "
             f"({len(data) // 1024} KiB, sha256 {sha256[:12]}…)")
    return point_id


def prune_chain(storage, name, retention_count):
    """Drop oldest points beyond retention. Every point is a standalone full."""
    chain = bm.load_chain(storage, name)
    if not chain:
        return
    points = chain.get("points", [])
    keep = max(int(retention_count or 1), 1)
    excess = points[:-keep] if len(points) > keep else []
    for point in excess:
        storage.delete_dir(bm.point_rel(name, point["id"]))
    if excess:
        chain["points"] = points[-keep:]
        chain["latest"] = chain["points"][-1]["id"] if chain["points"] else None
        bm.save_chain(storage, name, chain)
        log_info(f"[K8S] {name}: pruned {len(excess)} point(s), keep {keep}")


def run_cluster_backup(db, cluster, storage):
    """Snapshot every target of a cluster. Returns (ok, message)."""
    targets = json.loads(cluster.targets or "[]")
    if not targets:
        return False, "no snapshot targets configured"
    core = _clients(cluster.kubeconfig)
    done, errors = [], []
    for target in targets:
        try:
            t = resolve_target(target)
            if t["mode"] == "tenants":
                done.extend(snapshot_tenants(core, cluster.name, storage,
                                             cluster.retention_count))
                continue
            point = snapshot_target(core, cluster.name, target, storage,
                                    cluster.retention_count)
            done.append(f"{target.get('name')}:{point}")
        except Exception as e:
            log_error(f"[K8S] {cluster.name}/{target.get('name')}: {e}")
            errors.append(f"{target.get('name')}: {str(e)[:160]}")
    if errors and not done:
        return False, "; ".join(errors)
    msg = f"{len(done)} snapshot(s) stored"
    if errors:
        msg += f"; {len(errors)} failed: " + "; ".join(errors)
    return not errors, msg


def test_cluster(cluster):
    """Connectivity check: reach the API and locate every target's pod."""
    core = _clients(cluster.kubeconfig)
    results = []
    for target in json.loads(cluster.targets or "[]"):
        try:
            t = resolve_target(target)
            if t.get("mode") == "tenants":
                tenants = discover_tenants(core)
                results.append({"target": t["name"], "ok": bool(tenants),
                                "pod": f"{len(tenants)} tenant(s): " +
                                       ", ".join(x["name"] for x in tenants)})
                continue
            if t.get("mode") == "pod":
                if t.get("host_certs_dir"):
                    sel = ",".join(f"{k}={v}" for k, v in (t.get("node_selector") or {}).items())
                    nodes = core.list_node(label_selector=sel or None,
                                           _request_timeout=15).items
                    if not nodes:
                        raise RuntimeError(f"no node matches selector '{sel}'")
                    results.append({"target": t["name"], "ok": True,
                                    "pod": f"host-etcd mode → {len(nodes)} node(s)"})
                    continue
                core.read_namespaced_secret(t["certs_secret"], t["namespace"],
                                            _request_timeout=15)
                results.append({"target": t["name"], "ok": True,
                                "pod": f"helper-pod mode → {t['endpoint']}"})
                continue
            pod = _find_pod(core, t["namespace"], t["selector"])
            results.append({"target": t["name"], "ok": True, "pod": pod})
        except Exception as e:
            results.append({"target": target.get("name", "?"), "ok": False,
                            "error": str(e)[:200]})
    return results


# ---------------------------------------------------------------------------
#  k3s management-etcd S3 offload (configured from the UI)
# ---------------------------------------------------------------------------
K3S_S3_SECRET = "k3s-etcd-snapshot-s3"


def k3s_detect(core):
    """Nodes running k3s embedded etcd, with their last local snapshot time."""
    nodes = []
    for n in core.list_node(_request_timeout=15).items:
        ann = n.metadata.annotations or {}
        if "etcd.k3s.cattle.io/node-name" in ann:
            nodes.append({
                "name": n.metadata.name,
                "last_local_snapshot": ann.get(
                    "etcd.k3s.cattle.io/local-snapshots-timestamp"),
                "kubelet": n.status.node_info.kubelet_version,
            })
    return nodes


def k3s_apply_s3(core, cfg):
    """Create/update the S3 credentials Secret in kube-system and return the
    node config fragment the operator must still apply (host-level: file +
    rolling k3s restart — not reachable through the Kubernetes API)."""
    from kubernetes import client as kc
    data = {
        "etcd-s3-endpoint": cfg["endpoint"],
        "etcd-s3-access-key": cfg["access_key"],
        "etcd-s3-secret-key": cfg["secret_key"],
        "etcd-s3-bucket": cfg["bucket"],
        "etcd-s3-folder": cfg.get("folder") or "etcd",
        "etcd-s3-region": cfg.get("region") or "us-east-1",
    }
    secret = kc.V1Secret(
        metadata=kc.V1ObjectMeta(name=K3S_S3_SECRET, namespace="kube-system"),
        string_data=data)
    try:
        core.create_namespaced_secret("kube-system", secret, _request_timeout=15)
        action = "created"
    except Exception:
        core.replace_namespaced_secret(K3S_S3_SECRET, "kube-system", secret,
                                       _request_timeout=15)
        action = "updated"
    log_info(f"[K8S] k3s S3 snapshot secret {action} in kube-system")

    fragment = (
        "# /etc/rancher/k3s/config.yaml.d/etcd-s3.yaml — apply on EACH etcd node,\n"
        "# then `systemctl restart k3s` ONE NODE AT A TIME (verify quorum between).\n"
        "etcd-s3: true\n"
        f"etcd-s3-config-secret: {K3S_S3_SECRET}\n"
        f"etcd-snapshot-schedule-cron: \"{cfg.get('schedule_cron') or '0 */6 * * *'}\"\n"
        f"etcd-snapshot-retention: {int(cfg.get('local_retention') or 10)}\n"
        f"etcd-s3-retention: {int(cfg.get('s3_retention') or 28)}\n"
    )
    return {"secret": action, "config_fragment": fragment}


def k3s_status(core):
    """Detection + secret + actual bucket contents (end-to-end verification)."""
    result = {"nodes": k3s_detect(core), "secret_present": False,
              "bucket_objects": None, "bucket_error": None}
    if not result["nodes"]:
        return result
    try:
        from kubernetes.client.exceptions import ApiException
        try:
            sec = core.read_namespaced_secret(K3S_S3_SECRET, "kube-system",
                                              _request_timeout=15)
        except ApiException as e:
            if e.status == 404:
                return result  # not configured yet — no error, nothing to list
            raise
        result["secret_present"] = True
        import base64 as b64
        vals = {k: b64.b64decode(v).decode() for k, v in (sec.data or {}).items()}
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url="https://" + vals["etcd-s3-endpoint"].removeprefix("https://").removeprefix("http://"),
            aws_access_key_id=vals["etcd-s3-access-key"],
            aws_secret_access_key=vals["etcd-s3-secret-key"],
            region_name=vals.get("etcd-s3-region") or "us-east-1",
        )
        resp = s3.list_objects_v2(Bucket=vals["etcd-s3-bucket"],
                                  Prefix=vals.get("etcd-s3-folder") or "",
                                  MaxKeys=10)
        objs = sorted(resp.get("Contents", []), key=lambda o: o["LastModified"],
                      reverse=True)
        result["bucket_objects"] = [
            {"key": o["Key"], "size": o["Size"],
             "modified": o["LastModified"].isoformat()} for o in objs[:5]]
    except Exception as e:
        result["bucket_error"] = str(e)[:200]
    return result


# ---------------------------------------------------------------------------
#  Per-tenant resource export (Kamaji TenantControlPlane auto-discovery)
# ---------------------------------------------------------------------------

def discover_tenants(core):
    """TenantControlPlanes on the management cluster with kubeconfig refs."""
    from kubernetes import client as kc
    co = kc.CustomObjectsApi(core.api_client)
    out = []
    tcps = co.list_cluster_custom_object(
        "kamaji.clastix.io", "v1alpha1", "tenantcontrolplanes",
        _request_timeout=15)
    for t in tcps.get("items", []):
        meta = t["metadata"]
        secret = (t.get("status", {}).get("kubeconfig", {})
                  .get("admin", {}).get("secretName"))
        out.append({"name": meta["name"], "namespace": meta["namespace"],
                    "kubeconfig_secret": secret})
    return out


def _reachable(host, port, timeout=4):
    import socket
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, int(port)))
        return True
    except Exception:
        return False
    finally:
        s.close()


def _tenant_core(mgmt_core, tenant):
    """Build an API client for a tenant from its admin kubeconfig Secret.

    The kubeconfig is used in memory only — never persisted. Tenant control
    planes are often published at an edge address the appliance cannot reach;
    when the kubeconfig endpoint is unreachable, fall back to the tenant
    Service's LAN LoadBalancer address (same client-cert auth)."""
    import base64 as b64
    import yaml
    from urllib.parse import urlparse
    from kubernetes import client, config as kconfig

    sec = mgmt_core.read_namespaced_secret(
        tenant["kubeconfig_secret"], tenant["namespace"], _request_timeout=15)
    raw = None
    for key, val in (sec.data or {}).items():
        if "conf" in key or "kubeconfig" in key:
            raw = b64.b64decode(val).decode()
            break
    if raw is None:
        raise RuntimeError(
            f"no kubeconfig key in secret {tenant['namespace']}/{tenant['kubeconfig_secret']}")

    cfg = yaml.safe_load(raw)
    server = cfg["clusters"][0]["cluster"]["server"]
    u = urlparse(server)
    if not _reachable(u.hostname, u.port or 443):
        svc = mgmt_core.read_namespaced_service(
            tenant["name"], tenant["namespace"], _request_timeout=15)
        lb = None
        if svc.status.load_balancer and svc.status.load_balancer.ingress:
            lb = svc.status.load_balancer.ingress[0].ip
        port = svc.spec.ports[0].port if svc.spec.ports else 6443
        sni_host = None
        if lb and _reachable(lb, port):
            log_info(f"[K8S] tenant {tenant['name']}: endpoint {server} "
                     f"unreachable; using LAN LoadBalancer https://{lb}:{port}")
            cfg["clusters"][0]["cluster"]["server"] = f"https://{lb}:{port}"
        else:
            # Fallback 2: a shared ingress LoadBalancer routing by TLS SNI —
            # connect to its LAN VIP while keeping SNI/verification on the
            # tenant's original hostname.
            vip = _find_ingress_vip(mgmt_core)
            if not vip:
                raise RuntimeError(
                    f"API endpoint {server} unreachable, no tenant LoadBalancer "
                    "and no reachable ingress VIP — expose the TenantControlPlane "
                    "or the ingress on the LAN to enable exports")
            log_info(f"[K8S] tenant {tenant['name']}: endpoint {server} "
                     f"unreachable; routing via ingress VIP https://{vip}:443 "
                     f"with SNI {u.hostname}")
            cfg["clusters"][0]["cluster"]["server"] = f"https://{vip}:443"
            cfg["clusters"][0]["cluster"]["tls-server-name"] = u.hostname
            sni_host = u.hostname
    api_client = kconfig.new_client_from_config_dict(cfg)
    if sni_host and not getattr(api_client.configuration, "tls_server_name", None):
        # older loaders ignore tls-server-name in the dict — set it directly
        api_client.configuration.tls_server_name = sni_host
    return client.CoreV1Api(api_client)


def _find_ingress_vip(mgmt_core):
    """First reachable LAN LoadBalancer VIP serving port 443 (SNI router)."""
    for svc in mgmt_core.list_service_for_all_namespaces(_request_timeout=15).items:
        if svc.spec.type != "LoadBalancer" or not svc.status.load_balancer:
            continue
        ing = svc.status.load_balancer.ingress or []
        if not ing or not ing[0].ip:
            continue
        if any(p.port == 443 for p in (svc.spec.ports or [])):
            if _reachable(ing[0].ip, 443):
                return ing[0].ip
    return None


def export_tenant_resources(tenant_core):
    """Dump every listable API object from a tenant cluster.
    Returns (payload_dict, counts_dict)."""
    api = tenant_core.api_client

    def get(path, query=None):
        # kubernetes>=30 renamed response_type → response_types_map
        data = api.call_api(
            path, "GET", query_params=list((query or {}).items()),
            auth_settings=["BearerToken"],
            response_types_map={200: "object"},
            _return_http_data_only=True, _request_timeout=30)
        return data

    # Discover list-able collections (core + preferred group versions)
    collections = []
    for r in get("/api/v1").get("resources", []):
        if "/" not in r["name"] and "list" in r.get("verbs", []):
            if r["name"] not in EXPORT_SKIP:
                collections.append(("/api/v1/" + r["name"], r["name"]))
    for g in get("/apis").get("groups", []):
        gv = g["preferredVersion"]["groupVersion"]
        if gv.startswith("metrics.k8s.io"):
            continue
        try:
            resources = get(f"/apis/{gv}").get("resources", [])
        except Exception:
            continue
        for r in resources:
            if "/" in r["name"] or "list" not in r.get("verbs", []):
                continue
            full = f"{gv.split('/')[0]}/{r['name']}"
            if r["name"] in EXPORT_SKIP or full in EXPORT_SKIP:
                continue
            collections.append((f"/apis/{gv}/" + r["name"], full))

    payload, counts = {}, {}
    for path, label in collections:
        items, token = [], None
        try:
            while True:
                q = {"limit": 500}
                if token:
                    q["continue"] = token
                resp = get(path, q)
                for item in resp.get("items", []):
                    item.get("metadata", {}).pop("managedFields", None)
                    items.append(item)
                token = resp.get("metadata", {}).get("continue")
                if not token:
                    break
        except Exception as e:
            log_warn(f"[K8S] tenant export: skipping {label}: {str(e)[:120]}")
            continue
        if items:
            payload[label] = items
            counts[label] = len(items)
    return payload, counts


def snapshot_tenants(core, cluster_name, storage, retention_count):
    """Export every discovered tenant. Returns list of 'tenant:point' ids."""
    import gzip
    done = []
    tenants = discover_tenants(core)
    if not tenants:
        raise RuntimeError("no TenantControlPlanes found on this cluster")
    errors = []
    for tn in tenants:
        if not tn["kubeconfig_secret"]:
            log_warn(f"[K8S] tenant {tn['name']}: no admin kubeconfig secret; skipped")
            errors.append(f"{tn['name']}: no admin kubeconfig secret")
            continue
        try:
            tcore = _tenant_core(core, tn)
            payload, counts = export_tenant_resources(tcore)
        except Exception as e:
            log_warn(f"[K8S] tenant {tn['name']}: export failed: {str(e)[:160]}")
            errors.append(f"{tn['name']}: {str(e)[:160]}")
            continue
        raw = gzip.compress(json.dumps(payload).encode())
        sha256 = hashlib.sha256(raw).hexdigest()

        name = f"k8s/{cluster_name}/tenants/{tn['name']}"
        chain = bm.load_chain(storage, name) or bm.create_empty_chain(name)
        point_id = bm.new_point_id()
        point_dir = bm.point_rel(name, point_id)
        storage.makedirs(point_dir)
        with storage.open_write(f"{point_dir}/resources.json.gz") as f:
            f.write(raw)
        manifest = {
            "version": 1, "type": "resource_export", "point_id": point_id,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "tenant": tn["name"], "size_bytes": len(raw), "sha256": sha256,
            "object_counts": counts, "total_objects": sum(counts.values()),
        }
        bm.save_manifest(storage, name, point_id, manifest)
        chain = bm.add_point_to_chain(chain, {
            "id": point_id, "type": "full", "parent": None,
            "timestamp": manifest["timestamp"]})
        bm.save_chain(storage, name, chain)
        prune_chain(storage, name, retention_count)
        log_info(f"[K8S] tenant {tn['name']}: {sum(counts.values())} objects "
                 f"exported ({len(raw)//1024} KiB)")
        done.append(f"{tn['name']}:{point_id}")
    if errors and not done:
        raise RuntimeError("; ".join(errors))
    if errors:
        log_warn(f"[K8S] tenant export partial: {'; '.join(errors)}")
    return done
