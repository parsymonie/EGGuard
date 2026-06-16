"""Shared pytest fixtures and helpers."""

from __future__ import annotations

import io
import tarfile

import pytest


def make_tarball(category: str, domains: list[str], *, with_urls: bool = True) -> bytes:
    """Build a UT1-style ``<category>.tar.gz`` in memory.

    The archive contains ``<category>/domains`` and, optionally,
    ``<category>/urls`` — mirroring the real upstream layout.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        domains_bytes = ("\n".join(domains) + "\n").encode("utf-8")
        info = tarfile.TarInfo(name=f"{category}/domains")
        info.size = len(domains_bytes)
        tf.addfile(info, io.BytesIO(domains_bytes))

        if with_urls:
            urls_bytes = b"example.com/path\n"
            uinfo = tarfile.TarInfo(name=f"{category}/urls")
            uinfo.size = len(urls_bytes)
            tf.addfile(uinfo, io.BytesIO(urls_bytes))

    return buf.getvalue()


@pytest.fixture
def sample_tarball() -> bytes:
    return make_tarball(
        "adult",
        ["example.com", "Bad-Site.NET", "  spaced.org  ", "", "# comment", "dup.com", "dup.com"],
    )
