from pathlib import Path
from babel.messages.pofile import read_po, write_po
from babel.messages.mofile import write_mo

LOCALES_DIR = Path(__file__).resolve().parent / "app" / "locales"

FR = {
    "Donor Grants": "Conventions de financement",
    "New Grant": "Nouvelle convention",
    "Donor": "Bailleur",
    "Committed": "Engagé",
    "No grant agreements found.": "Aucune convention trouvée.",
    "Restricted Fund": "Fonds dédié",
    "Restricted Fund Account": "Compte de fonds dédiés",
    "Committed Amount": "Montant engagé",
    "Start Date": "Date de début",
    "End Date": "Date de fin",
    "Open Grant": "Ouvrir la convention",
    "Back to Grants": "Retour aux conventions",
    "Called": "Appelé",
    "Weighted Rate": "Taux moyen pondéré",
    "Tranches": "Tranches",
    "Activate Grant": "Activer la convention",
    "New Fund Call": "Nouvel appel de fonds",
    "Expected": "Prévu",
    "Number": "Numéro",
    "Add Tranche": "Ajouter une tranche",
    "No tranches yet.": "Aucune tranche.",
    "Fund Calls": "Appels de fonds",
    "No fund calls yet.": "Aucun appel de fonds.",
    "Post": "Valider",
    "Record Receipt": "Enregistrer l'encaissement",
    "Tranche": "Tranche",
    "No tranche link": "Sans lien de tranche",
    "Call Date": "Date d'appel",
    "Grant Receipt": "Encaissement de subvention",
    "Call Rate": "Taux d'appel",
    "Receipt Date": "Date d'encaissement",
    "Receipt Rate": "Taux d'encaissement",
    "Cash Received": "Montant encaissé",
    "Receivable Cleared": "Créance apurée",
    "Budget Maintenance": "Maintenance budgétaire",
    "Add Budget Line": "Ajouter une ligne budgétaire",
    "Approved Amount": "Montant approuvé",
    "Approved": "Approuvé",
    "Consumed": "Consommé",
    "Add": "Ajouter",
    "Update": "Mettre à jour",
    "Delete": "Supprimer",
    "Delete this budget line?": "Supprimer cette ligne budgétaire ?",
    "Back": "Retour",
    "ACTIVE": "Active",
    "CLOSED": "Clôturée",
    "PLANNED": "Planifiée",
    "CALLED": "Appelée",
    "RECEIVED": "Encaissée",
    "PENDING": "En attente",
    "PARTIALLY_RECEIVED": "Partiellement encaissée",
    "Grant agreement created.": "Convention créée.",
    "Tranche added.": "Tranche ajoutée.",
    "Grant activated.": "Convention activée.",
    "Fund call saved as DRAFT.": "Appel de fonds enregistré en brouillon.",
    "Fund call has been POSTED.": "Appel de fonds VALIDÉ.",
    "Receipt saved as DRAFT.": "Encaissement enregistré en brouillon.",
    "Receipt has been POSTED.": "Encaissement VALIDÉ.",
    "Budget line created.": "Ligne budgétaire créée.",
    "Budget line updated.": "Ligne budgétaire mise à jour.",
    "Budget line deleted.": "Ligne budgétaire supprimée.",
    "Grant end date cannot precede start date.": "La date de fin ne peut pas précéder la date de début.",
    "Committed amount cannot be negative.": "Le montant engagé ne peut pas être négatif.",
    "Donor fund tracking is not enabled in organization settings.": "Le suivi par bailleur n'est pas activé dans les paramètres.",
    "Donor (Third Party) not found.": "Bailleur (Tiers) introuvable.",
    "Fund not found.": "Fonds introuvable.",
    "Grant fund must be a restricted fund.": "Le fonds de la convention doit être un fonds dédié.",
    "Grant currency must match the fund currency.": "La devise de la convention doit correspondre à celle du fonds.",
    "Restricted fund account must be a postable Class 1 account.": "Le compte de fonds dédiés doit être un compte de Classe 1 mouvementable.",
    "Receivable account must be a postable account requiring a Third Party.": "Le compte de créance doit être mouvementable et exiger un Tiers.",
    "Grant not found.": "Convention introuvable.",
    "Tranche amount must be positive.": "Le montant de la tranche doit être positif.",
    "Tranche number must be positive.": "Le numéro de tranche doit être positif.",
    "This tranche number already exists for the grant.": "Ce numéro de tranche existe déjà pour la convention.",
    "Grant requires at least one tranche before activation.": "La convention exige au moins une tranche avant activation.",
    "Grant must be ACTIVE before issuing a fund call.": "La convention doit être ACTIVE avant tout appel de fonds.",
    "Fund call amount must be positive.": "Le montant de l'appel doit être positif.",
    "Tranche does not belong to this grant.": "La tranche n'appartient pas à cette convention.",
    "Only PLANNED tranches can be called.": "Seules les tranches PLANIFIÉES peuvent être appelées.",
    "Fund call cannot exceed the tranche amount.": "L'appel de fonds ne peut pas dépasser le montant de la tranche.",
    "Fund call not found.": "Appel de fonds introuvable.",
    "Fund call must be in DRAFT status to post.": "L'appel de fonds doit être en BROUILLON pour être validé.",
    "Grant journal 'SUB' is missing. Run migrations.": "Le journal 'SUB' est manquant. Exécutez les migrations.",
    "Only POSTED fund calls can be received.": "Seuls les appels de fonds VALIDÉS peuvent être encaissés.",
    "Receipt amount must be positive.": "Le montant de l'encaissement doit être positif.",
    "Receipt not found.": "Encaissement introuvable.",
    "Receipt must be in DRAFT status to post.": "L'encaissement doit être en BROUILLON pour être validé.",
    "Approved budget cannot be negative.": "Le budget approuvé ne peut pas être négatif.",
    "Budget account is invalid or not postable.": "Le compte budgétaire est invalide ou non mouvementable.",
    "Budget lines are allowed only on Class 6 (expense) or Class 2 (asset) accounts.": "Les lignes budgétaires ne sont autorisées que sur les comptes de Classe 6 ou 2.",
    "Fiscal year not found.": "Exercice introuvable.",
    "A budget line already exists for this account / fund / project / year.": "Une ligne budgétaire existe déjà pour ce compte / fonds / projet / exercice.",
    "Budget line not found.": "Ligne budgétaire introuvable.",
    "Cannot delete a budget line that already has posted consumption.": "Impossible de supprimer une ligne budgétaire déjà consommée.",
    "Cannot delete a budget line referenced by journal entries.": "Impossible de supprimer une ligne budgétaire référencée par des écritures.",
    "Receipt exceeds outstanding fund call {reference}. Outstanding: {outstanding}": "L'encaissement dépasse le solde de l'appel {reference}. Solde : {outstanding}",
    "Approved budget cannot be reduced below posted consumption. Consumed: {consumed}": "Le budget approuvé ne peut pas être inférieur à la consommation validée. Consommé : {consumed}",
}

EN = {k: k for k in FR}
EN.update({
    "Donor Grants": "Donor Grants",
    "New Grant": "New Grant",
    "Committed": "Committed",
    "Restricted Fund": "Restricted Fund",
    "Weighted Rate": "Weighted Average Rate",
    "Tranches": "Tranches",
    "Fund Calls": "Fund Calls",
    "Grant Receipt": "Grant Receipt",
    "Budget Maintenance": "Budget Maintenance",
    "ACTIVE": "Active",
    "CLOSED": "Closed",
    "PLANNED": "Planned",
    "CALLED": "Called",
    "RECEIVED": "Received",
    "PENDING": "Pending",
    "PARTIALLY_RECEIVED": "Partially Received",
})


def run() -> None:
    for locale, entries in (("fr", FR), ("en", EN)):
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