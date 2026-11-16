import re
from pathlib import Path

from fastapi import Request
from babel.support import Translations
from babel.messages.pofile import read_po
from babel.messages.mofile import write_mo

SUPPORTED_LOCALES = ["en", "fr"]
DEFAULT_LOCALE = "fr"
DOMAIN = "messages"

# app/core/i18n.py -> project root / locales
LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"


def compile_catalogs(force: bool = False) -> None:
    """
    Compile .po -> .mo automatically.
    This removes the manual pybabel step and prevents stale catalogs.
    """
    for locale in SUPPORTED_LOCALES:
        po_path = LOCALES_DIR / locale / "LC_MESSAGES" / f"{DOMAIN}.po"
        mo_path = LOCALES_DIR / locale / "LC_MESSAGES" / f"{DOMAIN}.mo"

        if not po_path.exists():
            continue

        mo_path.parent.mkdir(parents=True, exist_ok=True)

        if (
            not force
            and mo_path.exists()
            and mo_path.stat().st_mtime >= po_path.stat().st_mtime
        ):
            continue

        with po_path.open("rb") as f:
            catalog = read_po(f, locale=locale, domain=DOMAIN)

        with mo_path.open("wb") as f:
            write_mo(f, catalog)


def get_locale(request: Request) -> str:
    query_lang = request.query_params.get("lang")
    if query_lang in SUPPORTED_LOCALES:
        return query_lang

    cookie_lang = request.cookies.get("lang")
    if cookie_lang in SUPPORTED_LOCALES:
        return cookie_lang

    accept_language = request.headers.get("accept-language")
    if accept_language:
        first = accept_language.split(",")[0].split(";")[0].strip().lower()
        primary = first.split("-")[0]
        if primary in SUPPORTED_LOCALES:
            return primary

    return DEFAULT_LOCALE


def get_translator(locale: str) -> Translations:
    compile_catalogs()
    return Translations.load(
        dirname=str(LOCALES_DIR),
        locales=[locale],
        domain=DOMAIN,
    )


# Dynamic service messages -> translatable templates.
# These patterns match the exact f-strings raised by the service layer.
_DYNAMIC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^Journal '(?P<journal_code>.+)' does not exist\.$"),
        "Journal '{journal_code}' does not exist.",
    ),
    (
        re.compile(r"^Account (?P<account_code>\S+) is invalid, inactive, or not postable\.$"),
        "Account {account_code} is invalid, inactive, or not postable.",
    ),
    (
        re.compile(r"^Account (?P<account_code>\S+) \(Class 4\) requires a linked Third Party \(Tiers\)\.$"),
        "Account {account_code} (Class 4) requires a linked Third Party (Tiers).",
    ),
    (
        re.compile(r"^Account (?P<account_code>\S+) is invalid or not postable\.$"),
        "Account {account_code} is invalid or not postable.",
    ),
    (
        re.compile(r"^Budget exceeded for account (?P<account_code>\S+)\. Approved: (?P<approved>.+), Spent \+ New: (?P<spent>.+)$"),
        "Budget exceeded for account {account_code}. Approved: {approved}, Spent + New: {spent}",
    ),
    (
        re.compile(r"^Entry is unbalanced\. Debit: (?P<debit>.+), Credit: (?P<credit>.+)$"),
        "Entry is unbalanced. Debit: {debit}, Credit: {credit}",
    ),
    (
        re.compile(r"^Cannot post entry with status: (?P<status>.+)$"),
        "Cannot post entry with status: {status}",
    ),
    (
        re.compile(r"^Cannot close period: The ledger is unbalanced\. Debit: (?P<debit>.+), Credit: (?P<credit>.+)$"),
        "Cannot close period: The ledger is unbalanced. Debit: {debit}, Credit: {credit}",
    ),
    (
        re.compile(r"^Journal entry (?P<voucher>.+) has been POSTED\.$"),
        "Journal entry {voucher} has been POSTED.",
    ),
    (
        re.compile(r"^Reversal posted as (?P<voucher>.+)\.$"),
        "Reversal posted as {voucher}.",
    ),
    (
        re.compile(r"^Depreciation posted as (?P<voucher>.+)\.$"),
        "Depreciation posted as {voucher}.",
    ),
    (
        re.compile(r"^Allocation exceeds outstanding balance on bill (?P<reference>.+)\. Outstanding: (?P<outstanding>.+)$"),
        "Allocation exceeds outstanding balance on bill {reference}. Outstanding: {outstanding}",
    ),
]


def translate_message(request: Request, message: str | None) -> str:
    """
    Translate a static or dynamic user-facing message using the request locale.
    """
    if not message:
        return ""

    message = str(message)
    translator = get_translator(get_locale(request))

    translated = translator.gettext(message)
    if translated != message:
        return translated

    for pattern, key in _DYNAMIC_PATTERNS:
        match = pattern.fullmatch(message)
        if match:
            template = translator.gettext(key)
            return template.format(**match.groupdict())

    return message