"""Tests for the tarball parser."""

from __future__ import annotations

import io
import tarfile

import pytest

from egguard.parser import ParseError, extract_domains
from tests.conftest import make_tarball


def test_extracts_and_normalises_domains(sample_tarball: bytes) -> None:
    domains = extract_domains(sample_tarball)
    # Lowercased, trimmed, comments/blanks dropped, de-duplicated, sorted.
    assert domains == ["bad-site.net", "dup.com", "example.com", "spaced.org"]


def test_deduplicates() -> None:
    tarball = make_tarball("x", ["a.com", "a.com", "b.com"])
    assert extract_domains(tarball) == ["a.com", "b.com"]


def test_strips_scheme_and_path() -> None:
    tarball = make_tarball(
        "x", ["https://host.com/some/path", "host2.com:8080"]
    )
    assert extract_domains(tarball) == ["host.com", "host2.com"]


def test_missing_domains_member_raises() -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        data = b"nothing\n"
        info = tarfile.TarInfo(name="x/urls")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    with pytest.raises(ParseError, match="no 'domains' file"):
        extract_domains(buf.getvalue())


def test_malformed_archive_raises() -> None:
    with pytest.raises(ParseError, match="malformed"):
        extract_domains(b"this is not a gzip tarball")


def test_path_traversal_member_ignored() -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        data = b"evil.com\n"
        info = tarfile.TarInfo(name="../../etc/domains")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    # The traversal entry is the only 'domains' file; it must be ignored.
    with pytest.raises(ParseError):
        extract_domains(buf.getvalue())
