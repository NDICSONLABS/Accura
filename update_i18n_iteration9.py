from pathlib import Path
from babel.messages.pofile import read_po, write_po
from babel.messages.mofile import write_mo

LOCALES_DIR = Path(__file__).resolve().parent / "app" / "locales"

ENTRIES = {
    "fr": {
        "Fixed Assets": "Immobilisations",
        "New Fixed Asset": "Nouvelle immobilisation",
        "No fixed assets found.": "Aucune immobilisation trouvée.",
        "Search by code or label": "Rechercher par code ou libellé",
        "In Service": "Mise en service",
        "Acquisition Cost": "Coût d'acquisition",
        "Method": "Méthode",
        "Monthly Depreciation": "Amortissement mensuel",
        "Generate Schedule": "Générer le plan",
        "Post Depreciation": "Valider l'amortissement",
        "View Schedule": "Voir le plan",
        "Post depreciation for this period?": "Valider l'amortissement pour cette période ?",
        "Acquisition Date": "Date d'acquisition",
        "In Service Date": "Date de mise en service",
        "Acquisition Cost (XAF)": "Coût d'acquisition (XAF)",
        "Residual Value (XAF)": "Valeur résiduelle (XAF)",
        "Useful Life (months)": "Durée de vie (mois)",
        "Declining Rate (% annual)": "Taux dégressif (% annuel)",
        "Asset Account": "Compte d'immobilisation",
        "Depreciation Expense Account": "Compte de dotation",
        "Accumulated Depreciation Account": "Compte d'amortissement cumulé",
        "Save Asset": "Enregistrer l'immobilisation",
        "Back to Assets": "Retour aux immobilisations",
        "Accumulated Depreciation": "Amortissements cumulés",
        "Net Book Value": "Valeur nette comptable",
        "Useful Life": "Durée de vie",
        "months": "mois",
        "Expense Account": "Compte de charge",
        "Accumulated Account": "Compte d'amortissement",
        "No depreciation schedule yet.": "Aucun plan d'amortissement.",
        "Depreciation Schedule": "Plan d'amortissement",
        "Asset": "Immobilisation",
        "Proposed": "Proposé",
        "Amount": "Montant",
        "Journal Entry": "Écriture",
        "No schedule for this period. Generate it first.": "Aucun plan pour cette période. Générez-le d'abord.",
        "Open Asset": "Ouvrir l'immobilisation",
        "Fixed asset created.": "Immobilisation créée.",
        "Depreciation schedule generated.": "Plan d'amortissement généré.",
        "Depreciation posted as {voucher}.": "Amortissement validé sous {voucher}.",
        "STRAIGHT_LINE": "Linéaire",
        "DECLINING_BALANCE": "Dégressif",
        "ACTIVE": "Actif",
        "FULLY_DEPRECIATED": "Totalement amorti",
        "DISPOSED": "Cédé",
        "SCHEDULED": "Planifié",
        "POSTED": "Validé",
        "SKIPPED": "Ignoré",
        "Acquisition cost must be greater than zero.": "Le coût d'acquisition doit être supérieur à zéro.",
        "Residual value cannot be negative.": "La valeur résiduelle ne peut pas être négative.",
        "Residual value must be less than acquisition cost.": "La valeur résiduelle doit être inférieure au coût d'acquisition.",
        "Useful life must be at least one month.": "La durée de vie doit être d'au moins un mois.",
        "In-service date cannot precede acquisition date.": "La date de mise en service ne peut pas précéder la date d'acquisition.",
        "Declining balance method requires a positive annual rate.": "La méthode dégressive exige un taux annuel positif.",
        "Asset account must be a Class 2 account.": "Le compte d'immobilisation doit être un compte de Classe 2.",
        "Depreciation expense account must be a postable Class 6 account.": "Le compte de dotation doit être un compte de Classe 6 mouvementable.",
        "Accumulated depreciation account must be a postable Class 2 account.": "Le compte d'amortissement cumulé doit être un compte de Classe 2 mouvementable.",
        "Cannot generate depreciation: accounting period is not OPEN.": "Impossible de générer l'amortissement : la période comptable n'est pas OUVERTE.",
        "Cannot generate depreciation: fiscal year is not OPEN.": "Impossible de générer l'amortissement : l'exercice n'est pas OUVERT.",
        "Cannot post depreciation: accounting period is not OPEN.": "Impossible de valider l'amortissement : la période comptable n'est pas OUVERTE.",
        "Cannot post depreciation: fiscal year is not OPEN.": "Impossible de valider l'amortissement : l'exercice n'est pas OUVERT.",
        "Depreciation journal 'AMOR' is missing. Run migrations.": "Le journal d'amortissement 'AMOR' est manquant. Exécutez les migrations.",
        "No scheduled depreciation lines to post for this period.": "Aucune ligne d'amortissement planifiée à valider pour cette période.",
        "Depreciation total is zero; nothing to post.": "Le total d'amortissement est nul ; rien à valider.",
    },
    "en": {
        "Fixed Assets": "Fixed Assets",
        "New Fixed Asset": "New Fixed Asset",
        "No fixed assets found.": "No fixed assets found.",
        "Search by code or label": "Search by code or label",
        "In Service": "In Service",
        "Acquisition Cost": "Acquisition Cost",
        "Method": "Method",
        "Monthly Depreciation": "Monthly Depreciation",
        "Generate Schedule": "Generate Schedule",
        "Post Depreciation": "Post Depreciation",
        "View Schedule": "View Schedule",
        "Post depreciation for this period?": "Post depreciation for this period?",
        "Acquisition Date": "Acquisition Date",
        "In Service Date": "In Service Date",
        "Acquisition Cost (XAF)": "Acquisition Cost (XAF)",
        "Residual Value (XAF)": "Residual Value (XAF)",
        "Useful Life (months)": "Useful Life (months)",
        "Declining Rate (% annual)": "Declining Rate (% annual)",
        "Asset Account": "Asset Account",
        "Depreciation Expense Account": "Depreciation Expense Account",
        "Accumulated Depreciation Account": "Accumulated Depreciation Account",
        "Save Asset": "Save Asset",
        "Back to Assets": "Back to Assets",
        "Accumulated Depreciation": "Accumulated Depreciation",
        "Net Book Value": "Net Book Value",
        "Useful Life": "Useful Life",
        "months": "months",
        "Expense Account": "Expense Account",
        "Accumulated Account": "Accumulated Account",
        "No depreciation schedule yet.": "No depreciation schedule yet.",
        "Depreciation Schedule": "Depreciation Schedule",
        "Asset": "Asset",
        "Proposed": "Proposed",
        "Amount": "Amount",
        "Journal Entry": "Journal Entry",
        "No schedule for this period. Generate it first.": "No schedule for this period. Generate it first.",
        "Open Asset": "Open Asset",
        "Fixed asset created.": "Fixed asset created.",
        "Depreciation schedule generated.": "Depreciation schedule generated.",
        "Depreciation posted as {voucher}.": "Depreciation posted as {voucher}.",
        "STRAIGHT_LINE": "Straight-Line",
        "DECLINING_BALANCE": "Declining Balance",
        "ACTIVE": "Active",
        "FULLY_DEPRECIATED": "Fully Depreciated",
        "DISPOSED": "Disposed",
        "SCHEDULED": "Scheduled",
        "POSTED": "Posted",
        "SKIPPED": "Skipped",
        "Acquisition cost must be greater than zero.": "Acquisition cost must be greater than zero.",
        "Residual value cannot be negative.": "Residual value cannot be negative.",
        "Residual value must be less than acquisition cost.": "Residual value must be less than acquisition cost.",
        "Useful life must be at least one month.": "Useful life must be at least one month.",
        "In-service date cannot precede acquisition date.": "In-service date cannot precede acquisition date.",
        "Declining balance method requires a positive annual rate.": "Declining balance method requires a positive annual rate.",
        "Asset account must be a Class 2 account.": "Asset account must be a Class 2 account.",
        "Depreciation expense account must be a postable Class 6 account.": "Depreciation expense account must be a postable Class 6 account.",
        "Accumulated depreciation account must be a postable Class 2 account.": "Accumulated depreciation account must be a postable Class 2 account.",
        "Cannot generate depreciation: accounting period is not OPEN.": "Cannot generate depreciation: accounting period is not OPEN.",
        "Cannot generate depreciation: fiscal year is not OPEN.": "Cannot generate depreciation: fiscal year is not OPEN.",
        "Cannot post depreciation: accounting period is not OPEN.": "Cannot post depreciation: accounting period is not OPEN.",
        "Cannot post depreciation: fiscal year is not OPEN.": "Cannot post depreciation: fiscal year is not OPEN.",
        "Depreciation journal 'AMOR' is missing. Run migrations.": "Depreciation journal 'AMOR' is missing. Run migrations.",
        "No scheduled depreciation lines to post for this period.": "No scheduled depreciation lines to post for this period.",
        "Depreciation total is zero; nothing to post.": "Depreciation total is zero; nothing to post.",
    },
}


def run() -> None:
    for locale, entries in ENTRIES.items():
        po_path = LOCALES_DIR / locale / "LC_MESSAGES" / "messages.po"
        mo_path = LOCALES_DIR / locale / "LC_MESSAGES" / "messages.mo"

        with po_path.open("rb") as f:
            catalog = read_po(f, locale=locale, domain="messages")

        added = 0
        for msgid, msgstr in entries.items():
            if msgid not in catalog:
                catalog.add(msgid, string=msgstr)
                added += 1

        with po_path.open("wb") as f:
            write_po(f, catalog, width=76)

        with mo_path.open("wb") as f:
            write_mo(f, catalog)

        print(f"[{locale}] added {added} entries, compiled {mo_path}")


if __name__ == "__main__":
    run()