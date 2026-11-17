from pathlib import Path
from babel.messages.pofile import read_po, write_po
from babel.messages.mofile import write_mo

LOCALES_DIR = Path(__file__).resolve().parent / "app" / "locales"

FR = {
    "CSRF validation failed": "Échec de la validation CSRF",
    "Too many failed login attempts. Please try again later.": "Trop de tentatives de connexion échouées. Veuillez réessayer plus tard.",
    "Invalid email or password": "Email ou mot de passe invalide",
    "Not authenticated": "Non authentifié",
    "User not found": "Utilisateur introuvable",
    "Insufficient permissions": "Permissions insuffisantes",
    "Audit chain verified.": "Chaîne d'audit vérifiée.",
    "Audit chain integrity violation detected.": "Violation d'intégrité de la chaîne d'audit détectée.",
}
EN = {k: k for k in FR}


def run() -> None:
    for locale, entries in (("fr", FR), ("en", EN)):
        po = LOCALES_DIR / locale / "LC_MESSAGES" / "messages.po"
        mo = LOCALES_DIR / locale / "LC_MESSAGES" / "messages.mo"
        with po.open("rb") as f:
            catalog = read_po(f, locale=locale, domain="messages")
        added = 0
        for msgid, msgstr in entries.items():
            if msgid not in catalog:
                catalog.add(msgid, string=msgstr)
                added += 1
        with po.open("wb") as f:
            write_po(f, catalog, width=76)
        with mo.open("wb") as f:
            write_mo(f, catalog)
        print(f"[{locale}] added {added} entries")


if __name__ == "__main__":
    run()