import os
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from services import vddk_install


def _make_tarball(path, distrib_dirname="vmware-vix-disklib-distrib", libdir="lib64",
                  nest=None):
    """Build a tarball shaped like a VDDK release."""
    with tempfile.TemporaryDirectory() as staging:
        parts = [staging] + ([nest] if nest else []) + [distrib_dirname, libdir]
        target = os.path.join(*parts)
        os.makedirs(target)
        with open(os.path.join(target, "libvixDiskLib.so"), "wb") as fh:
            fh.write(b"\x7fELF-not-really")
        with tarfile.open(path, "w:gz") as tf:
            for entry in sorted(os.listdir(staging)):
                tf.add(os.path.join(staging, entry), arcname=entry)
    return path


class TestVersionParsing(unittest.TestCase):
    def test_parses_v8(self):
        self.assertEqual(
            vddk_install.parse_vddk_version("VMware-vix-disklib-8.0.3-24145417.x86_64.tar.gz"),
            (8, 0, 3))

    def test_parses_v9(self):
        self.assertEqual(
            vddk_install.parse_vddk_version("VMware-vix-disklib-9.0.0-24280709.x86_64.tar.gz"),
            (9, 0, 0))

    def test_unparseable_sorts_lowest(self):
        self.assertEqual(vddk_install.parse_vddk_version("random.tar.gz"), ())
        self.assertLess((), (8, 0, 3))

    def test_v9_outranks_v8(self):
        self.assertGreater(vddk_install.parse_vddk_version("VMware-vix-disklib-9.0.0.tar.gz"),
                           vddk_install.parse_vddk_version("VMware-vix-disklib-8.0.3.tar.gz"))

    def test_double_digit_minor_sorts_numerically(self):
        # string comparison would put 9.10 below 9.9
        self.assertGreater(vddk_install.parse_vddk_version("VMware-vix-disklib-9.10.0.tar.gz"),
                           vddk_install.parse_vddk_version("VMware-vix-disklib-9.9.0.tar.gz"))


class TestFindTarball(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(vddk_install, "VDDK_VENDOR_DIRS", [self.tmp.name])
        patcher.start(); self.addCleanup(patcher.stop)

    def test_picks_highest_version_not_newest_file(self):
        v9 = os.path.join(self.tmp.name, "VMware-vix-disklib-9.0.0-24280709.x86_64.tar.gz")
        v8 = os.path.join(self.tmp.name, "VMware-vix-disklib-8.0.3-24145417.x86_64.tar.gz")
        open(v9, "wb").close()
        open(v8, "wb").close()
        # make the OLDER version the NEWER file — mtime ordering would pick it
        os.utime(v9, (1_000_000, 1_000_000))
        os.utime(v8, (2_000_000, 2_000_000))
        self.assertEqual(vddk_install.find_vddk_tarball(), v9)

    def test_none_when_empty(self):
        self.assertIsNone(vddk_install.find_vddk_tarball())


class TestInstallFromTarball(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.libdir = os.path.join(self.tmp.name, "installed")

    def _install(self, **kwargs):
        tarball = _make_tarball(
            os.path.join(self.tmp.name, "VMware-vix-disklib-9.0.0-24280709.x86_64.tar.gz"),
            **kwargs)
        return vddk_install.install_vddk_from_tarball(tarball, self.libdir)

    def test_classic_layout(self):
        ok, msg = self._install()
        self.assertTrue(ok, msg)
        self.assertTrue(os.path.isfile(os.path.join(self.libdir, "lib64", "libvixDiskLib.so")))

    def test_version_qualified_directory_name(self):
        # the exact-name match would have failed here
        ok, msg = self._install(distrib_dirname="vmware-vix-disklib-9.0.0-distrib")
        self.assertTrue(ok, msg)
        self.assertTrue(os.path.isfile(os.path.join(self.libdir, "lib64", "libvixDiskLib.so")))

    def test_extra_nesting_level(self):
        ok, msg = self._install(nest="vddk")
        self.assertTrue(ok, msg)

    def test_lib32_only(self):
        ok, msg = self._install(libdir="lib32")
        self.assertTrue(ok, msg)

    def test_reports_version_in_message(self):
        ok, msg = self._install()
        self.assertTrue(ok)
        self.assertIn("9.0.0", msg)

    def test_tarball_without_the_library_is_rejected(self):
        bogus = os.path.join(self.tmp.name, "VMware-vix-disklib-9.0.0.tar.gz")
        with tempfile.TemporaryDirectory() as staging:
            os.makedirs(os.path.join(staging, "docs"))
            open(os.path.join(staging, "docs", "README.txt"), "w").close()
            with tarfile.open(bogus, "w:gz") as tf:
                tf.add(os.path.join(staging, "docs"), arcname="docs")
        ok, msg = vddk_install.install_vddk_from_tarball(bogus, self.libdir)
        self.assertFalse(ok)
        self.assertIn("libvixDiskLib.so", msg)

    def test_soname_compat_symlink_created_for_v9(self):
        # nbdkit plugins that only know libvixDiskLib.so.8 must still load a
        # v9-only VDDK — the failure mode was "cannot open shared object file".
        tarball = os.path.join(self.tmp.name, "VMware-vix-disklib-9.1.0.0-25379531.x86_64.tar.gz")
        with tempfile.TemporaryDirectory() as staging:
            target = os.path.join(staging, "vmware-vix-disklib-distrib", "lib64")
            os.makedirs(target)
            with open(os.path.join(target, "libvixDiskLib.so.9.1.0.0"), "wb") as fh:
                fh.write(b"\x7fELF-not-really")
            os.symlink("libvixDiskLib.so.9.1.0.0", os.path.join(target, "libvixDiskLib.so"))
            with tarfile.open(tarball, "w:gz") as tf:
                tf.add(os.path.join(staging, "vmware-vix-disklib-distrib"),
                       arcname="vmware-vix-disklib-distrib")
        ok, msg = vddk_install.install_vddk_from_tarball(tarball, self.libdir)
        self.assertTrue(ok, msg)
        compat = os.path.join(self.libdir, "lib64", "libvixDiskLib.so.8")
        self.assertTrue(os.path.islink(compat))
        self.assertEqual(os.readlink(compat), "libvixDiskLib.so.9.1.0.0")

    def test_is_vddk_installed_reflects_result(self):
        self.assertFalse(vddk_install.is_vddk_installed(self.libdir))
        self._install()
        self.assertTrue(vddk_install.is_vddk_installed(self.libdir))


if __name__ == "__main__":
    unittest.main()
