import os
from fastapi import Request
from babel.support import Translations

SUPPORTED_LOCALES = ["en", "fr"]
DEFAULT_LOCALE = "fr"  # OHADA/CEMAC default

# Path to the locales directory (project_root/locales)
LOCALES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "locales")


def get_locale(request: Request) -> str:
    """Determine the user's preferred locale directly from the request object."""

    # 1. Query parameter (e.g., ?lang=en)
    query_lang = request.query_params.get("lang")
    if query_lang in SUPPORTED_LOCALES:
        return query_lang

    # 2. Cookie (read directly from request.cookies)
    lang_cookie = request.cookies.get("lang")
    if lang_cookie in SUPPORTED_LOCALES:
        return lang_cookie

    # 3. Accept-Language header (read directly from request.headers)
    accept_language = request.headers.get("accept-language")
    if accept_language:
        first_lang = accept_language.split(",")[0].split("-")[0].lower()
        if first_lang in SUPPORTED_LOCALES:
            return first_lang

    # 4. Default
    return DEFAULT_LOCALE


def get_translator(locale: str) -> Translations:
    """Load the Babel translation catalog for the given locale."""
    try:
        return Translations.load(LOCALES_DIR, [locale])
    except Exception:
        # Fallback to default if locale not found
        return Translations.load(LOCALES_DIR, [DEFAULT_LOCALE])