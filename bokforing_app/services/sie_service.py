from datetime import datetime
from bokforing_app.models import Company, BankTransaction
from bokforing_app.services.accounting_config import KONTOPLAN


def generate_sie_content(company_id):
    company = Company.query.get_or_404(company_id)
    transactions = BankTransaction.query.filter_by(
        company_id=company_id
    ).order_by(BankTransaction.bokforingsdag).all()

    if not transactions:
        return None, "Inga transaktioner att exportera"

    first_date = transactions[0].bokforingsdag
    year_start = first_date.strftime('%Y') + '0101'
    year_end = first_date.strftime('%Y') + '1231'

    konton = set(entry.konto for t in transactions for entry in t.entries)

    sie_data = [
        '#FLAGGA 0',
        '#PROGRAM "CSV-to-SIE App" 1.0',
        '#FORMAT PC8',
        f'#GEN {datetime.now().strftime("%Y%m%d")} "Admin"',
        '#SIETYP 4',
        f'#FNAMN "{company.name}"',
        f'#ORGNR {company.org_nummer}',
        f'#ADRESS "" "{company.gata}" "{company.postkod} {company.ort}" ""',
        f'#RAR 0 {year_start} {year_end}'
    ]

    for konto_nr in sorted(list(konton)):
        konto_namn = KONTOPLAN.get(konto_nr, f"Okänt konto {konto_nr}")
        sie_data.append(f'#KONTO {konto_nr} "{konto_namn}"')

    ver_nr = 1
    for trans in transactions:
        ver_date = trans.bokforingsdag.strftime('%Y%m%d')
        ver_text = str(trans.referens).replace('"', '')

        sie_data.append(f'#VER "B" {ver_nr} {ver_date} "{ver_text}"')
        sie_data.append('{')
        for entry in trans.entries:
            belopp = entry.debet if entry.debet > 0 else -entry.kredit
            if belopp != 0.0:
                sie_data.append(f'#TRANS {entry.konto} {{}} {belopp:.2f}')
        sie_data.append('}')
        ver_nr += 1

    return "\r\n".join(sie_data), None