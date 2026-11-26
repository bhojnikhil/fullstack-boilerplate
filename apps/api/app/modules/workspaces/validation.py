"""Workspace field rules: slug, ISO 4217 currency and IANA timezone."""

import re
import unicodedata
from functools import cache
from zoneinfo import available_timezones

SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.ASCII)
MIN_SLUG_LENGTH = 3
MAX_SLUG_LENGTH = 48

# Active ISO 4217 alphabetic codes (currencies, not funds or metals: no XAU, XDR, XXX).
# Update this list when ISO 4217 publishes an amendment.
CURRENCIES = frozenset(
    """
    AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD
    CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS
    GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW
    KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR
    MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR
    SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX
    USD UYU UZS VES VND VUV WST XAF XCD XOF XPF YER ZAR ZMW ZWG
    """.split()  # noqa: SIM905
)


@cache
def timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def validate_slug(slug: str) -> str:
    if not MIN_SLUG_LENGTH <= len(slug) <= MAX_SLUG_LENGTH or not SLUG_PATTERN.fullmatch(slug):
        raise ValueError(
            f"Use {MIN_SLUG_LENGTH}-{MAX_SLUG_LENGTH} lowercase letters, digits and single hyphens"
        )
    return slug


def validate_currency(code: str) -> str:
    code = code.strip().upper()
    if code not in CURRENCIES:
        raise ValueError("Use an ISO 4217 currency code such as USD or EUR")
    return code


def validate_timezone(name: str) -> str:
    name = name.strip()
    if name not in timezones():
        raise ValueError("Use an IANA timezone name such as Europe/Berlin")
    return name


def printable(value: str) -> str:
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("Control characters are not allowed")
    return value


def slugify(name: str) -> str:
    """A slug candidate from a display name (ASCII letters and digits only)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[: MAX_SLUG_LENGTH - 9]
    return slug.strip("-") or "workspace"
