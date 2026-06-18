"""The catalogue of UT1 Capitole blacklist categories.

The Université Toulouse Capitole publishes its blacklist as a set of
per-category gzipped tarballs at
https://dsi.ut-capitole.fr/blacklists/download/<name>.tar.gz

Each archive unpacks to a ``<name>/`` directory containing a ``domains``
file (one hostname per line) and, for some categories, a ``urls`` file.
EGGuard consumes the ``domains`` file only.

The ``Action`` attached to each category is a *suggested* default
action, not a hard rule: operators override any of these per category in
``config.yaml``. The suggestions follow the spirit of the UT1
documentation, which stresses that the lists are a *categorisation* of
sites rather than a fixed block list — for example ``child`` and
``liste_bu`` are whitelists, and ``press`` may be allowed or denied
depending on context.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Action(enum.Enum):
    """A suggested default action for a category.

    Maps directly onto EnforceGate's four policy actions.
    """

    DENY = "deny"
    WARN = "warn"
    AUP = "aup"
    PERMIT = "permit"


# Feed formats — how a downloaded feed is parsed into domains.
FMT_UT1_TARBALL = (
    "ut1-tarball"  # UT1's <category>.tar.gz with a `domains` member
)
FMT_HOSTFILE = "hostfile"  # a hosts-format list ("0.0.0.0 domain" per line)


@dataclass(frozen=True, slots=True)
class Category:
    """A single feed (a UT1 category, or another source) and its handling.

    ``source`` namespaces the feed (``ut1``, ``abusech``); it prefixes the
    generated file/rule names so feeds from different sources never collide.
    """

    name: str
    description: str
    disposition: Action
    source: str = "ut1"
    fmt: str = FMT_UT1_TARBALL
    # Source-specific download path; defaults to ``name`` (UT1 uses the name).
    remote: str = ""

    @property
    def fetch_path(self) -> str:
        """The path/identifier used to build this feed's download URL."""
        return self.remote or self.name

    @property
    def slug(self) -> str:
        """Stable identifier used for file names and the rule name."""
        return f"{self.source}-{self.name}"

    @property
    def list_filename(self) -> str:
        """File name used for this feed's domain list."""
        return f"{self.slug}.list"

    def policy_filename(self, prefix: str) -> str:
        """File name used for this feed's generated policy."""
        return f"{prefix}-{self.slug}.policy"


# --------------------------------------------------------------------------- #
# The full catalogue — the UT1 categories plus a few non-UT1 feeds (abuse.ch).
# UT1 descriptions are concise English renderings of the upstream French text.
# --------------------------------------------------------------------------- #
_D = Action

CATALOGUE: tuple[Category, ...] = (
    Category(
        "adult", "Adult content — erotic to hard-core pornography", _D.DENY
    ),
    Category(
        "agressif",
        "Hate speech — racist, antisemitic, incitement to hatred",
        _D.DENY,
    ),
    Category("ai", "Artificial-intelligence services", _D.WARN),
    Category("arjel", "Online gambling certified by ARJEL (France)", _D.DENY),
    Category("associations_religieuses", "Religious associations", _D.PERMIT),
    Category("astrology", "Astrology", _D.WARN),
    Category("audio-video", "Audio and video streaming", _D.WARN),
    Category("bank", "Online banking", _D.PERMIT),
    Category("bitcoin", "Bitcoin and cryptocurrency", _D.WARN),
    Category("blog", "Blog-hosting platforms", _D.WARN),
    Category("celebrity", "Celebrity and tabloid news", _D.WARN),
    Category("chat", "Chat and online messaging", _D.WARN),
    Category("child", "Whitelist — safe for young children", _D.PERMIT),
    Category("cleaning", "PC cleaning, antivirus and update tools", _D.PERMIT),
    Category("cooking", "Cooking and recipes", _D.WARN),
    Category("cryptojacking", "Cryptomining / cryptojacking", _D.DENY),
    Category(
        "dangerous_material",
        "Dangerous material — explosives, poisons, etc.",
        _D.DENY,
    ),
    Category("dating", "Online dating", _D.WARN),
    Category("ddos", "DDoS attack resources", _D.DENY),
    Category("dialer", "Dialer programs", _D.DENY),
    Category("doh", "DNS-over-HTTPS servers and equivalents", _D.DENY),
    Category("download", "Software download sites", _D.WARN),
    Category("drogue", "Drugs", _D.DENY),
    Category("dynamic-dns", "Dynamic-DNS providers", _D.WARN),
    Category("educational_games", "Educational games", _D.PERMIT),
    Category(
        "examen_pix", "French PIX exam — allow list (FR exams only)", _D.PERMIT
    ),
    Category("fakenews", "Fake-news sites", _D.WARN),
    Category("filehosting", "File hosting — video, image, audio", _D.WARN),
    Category("financial", "Financial information and stock markets", _D.PERMIT),
    Category("forums", "Online forums", _D.WARN),
    Category("gambling", "Online gambling and casinos", _D.DENY),
    Category("games", "Online and downloadable games", _D.WARN),
    Category("hacking", "Hacking and computer-intrusion tools", _D.DENY),
    Category("jobsearch", "Job-search sites", _D.WARN),
    Category("lingerie", "Lingerie", _D.WARN),
    Category(
        "liste_bu", "University-library whitelist (UT1-specific)", _D.PERMIT
    ),
    Category("malware", "Malware-distribution sites", _D.DENY),
    Category("manga", "Manga and comics", _D.WARN),
    Category("marketingware", "Aggressive marketing software", _D.DENY),
    Category(
        "mixed_adult", "Mixed adult — unstructured adult portions", _D.DENY
    ),
    Category("mobile-phone", "Mobile-phone content (ringtones, etc.)", _D.WARN),
    Category("phishing", "Phishing and banking-fraud sites", _D.DENY),
    Category("press", "News and press", _D.WARN),
    Category("publicite", "Advertising and tracking", _D.DENY),
    Category("radio", "Internet radio", _D.WARN),
    Category("reaffected", "Domains that changed owner and content", _D.WARN),
    Category("redirector", "Filter-bypass redirectors", _D.DENY),
    Category(
        "remote-control", "Remote-control and remote-access tools", _D.WARN
    ),
    Category("residential-proxies", "Residential-proxy services", _D.DENY),
    Category("sect", "Cults and sects", _D.DENY),
    Category(
        "sexual_education",
        "Sexual education (may trigger adult filters)",
        _D.PERMIT,
    ),
    Category("shopping", "Online shopping and e-commerce", _D.WARN),
    Category("shortener", "URL shorteners", _D.DENY),
    Category("social_networks", "Social networks", _D.WARN),
    Category("sports", "Sports", _D.WARN),
    Category("stalkerware", "Stalkerware and consumer spyware", _D.DENY),
    Category(
        "strict_redirector",
        "Strict redirectors (includes search engines)",
        _D.DENY,
    ),
    Category(
        "strong_redirector",
        "Strong redirectors (blocks specific search terms)",
        _D.DENY,
    ),
    Category("translation", "Translation sites", _D.WARN),
    Category("tricheur", "Exam cheating — general", _D.DENY),
    Category("tricheur_pix", "Exam cheating — French PIX", _D.DENY),
    Category("update", "OS and software update sites", _D.PERMIT),
    Category("vpn", "VPN services", _D.DENY),
    Category("warez", "Warez — pirated software and media", _D.DENY),
    Category("webhosting", "Web-hosting services", _D.WARN),
    Category("webmail", "Webmail services", _D.WARN),
    # --- abuse.ch feeds (need a free Auth-Key; see config.abusech_auth_key) -- #
    Category(
        "urlhaus",
        "abuse.ch URLhaus — active malware-distribution hosts",
        _D.DENY,
        source="abusech",
        fmt=FMT_HOSTFILE,
        remote="hostfile",
    ),
)

# Fast lookup by name.
BY_NAME: dict[str, Category] = {c.name: c for c in CATALOGUE}


def all_names() -> list[str]:
    """Return every known category name, in catalogue order."""
    return [c.name for c in CATALOGUE]


def get(name: str) -> Category:
    """Look up a category by name.

    Raises:
        KeyError: if *name* is not a known UT1 category.
    """
    return BY_NAME[name]
