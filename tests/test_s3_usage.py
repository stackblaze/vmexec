"""deploy/s3-usage.py: totals and the newest write (install.sh's one-writer check)."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

_spec = importlib.util.spec_from_file_location(
    "s3_usage", os.path.join(os.path.dirname(__file__), "..", "deploy", "s3-usage.py"))
s3_usage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s3_usage)

PAGE = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <IsTruncated>{trunc}</IsTruncated>{token}
  {items}
</ListBucketResult>"""
ITEM = "<Contents><Key>vmexec/{k}</Key><LastModified>{t}</LastModified><Size>{s}</Size></Contents>"


def page(items, token=None):
    body = PAGE.format(trunc="true" if token else "false",
                       token=f"<NextContinuationToken>{token}</NextContinuationToken>" if token else "",
                       items="".join(ITEM.format(k=i, t=t, s=s) for i, (t, s) in enumerate(items)))
    r = io.BytesIO(body.encode())
    r.__enter__ = lambda *a: r
    r.__exit__ = lambda *a: None
    return r


class TestS3Usage(unittest.TestCase):
    def run_main(self, pages):
        out = os.path.join(tempfile.mkdtemp(), "u.json")
        argv = ["s3-usage.py", "https://s3.example", "r", "b", "vmexec", out]
        env = {"AWS_ACCESS_KEY_ID": "a", "AWS_SECRET_ACCESS_KEY": "s"}
        with patch.object(sys, "argv", argv), patch.dict(os.environ, env), \
                patch.object(s3_usage.urllib.request, "urlopen", side_effect=pages), \
                patch("builtins.print"):
            s3_usage.main()
        return json.load(open(out))

    def test_newest_across_pages(self):
        doc = self.run_main([
            page([("2026-11-04T14:00:00.000Z", 10), ("2026-11-04T14:30:48.123Z", 5)], token="t"),
            page([("2026-11-03T09:00:00Z", 1)]),
        ])
        self.assertEqual((doc["objects"], doc["bytes"]), (3, 16))
        self.assertEqual(doc["newest"], "2026-11-04T14:30:48+00:00")

    def test_empty_prefix(self):
        doc = self.run_main([page([])])
        self.assertEqual(doc["objects"], 0)
        self.assertIsNone(doc["newest"])


if __name__ == "__main__":
    unittest.main()
