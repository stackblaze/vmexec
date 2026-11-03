"""Compression helpers for backup data (zlib for deltas, gzip for flat files)."""

import gzip
import os
import re
import shutil
import zlib


def effective_level(config_or_level):
    """Return 0-9 compression level; 0 means disabled."""
    if config_or_level is None:
        return 0
    if hasattr(config_or_level, "perf_compression_level"):
        level = getattr(config_or_level, "perf_compression_level", 0) or 0
    else:
        level = int(config_or_level or 0)
    return max(0, min(9, level))


def compress_bytes(data, level):
    if not data or level <= 0:
        return data, False
    return zlib.compress(data, level=level), True


def decompress_bytes(data):
    return zlib.decompress(data)


def gzip_file_inplace(path, level):
    """Compress file to path.gz and remove original. Returns new path."""
    if level <= 0 or not path or not os.path.isfile(path):
        return path
    gz_path = path + ".gz"
    with open(path, "rb") as f_in, gzip.open(gz_path, "wb", compresslevel=level) as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(path)
    return gz_path


def gunzip_to_path(gz_path, dest_path):
    with gzip.open(gz_path, "rb") as f_in, open(dest_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


def maybe_compress_flat_file(local_path, level):
    """Gzip a flat VMDK after write when compression enabled."""
    if level <= 0 or not local_path or not os.path.isfile(local_path):
        return local_path
    if local_path.endswith(".gz"):
        return local_path
    return gzip_file_inplace(local_path, level)


def compress_storage_file(storage, rel_path, level):
    """Gzip a file in local/NFS storage. Returns updated rel_path (may gain .gz)."""
    if level <= 0 or not rel_path:
        return rel_path
    if hasattr(storage, "base_path") and not storage.get_base_path().startswith("s3://"):
        local = os.path.join(storage.base_path, rel_path)
        if os.path.isfile(local):
            gz_local = maybe_compress_flat_file(local, level)
            if gz_local != local:
                return rel_path + ".gz"
    return rel_path


