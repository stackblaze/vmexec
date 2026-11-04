#!/usr/bin/env python3
"""Bucket usage for the Settings > Storage tab, without S3 keys in the app.

Runs on the appliance host (vmexec-s3-usage.timer), with the key ZeroFS
already uses (EnvironmentFile=/etc/zerofs/zerofs.env), lists the backup
prefix and writes only totals to a file the web container reads:

  s3-usage.py <endpoint> <region> <bucket> <prefix> <out.json>

Output: {"bytes": N, "objects": N, "location": "bucket/prefix", "at": ISO,
         "newest": ISO or null (last write under the prefix)}.
Standard library only (SigV4 by hand). Credentials are never written out.
"""
import datetime
import hashlib
import hmac
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def _sign(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def list_page(endpoint, region, bucket, prefix, token, ak, sk):
    host = urllib.parse.urlparse(endpoint).netloc
    params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
    if token:
        params["continuation-token"] = token
    query = "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
                     for k, v in sorted(params.items()))
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload = hashlib.sha256(b"").hexdigest()
    path = "/" + urllib.parse.quote(bucket)
    canonical = "\n".join(["GET", path, query, f"host:{host}", f"x-amz-content-sha256:{payload}",
                           f"x-amz-date:{amz_date}", "", "host;x-amz-content-sha256;x-amz-date", payload])
    scope = f"{day}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = _sign(_sign(_sign(_sign(("AWS4" + sk).encode(), day), region), "s3"), "aws4_request")
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"{endpoint.rstrip('/')}{path}?{query}", headers={
        "x-amz-date": amz_date, "x-amz-content-sha256": payload,
        "Authorization": f"AWS4-HMAC-SHA256 Credential={ak}/{scope}, "
                         f"SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature={sig}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        root = ET.fromstring(r.read())
    ns = {"s": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
    find = (lambda e, t: e.findall(f"s:{t}", ns)) if ns else (lambda e, t: e.findall(t))
    items = find(root, "Contents")
    sizes = [int(c.findtext("s:Size" if ns else "Size", namespaces=ns) or 0) for c in items]
    stamps = [c.findtext("s:LastModified" if ns else "LastModified", namespaces=ns) or "" for c in items]
    truncated = (root.findtext("s:IsTruncated" if ns else "IsTruncated", namespaces=ns) or "false") == "true"
    nxt = root.findtext("s:NextContinuationToken" if ns else "NextContinuationToken", namespaces=ns)
    return sizes, stamps, (nxt if truncated else None)


def main():
    if len(sys.argv) != 6:
        raise SystemExit(__doc__)
    endpoint, region, bucket, prefix, out = sys.argv[1:]
    prefix = prefix.strip("/") + "/"
    ak, sk = os.environ["AWS_ACCESS_KEY_ID"], os.environ["AWS_SECRET_ACCESS_KEY"]
    total = count = 0
    newest = None
    token = None
    while True:
        sizes, stamps, token = list_page(endpoint, region, bucket, prefix, token, ak, sk)
        for t in stamps:
            if t:
                d = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
                newest = d if newest is None or d > newest else newest
        total += sum(sizes)
        count += len(sizes)
        if not token:
            break
    doc = {"bytes": total, "objects": count, "location": f"{bucket}/{prefix.rstrip('/')}",
           "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "newest": newest.astimezone(datetime.timezone.utc).isoformat(timespec="seconds") if newest else None}
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, out)
    print(f"{doc['location']}: {count} objects, {total} bytes")


if __name__ == "__main__":
    main()
