"""Extraction of domain entries from UT1 category tarballs.

A UT1 tarball unpacks to ``<category>/domains`` (and optionally
``<category>/urls`` and ``<category>/usage``). EGGuard reads the
``domains`` member, normalises each entry, and returns a de-duplicated,
sorted list suitable for an EnforceGate ``match-domain-list`` directive.
"""

from __future__ import annotations

import io
import tarfile
from pathlib import PurePosixPath


class ParseError(RuntimeError):
    """A tarball did not contain a usable ``domains`` member."""


# A hardened cap on uncompressed size to defend against decompression
# bombs (the real adult list is a few MB; 512 MB is far beyond any
# legitimate category).
_MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


def extract_domains(tarball: bytes) -> list[str]:
    """Return the normalised, de-duplicated, sorted domains in *tarball*.

    Raises:
        ParseError: if no ``domains`` member is present or the archive is
            malformed.
    """
    seen: set[str] = set()

    try:
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
            member = _find_domains_member(archive)
            if member is None:
                raise ParseError("no 'domains' file found in archive")
            if member.size > _MAX_UNCOMPRESSED_BYTES:
                raise ParseError(
                    f"'domains' member is implausibly large ({member.size} bytes)"
                )
            handle = archive.extractfile(member)
            if handle is None:
                raise ParseError("could not read 'domains' member")
            raw = handle.read()
    except tarfile.TarError as exc:
        raise ParseError(f"malformed tar.gz archive: {exc}") from exc

    for line in raw.decode("utf-8", errors="replace").splitlines():
        domain = _normalise(line)
        if domain is not None:
            seen.add(domain)

    return sorted(seen)


def _find_domains_member(archive: tarfile.TarFile) -> tarfile.TarInfo | None:
    """Find the ``<category>/domains`` file, ignoring path-traversal entries."""
    for member in archive.getmembers():
        if not member.isfile():
            continue
        parts = PurePosixPath(member.name).parts
        # Reject absolute paths or any '..' traversal for safety.
        if member.name.startswith("/") or ".." in parts:
            continue
        if parts and parts[-1] == "domains":
            return member
    return None


def _normalise(line: str) -> str | None:
    """Normalise one raw line to a bare lowercase hostname, or ``None``.

    Drops blank lines and comments, strips an optional leading scheme and
    any trailing path, and lowercases the result.
    """
    text = line.strip()
    if not text or text.startswith("#"):
        return None

    # Strip a scheme if the upstream ever includes one (defensive).
    if "://" in text:
        text = text.split("://", 1)[1]

    # Keep only the host portion (UT1 'domains' files are already bare
    # hostnames, but a stray path or port is handled gracefully).
    text = text.split("/", 1)[0]
    text = text.split(":", 1)[0]
    text = text.strip(". ").lower()

    return text or None
