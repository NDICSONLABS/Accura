from decimal import Decimal

from app.services.statements_service import CompteResultat, StatementRow
from app.services.export_service import (
    export_compte_resultat_to_excel,
    export_compte_resultat_to_pdf,
)


def test_compte_resultat_excel_export():
    data = CompteResultat(
        charges=[
            StatementRow(account_code="601", account_label="Achats", amount=Decimal("200000"))
        ],
        produits=[
            StatementRow(account_code="701", account_label="Dons", amount=Decimal("500000"))
        ],
        total_charges=Decimal("200000"),
        total_produits=Decimal("500000"),
        resultat=Decimal("300000"),
    )

    buffer = export_compte_resultat_to_excel(data)
    content = buffer.getvalue()

    assert content.startswith(b"PK")  # XLSX files are ZIP containers


def test_compte_resultat_pdf_export_reportlab():
    data = CompteResultat(
        charges=[
            StatementRow(account_code="601", account_label="Achats", amount=Decimal("200000"))
        ],
        produits=[
            StatementRow(account_code="701", account_label="Dons", amount=Decimal("500000"))
        ],
        total_charges=Decimal("200000"),
        total_produits=Decimal("500000"),
        resultat=Decimal("300000"),
    )

    buffer = export_compte_resultat_to_pdf(data)
    content = buffer.getvalue()

    assert content.startswith(b"%PDF")