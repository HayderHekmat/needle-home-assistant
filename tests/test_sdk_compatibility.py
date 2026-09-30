"""Regression checks for the SDK libc handling required by Home Assistant."""

from unittest.mock import mock_open, patch

import needle
from needle.agent import fetch


def test_musl_maps_override_misleading_libc_version():
    with (
        patch.object(fetch.sys, "platform", "linux"),
        patch.object(fetch.platform, "libc_ver", return_value=("glibc", "2.39")),
        patch("builtins.open", mock_open(read_data=b"/lib/ld-musl-x86_64.so.1")),
    ):
        assert fetch._is_musl()


def test_wrong_cached_library_retries_musl_build(tmp_path):
    cached = str(tmp_path / "libneedle.so")
    loaded = object()
    with (
        patch.object(needle, "_library_path", return_value=cached),
        patch.object(
            needle.ctypes,
            "CDLL",
            side_effect=[OSError("ld-linux-x86-64.so.2: not found"), loaded],
        ),
        patch.object(fetch, "other_libc_tag", return_value="musllinux_1_2_x86_64"),
        patch.object(fetch, "_platform_tag", return_value="manylinux2014_x86_64"),
        patch.object(fetch, "fetch_library", return_value=cached) as download,
        patch.object(needle.warnings, "warn"),
    ):
        assert needle._load_cdll(3) is loaded
    download.assert_called_once_with(
        dest_dir=str(tmp_path), tag="musllinux_1_2_x86_64", generation=3
    )


def test_updated_engine_uses_a_new_cache_namespace():
    assert fetch.engine_version(3) != "3.0.1"
    assert fetch.cache_dir(3).endswith(fetch.engine_version(3))
