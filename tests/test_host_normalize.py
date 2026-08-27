import socket
import unittest
from unittest.mock import patch

from pyVmomi import vim

import esxi_handler


class TestSplitHostPort(unittest.TestCase):
    """SmartConnect wants a bare hostname; everything else is a DNS miss."""

    def test_bare_hostname_untouched(self):
        self.assertEqual(esxi_handler.split_host_port("vcenter.example.com"),
                         ("vcenter.example.com", None))

    def test_bare_ip_untouched(self):
        self.assertEqual(esxi_handler.split_host_port("10.0.0.50"), ("10.0.0.50", None))

    def test_strips_https_scheme(self):
        self.assertEqual(esxi_handler.split_host_port("https://vcenter.example.com"),
                         ("vcenter.example.com", None))

    def test_strips_trailing_slash(self):
        self.assertEqual(esxi_handler.split_host_port("vcenter.example.com/"),
                         ("vcenter.example.com", None))

    def test_strips_scheme_and_trailing_slash(self):
        self.assertEqual(esxi_handler.split_host_port("https://vcenter.example.com/"),
                         ("vcenter.example.com", None))

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(esxi_handler.split_host_port("  vcenter.example.com  "),
                         ("vcenter.example.com", None))

    def test_keeps_explicit_port(self):
        self.assertEqual(esxi_handler.split_host_port("vcenter.example.com:8443"),
                         ("vcenter.example.com", 8443))

    def test_strips_path(self):
        self.assertEqual(esxi_handler.split_host_port("https://vcenter.example.com/sdk"),
                         ("vcenter.example.com", None))

    def test_empty_input(self):
        self.assertEqual(esxi_handler.split_host_port(""), ("", None))
        self.assertEqual(esxi_handler.split_host_port(None), ("", None))


class TestNormalizeHost(unittest.TestCase):
    def test_roundtrips_plain_host(self):
        self.assertEqual(esxi_handler.normalize_host("https://vc.example.com/"), "vc.example.com")

    def test_preserves_non_default_port(self):
        self.assertEqual(esxi_handler.normalize_host("vc.example.com:8443"), "vc.example.com:8443")


class TestDescribeConnectFailure(unittest.TestCase):
    """Every failure used to collapse into one opaque message."""

    def test_invalid_login_is_named_as_credentials(self):
        msg = esxi_handler.describe_connect_failure("vc.example.com", vim.fault.InvalidLogin())
        self.assertIn("username or password", msg)

    def test_dns_failure_points_at_the_address_format(self):
        msg = esxi_handler.describe_connect_failure("bad host", socket.gaierror(-2, "Name or service not known"))
        self.assertIn("could not be resolved", msg)
        self.assertIn("no trailing slash", msg)

    def test_timeout_is_distinct(self):
        msg = esxi_handler.describe_connect_failure("vc.example.com", socket.timeout())
        self.assertIn("Timed out", msg)

    def test_refused_is_distinct(self):
        msg = esxi_handler.describe_connect_failure("vc.example.com", ConnectionRefusedError())
        self.assertIn("refused", msg)


class TestConnectEsxiContract(unittest.TestCase):
    def test_returns_none_by_default_so_existing_callers_are_unaffected(self):
        with patch.object(esxi_handler, "SmartConnect", side_effect=vim.fault.InvalidLogin()):
            self.assertIsNone(esxi_handler.connect_esxi("vc.example.com", "u", "p"))

    def test_raises_with_reason_when_asked(self):
        with patch.object(esxi_handler, "SmartConnect", side_effect=vim.fault.InvalidLogin()):
            with self.assertRaises(esxi_handler.VSphereConnectionError) as ctx:
                esxi_handler.connect_esxi("vc.example.com", "u", "p", raise_on_error=True)
        self.assertIn("username or password", str(ctx.exception))

    def test_normalizes_before_connecting(self):
        with patch.object(esxi_handler, "SmartConnect") as sc:
            esxi_handler.connect_esxi("https://vc.example.com/", "u", "p")
        self.assertEqual(sc.call_args.kwargs["host"], "vc.example.com")
        self.assertNotIn("port", sc.call_args.kwargs)

    def test_passes_explicit_port_through(self):
        with patch.object(esxi_handler, "SmartConnect") as sc:
            esxi_handler.connect_esxi("vc.example.com:8443", "u", "p")
        self.assertEqual(sc.call_args.kwargs["port"], 8443)

    def test_empty_host_raises_without_touching_the_network(self):
        with patch.object(esxi_handler, "SmartConnect") as sc:
            with self.assertRaises(esxi_handler.VSphereConnectionError):
                esxi_handler.connect_esxi("   ", "u", "p", raise_on_error=True)
        sc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
