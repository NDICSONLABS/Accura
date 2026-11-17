from pathlib import Path
from babel.messages.pofile import read_po, write_po
from babel.messages.mofile import write_mo

LOCALES_DIR = Path(__file__).resolve().parent / "app" / "locales"

FR = {
    "Closing Engine": "Moteur de clôture",
    "Closing Checklist": "Checklist de clôture",
    "Ready to close.": "Prêt à clôturer.",
    "Soft Lock": "Verrouiller",
    "FX Revaluation": "Réévaluation FX",
    "Close Fiscal Year": "Clôturer l'exercice",
    "Open Next Year": "Ouvrir l'exercice suivant",
    "Carry Forward Result": "Affecter le résultat",
    "Close this fiscal year? This cannot be undone.": "Clôturer cet exercice ? Cette action est irréversible.",
    "FX Revaluations": "Réévaluations FX",
    "As Of": "Au",
    "Latent Loss": "Perte latente",
    "Latent Gain": "Gain latent",
    "Reversed": "Contre-passée",
    "Open": "Ouvrir",
    "No revaluations yet.": "Aucune réévaluation.",
    "Closing Rates": "Taux de clôture",
    "Latent Loss Provision (optional)": "Provision pour perte latente (facultatif)",
    "OHADA requires provisioning latent exchange losses. Supply the policy accounts to post the provision.": "L'OHADA exige une provision pour pertes de change latentes. Indiquez les comptes de politique comptable pour comptabiliser la provision.",
    "Provision Expense (Class 6)": "Charge de provision (Classe 6)",
    "Provision Account (Class 1)": "Compte de provision (Classe 1)",
    "Open Exposures": "Positions ouvertes",
    "Foreign Balance": "Solde en devise",
    "Historical XAF": "Contre-valeur historique",
    "No foreign currency exposure at this date.": "Aucune position en devise à cette date.",
    "Run Revaluation": "Lancer la réévaluation",
    "Latent exchange loss is not provisioned. OHADA requires a provision for latent losses.": "La perte de change latente n'est pas provisionnée. L'OHADA exige une provision.",
    "Historical": "Historique",
    "Revalued": "Réévalué",
    "Direction": "Sens",
    "Reverse Revaluation": "Contre-passer la réévaluation",
    "View Reversal": "Voir la contre-passation",
    "Open Revaluation": "Ouvrir la réévaluation",
    "Open Result Entry": "Ouvrir l'écriture de résultat",
    "Refresh Dashboard": "Rafraîchir",
    "Result": "Résultat",
    "LOSS": "Perte",
    "GAIN": "Gain",
    "SOFT_LOCKED": "Verrouillée",
    "Period soft-locked.": "Période verrouillée.",
    "FX revaluation posted.": "Réévaluation FX validée.",
    "FX revaluation reversed.": "Réévaluation FX contre-passée.",
    "Fiscal year closed.": "Exercice clôturé.",
    "Next fiscal year opened.": "Exercice suivant ouvert.",
    "Result carried forward.": "Résultat affecté.",
    "Period is already permanently closed.": "La période est déjà définitivement clôturée.",
    "Revaluation period must be OPEN.": "La période de réévaluation doit être OUVERTE.",
    "A previous FX revaluation must be reversed before running a new one.": "Une réévaluation précédente doit être contre-passée avant d'en lancer une nouvelle.",
    "At least one closing rate is required.": "Au moins un taux de clôture est requis.",
    "No foreign currency exposure requires revaluation at these rates.": "Aucune position en devise ne nécessite de réévaluation à ces taux.",
    "Closing journal 'CLOT' is missing. Run migrations.": "Le journal de clôture 'CLOT' est manquant. Exécutez les migrations.",
    "Translation accounts 478 / 479 are missing. Run migrations.": "Les comptes d'écart de conversion 478 / 479 sont manquants. Exécutez les migrations.",
    "Provisioning requires both an expense account and a provision account.": "La provision exige un compte de charge et un compte de provision.",
    "Provision expense account must be a postable Class 6 account.": "Le compte de charge de provision doit être un compte de Classe 6 mouvementable.",
    "Provision account must be a postable Class 1 account.": "Le compte de provision doit être un compte de Classe 1 mouvementable.",
    "Revaluation run not found.": "Réévaluation introuvable.",
    "Only POSTED revaluations can be reversed.": "Seules les réévaluations VALIDÉES peuvent être contre-passées.",
    "This revaluation has already been reversed.": "Cette réévaluation a déjà été contre-passée.",
    "Fiscal year has no accounting periods.": "L'exercice n'a aucune période comptable.",
    "Fiscal year is already CLOSED.": "L'exercice est déjà CLÔTURÉ.",
    "All periods except the last must be soft-locked or closed.": "Toutes les périodes sauf la dernière doivent être verrouillées ou clôturées.",
    "The last period must be OPEN to receive the result entry.": "La dernière période doit être OUVERTE pour recevoir l'écriture de résultat.",
    "Trial balance is not balanced.": "La balance générale n'est pas équilibrée.",
    "Fiscal year is already closed.": "L'exercice est déjà clôturé.",
    "Result account 131 must be postable. Run migrations.": "Le compte de résultat 131 doit être mouvementable. Exécutez les migrations.",
    "No management balances to close for this fiscal year.": "Aucun solde de gestion à clôturer pour cet exercice.",
    "Fiscal year code must be numeric to derive the next year.": "Le code d'exercice doit être numérique pour déduire l'année suivante.",
    "Fiscal year has not been closed yet.": "L'exercice n'est pas encore clôturé.",
    "Result has already been carried forward.": "Le résultat a déjà été affecté.",
    "Open the next fiscal year before carrying forward the result.": "Ouvrez l'exercice suivant avant d'affecter le résultat.",
    "The next fiscal year has no OPEN period.": "L'exercice suivant n'a aucune période OUVERTE.",
    "Retained earnings account 121 must be postable. Run migrations.": "Le compte de report à nouveau 121 doit être mouvementable. Exécutez les migrations.",
    "Result is zero; nothing to carry forward.": "Le résultat est nul ; rien à affecter.",
}
EN = {k: k for k in FR}
EN.update({"SOFT_LOCKED": "Soft Locked", "LOSS": "Loss", "GAIN": "Gain"})


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