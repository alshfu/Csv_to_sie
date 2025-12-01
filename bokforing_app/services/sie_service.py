import codecs
from datetime import datetime
from bokforing_app.models import Company, BankTransaction, Konto
from bokforing_app import db


def generate_sie_content(company_id):
    company = Company.query.get_or_404(company_id)
    transactions = BankTransaction.query.filter_by(
        company_id=company_id,
        status='processed'
    ).order_by(BankTransaction.bokforingsdag).all()

    if not transactions:
        return None, "Inga bokförda transaktioner att exportera."

    all_dates = [t.bokforingsdag for t in transactions]
    min_date = min(all_dates)
    
    financial_year_start = datetime(min_date.year, 1, 1)
    financial_year_end = datetime(min_date.year, 12, 31)

    used_konto_nrs = set()
    for trans in transactions:
        for entry in trans.entries:
            used_konto_nrs.add(entry.konto)

    konto_descriptions = {k.konto_nr: k.beskrivning for k in Konto.query.filter(Konto.konto_nr.in_(used_konto_nrs)).all()}

    sie_lines = []

    sie_lines.append('#FLAGGA 0')
    sie_lines.append(f'#PROGRAM "Csv-to-Sie App" 1.0')
    sie_lines.append('#FORMAT PC8')
    sie_lines.append(f'#GEN {datetime.now().strftime("%Y%m%d")} "CsvToSie"')
    sie_lines.append('#SIETYP 4')
    sie_lines.append(f'#FNAMN "{company.name}"')
    sie_lines.append(f'#ORGNR {company.org_nummer}')
    address_line = f'#ADRESS "{company.gata}" "" "{company.postkod} {company.ort}" ""'
    sie_lines.append(address_line)
    sie_lines.append(f'#RAR 0 {financial_year_start.strftime("%Y%m%d")} {financial_year_end.strftime("%Y%m%d")}')
    sie_lines.append('#VALUTA SEK')
    sie_lines.append('#KPTYP BAS95')

    for konto_nr in sorted(list(used_konto_nrs)):
        konto_namn = konto_descriptions.get(konto_nr, f"Okänt konto {konto_nr}")
        sie_lines.append(f'#KONTO {konto_nr} "{konto_namn}"')

    ver_nr_counter = 1
    for trans in transactions:
        ver_date = trans.bokforingsdag.strftime('%Y%m%d')
        ver_text = trans.referens.replace('"', "'").strip() if trans.referens else f"Transaktion {trans.id}"
        if not ver_text: ver_text = f"Transaktion {trans.id}"

        sie_lines.append(f'#VER "A" {ver_nr_counter} {ver_date} "{ver_text}" {{')
        
        for entry in trans.entries:
            belopp = entry.debet if entry.debet > 0 else -entry.kredit
            formatted_belopp = f"{belopp:.2f}".replace(',', '.')
            trans_text = ver_text
            sie_lines.append(f'#TRANS {entry.konto} {{}} {formatted_belopp} "{trans_text}"')
        
        sie_lines.append('}')
        ver_nr_counter += 1

    sie_content_str = "\n".join(sie_lines)
    
    try:
        encoded_content = codecs.encode(sie_content_str, 'cp437')
        return encoded_content, None
    except UnicodeEncodeError as e:
        return None, f"Fel vid kodning av SIE-fil (ogiltigt tecken): {e}. Kontrollera referenstexter för ovanliga tecken."
