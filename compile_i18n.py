"""
Merge missing translations and compile catalogs.
Run: python compile_i18n.py
"""
from pathlib import Path

from babel.messages.pofile import read_po, write_po
from babel.messages.mofile import write_mo

LOCALES_DIR = Path(__file__).resolve().parent / "app" / "locales"
DOMAIN = "messages"
LOCALES = ["fr", "en"]

EXTRA = {
    "fr": {
        # Dynamic service messages
        "Journal '{journal_code}' does not exist.": "Le journal '{journal_code}' n'existe pas.",
        "Account {account_code} is invalid, inactive, or not postable.": "Le compte {account_code} est invalide, inactif ou non mouvementable.",
        "Account {account_code} (Class 4) requires a linked Third Party (Tiers).": "Le compte {account_code} (Classe 4) exige un Tiers associé.",
        "Account {account_code} is invalid or not postable.": "Le compte {account_code} est invalide ou non mouvementable.",
        "Budget exceeded for account {account_code}. Approved: {approved}, Spent + New: {spent}": "Budget dépassé pour le compte {account_code}. Approuvé : {approved}, Consommé + Nouveau : {spent}",
        "Entry is unbalanced. Debit: {debit}, Credit: {credit}": "L'écriture est déséquilibrée. Débit : {debit}, Crédit : {credit}",
        "Cannot post entry with status: {status}": "Impossible de valider une écriture au statut : {status}",
        "Cannot close period: The ledger is unbalanced. Debit: {debit}, Credit: {credit}": "Impossible de clôturer la période : le grand livre est déséquilibré. Débit : {debit}, Crédit : {credit}",
        "Journal entry {voucher} has been POSTED.": "L'écriture {voucher} a été VALIDÉE.",
        "Reversal posted as {voucher}.": "Contre-passation validée sous {voucher}.",
        "Journal entry saved as DRAFT.": "Écriture enregistrée en brouillon.",
        "Paramètres mis à jour avec succès.": "Paramètres mis à jour avec succès.",
        "Email ou mot de passe invalide": "Email ou mot de passe invalide",
        "Invalid email or password": "Email ou mot de passe invalide",
        # Hardcoded template labels
        "Fournisseur (Tiers)": "Fournisseur (Tiers)",
        "Total Base (XAF)": "Total base (XAF)",
        "Retenue à la source (447)": "Retenue à la source (447)",
        "Aperçu des Écritures Comptables (GL Preview)": "Aperçu des écritures comptables",
        "Charges (Lignes de facture)": "Charges (lignes de facture)",
        "État, impôts retenus à la source": "État, impôts retenus à la source",
        "Écart:": "Écart :",
        "Équilibre:": "Équilibre :",
        "Enregistrer la Facture": "Enregistrer la facture",
        "Multi-Devises (Multi-Currency)": "Multi-devises",
        "Activer la gestion des taux de change et des écritures en devises.": "Activer la gestion des taux de change et des écritures en devises.",
        "Suivi par Bailleur (Donor Tracking)": "Suivi par bailleur",
        "Activer les fonds dédiés (Classe 16x) et l'affectation par projet.": "Activer les fonds dédiés (Classe 16x) et l'affectation par projet.",
        "Enregistrer": "Enregistrer",
        "Fournisseur": "Fournisseur",
        "Compte": "Compte",
        "Libellé": "Libellé",
        "Débit (XAF)": "Débit (XAF)",
        "Crédit (XAF)": "Crédit (XAF)",
    },
    "en": {
        "Journal '{journal_code}' does not exist.": "Journal '{journal_code}' does not exist.",
        "Account {account_code} is invalid, inactive, or not postable.": "Account {account_code} is invalid, inactive, or not postable.",
        "Account {account_code} (Class 4) requires a linked Third Party (Tiers).": "Account {account_code} (Class 4) requires a linked Third Party.",
        "Account {account_code} is invalid or not postable.": "Account {account_code} is invalid or not postable.",
        "Budget exceeded for account {account_code}. Approved: {approved}, Spent + New: {spent}": "Budget exceeded for account {account_code}. Approved: {approved}, Spent + New: {spent}",
        "Entry is unbalanced. Debit: {debit}, Credit: {credit}": "Entry is unbalanced. Debit: {debit}, Credit: {credit}",
        "Cannot post entry with status: {status}": "Cannot post entry with status: {status}",
        "Cannot close period: The ledger is unbalanced. Debit: {debit}, Credit: {credit}": "Cannot close period: The ledger is unbalanced. Debit: {debit}, Credit: {credit}",
        "Journal entry {voucher} has been POSTED.": "Journal entry {voucher} has been POSTED.",
        "Reversal posted as {voucher}.": "Reversal posted as {voucher}.",
        "Journal entry saved as DRAFT.": "Journal entry saved as DRAFT.",
        "Paramètres mis à jour avec succès.": "Settings updated successfully.",
        "Email ou mot de passe invalide": "Invalid email or password",
        "Invalid email or password": "Invalid email or password",
        "Fournisseur (Tiers)": "Supplier (Third Party)",
        "Total Base (XAF)": "Total Base (XAF)",
        "Retenue à la source (447)": "Withholding Tax (447)",
        "Aperçu des Écritures Comptables (GL Preview)": "Generated Journal Entries Preview",
        "Charges (Lignes de facture)": "Expenses (Bill Lines)",
        "État, impôts retenus à la source": "State, taxes withheld at source",
        "Écart:": "Difference:",
        "Équilibre:": "Balance:",
        "Enregistrer la Facture": "Save Bill",
        "Multi-Devises (Multi-Currency)": "Multi-Currency",
        "Activer la gestion des taux de change et des écritures en devises.": "Enable exchange rates and foreign currency entries.",
        "Suivi par Bailleur (Donor Tracking)": "Donor Tracking",
        "Activer les fonds dédiés (Classe 16x) et l'affectation par projet.": "Enable restricted funds (Class 16x) and project allocation.",
        "Enregistrer": "Save",
        "Fournisseur": "Supplier",
        "Compte": "Account",
        "Libellé": "Description",
        "Débit (XAF)": "Debit (XAF)",
        "Crédit (XAF)": "Credit (XAF)",
    },
}


def run() -> None:
    for locale in LOCALES:
        po_path = LOCALES_DIR / locale / "LC_MESSAGES" / f"{DOMAIN}.po"
        mo_path = LOCALES_DIR / locale / "LC_MESSAGES" / f"{DOMAIN}.mo"

        if not po_path.exists():
            raise FileNotFoundError(f"Missing catalog: {po_path}")

        with po_path.open("rb") as f:
            catalog = read_po(f, locale=locale, domain=DOMAIN)

        added = 0
        for msgid, msgstr in EXTRA[locale].items():
            if msgid not in catalog:
                catalog.add(msgid, string=msgstr)
                added += 1

        with po_path.open("wb") as f:
            write_po(f, catalog, width=76)

        with mo_path.open("wb") as f:
            write_mo(f, catalog)

        print(f"[{locale}] added {added} entries -> compiled {mo_path}")

    # Verify
    from babel.support import Translations

    for locale in LOCALES:
        t = Translations.load(str(LOCALES_DIR), [locale], domain=DOMAIN)
        print(
            f"[{locale}] "
            f"Reversal={t.gettext('Reversal (Contre-passation)')!r} | "
            f"PostEntry={t.gettext('Post Entry')!r} | "
            f"BurnRate={t.gettext('Burn Rate')!r}"
        )


if __name__ == "__main__":
    run()