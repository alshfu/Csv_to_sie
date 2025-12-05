# -*- coding: utf-8 -*-
"""
Definierar huvud-routes för applikationen som renderar HTML-sidor.

Denna modul hanterar all logik för att visa de olika sidorna i webbgränssnittet,
som att hämta data från databasen och skicka den till Jinja2-mallarna för rendering.
"""
from flask import render_template, request, flash, redirect, url_for, Response, current_app, jsonify
from bokforing_app.main import bp
from bokforing_app.models import Company, BankTransaction, BookkeepingEntry, Invoice, InvoiceRow, Client, Bilaga, \
    Matchning
from bokforing_app import db
from bokforing_app.services.accounting_config import KONTOPLAN, ASSOCIATION_MAP
import bokforing_app.services.booking_service as booking_service
import bokforing_app.services.fakturanu_service as fakturanu_service
from datetime import datetime, timedelta
from sqlalchemy import extract, func, and_
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time


@bp.route('/', methods=['GET', 'POST'])
def index():
    """
    Visar startsidan med en lista över alla företag och ett formulär för att skapa ett nytt.
    """
    if request.method == 'POST':
        try:
            new_company = Company(
                name=request.form['name'],
                org_nummer=request.form['org_nummer'],
                gata=request.form['gata'],
                postkod=request.form['postkod'],
                ort=request.form['ort']
            )
            db.session.add(new_company)
            db.session.commit()
            flash(f"Företag '{new_company.name}' har skapats.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Fel vid skapande av företag: {e}", "danger")
        return redirect(url_for('main.index'))

    companies = Company.query.all()
    return render_template('companies.html', companies=companies)


@bp.route('/company/<int:company_id>', methods=['GET'])
def bokforing_page(company_id):
    """
    Visar huvudsidan för bokföring för ett specifikt företag.
    Hämtar och visar obearbetade transaktioner och potentiella dubbletter.
    """
    company = Company.query.get_or_404(company_id)

    unprocessed_transactions = BankTransaction.query.filter_by(
        company_id=company_id,
        status='unprocessed'
    ).order_by(BankTransaction.bokforingsdag.desc()).all()

    pending_duplicates = BankTransaction.query.filter_by(
        company_id=company_id,
        status='pending_duplicate'
    ).order_by(BankTransaction.bokforingsdag.desc()).all()

    return render_template(
        'transactions.html',
        company=company,
        transactions=unprocessed_transactions,
        pending_duplicates=pending_duplicates,
        kontoplan=KONTOPLAN
    )


@bp.route('/company/<int:company_id>/matcha', methods=['GET'])
def matcha_page(company_id):
    """
    Visar den nya matchningssidan med tre kolumner:
    1. Transaktioner med kvarvarande belopp att matcha.
    2. Fakturor med kvarvarande belopp att betala.
    3. Bilagor med kvarvarande belopp att betala.
    """
    company = Company.query.get_or_404(company_id)

    # Subquery för att summera matchade belopp per transaktion
    subquery_trans = db.session.query(
        Matchning.transaction_id,
        func.sum(Matchning.amount).label('total_matched')
    ).group_by(Matchning.transaction_id).subquery()

    # Hämta transaktioner där matchat belopp är mindre än transaktionens belopp
    unmatched_transactions = db.session.query(
        BankTransaction,
        (BankTransaction.belopp - func.coalesce(subquery_trans.c.total_matched, 0)).label('remaining_amount')
    ).outerjoin(subquery_trans, BankTransaction.id == subquery_trans.c.transaction_id).filter(
        BankTransaction.company_id == company_id,
        func.coalesce(subquery_trans.c.total_matched, 0) < BankTransaction.belopp
    ).all()

    # Subquery för att summera matchade belopp per faktura
    subquery_inv = db.session.query(
        Matchning.invoice_id,
        func.sum(Matchning.amount).label('total_matched')
    ).group_by(Matchning.invoice_id).subquery()

    # Hämta fakturor där matchat belopp är mindre än fakturans summa
    unpaid_invoices = db.session.query(
        Invoice,
        (Invoice.sum - func.coalesce(subquery_inv.c.total_matched, 0)).label('remaining_amount')
    ).outerjoin(subquery_inv, Invoice.id == subquery_inv.c.invoice_id).filter(
        Invoice.company_id == company_id,
        func.coalesce(subquery_inv.c.total_matched, 0) < Invoice.sum
    ).all()

    # Subquery för att summera matchade belopp per bilaga
    subquery_bil = db.session.query(
        Matchning.bilaga_id,
        func.sum(Matchning.amount).label('total_matched')
    ).group_by(Matchning.bilaga_id).subquery()

    # Hämta bilagor där matchat belopp är mindre än bilagans summa
    unpaid_bilagor = db.session.query(
        Bilaga,
        (Bilaga.brutto_amount - func.coalesce(subquery_bil.c.total_matched, 0)).label('remaining_amount')
    ).outerjoin(subquery_bil, Bilaga.id == subquery_bil.c.bilaga_id).filter(
        Bilaga.company_id == company_id,
        Bilaga.brutto_amount != None,
        func.coalesce(subquery_bil.c.total_matched, 0) < Bilaga.brutto_amount
    ).all()

    return render_template(
        'matcha.html',
        company=company,
        unmatched_transactions=unmatched_transactions,
        unpaid_invoices=unpaid_invoices,
        unpaid_bilagor=unpaid_bilagor
    )


@bp.route('/company/<int:company_id>/profile', methods=['GET', 'POST'])
def company_profile(company_id):
    """Visar och hanterar uppdatering av företagets profil och inställningar."""
    company = Company.query.get_or_404(company_id)
    if request.method == 'POST':
        try:
            company.name = request.form['name']
            company.org_nummer = request.form['org_nummer']
            company.gata = request.form['gata']
            company.postkod = request.form['postkod']
            company.ort = request.form['ort']
            company.accounting_method = request.form['accounting_method']
            company.fakturanu_key_id = request.form['fakturanu_key_id']
            company.fakturanu_password = request.form['fakturanu_password']
            db.session.commit()
            flash('Företagsprofilen har uppdaterats.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Ett fel inträffade: {e}', 'danger')
        return redirect(url_for('main.company_profile', company_id=company.id))

    return render_template('company_profile.html', company=company)


@bp.route('/company/<int:company_id>/invoices', methods=['GET'])
def invoices(company_id):
    """Visar en lista över obokförda kundfakturor."""
    company = Company.query.get_or_404(company_id)
    unbooked_invoices = Invoice.query.filter_by(company_id=company_id).filter(~Invoice.transactions.any()).order_by(
        Invoice.date.desc()).all()
    return render_template('invoices.html', company=company, invoices=unbooked_invoices, KONTOPLAN=KONTOPLAN)


@bp.route('/company/<int:company_id>/invoices/sync', methods=['GET'])
def sync_invoices(company_id):
    """Synkroniserar fakturor från Fakturan.nu till den lokala databasen."""
    company = Company.query.get_or_404(company_id)

    if not company.fakturanu_key_id or not company.fakturanu_password:
        flash("API-nycklar för Faktura.nu saknas. Vänligen lägg till dem i företagsprofilen.", "danger")
        return redirect(url_for('main.invoices', company_id=company.id))

    # Hämta senaste ändringsdatum från databasen för att bara hämta nya/ändrade fakturor
    last_updated_invoice = Invoice.query.filter_by(company_id=company_id).order_by(Invoice.updated_at.desc()).first()
    modified_since = last_updated_invoice.updated_at.strftime('%Y-%m-%d %H:%M:%S') if last_updated_invoice else None

    params = {}
    if modified_since:
        # Använd 'start_date' från API-dokumentationen istället för 'modified_since' (som inte stöds)
        params['start_date'] = modified_since.split(' ')[0]  # Använd endast datum för filter

    list_result = fakturanu_service.get_invoices(company.fakturanu_key_id, company.fakturanu_password, params=params)

    if 'error' in list_result:
        flash(f"Synkronisering misslyckades: {list_result['error']}", "danger")
        return redirect(url_for('main.invoices', company_id=company.id))

    # Uppdaterad parsning: Använd 'invoices' istället för 'data' enligt get_invoices-struktur
    api_invoices_list = list_result.get('invoices', [])
    current_app.logger.info(f"Hämtade {len(api_invoices_list)} fakturor från API.")

    new_invoices = 0
    updated_invoices = 0
    new_clients = 0

    for api_invoice in api_invoices_list:
        fakturanu_id = api_invoice['id']
        current_app.logger.debug(f"Behandlar faktura {fakturanu_id}.")

        client_id = api_invoice.get('client_id')
        client = None
        if client_id:
            client = Client.query.filter_by(fakturanu_id=client_id, company_id=company.id).first()
            if not client:
                client_details_result = fakturanu_service.get_client_details(company.fakturanu_key_id,
                                                                             company.fakturanu_password, client_id)
                if 'data' in client_details_result:
                    client_data = client_details_result['data']
                    client = Client(
                        fakturanu_id=client_id,
                        company_id=company.id,
                        name=client_data.get('name'),
                        org_number=client_data.get('org_number'),
                        email=client_data.get('email'),
                        phone=client_data.get('phone'),
                        street_address=client_data.get('address', {}).get('street_address'),
                        zip_code=client_data.get('address', {}).get('zip_code'),
                        city=client_data.get('address', {}).get('city'),
                        country=client_data.get('address', {}).get('country')
                    )
                    db.session.add(client)
                    new_clients += 1
                    current_app.logger.debug(f"Skapade ny klient {client_id}.")

        if not client:
            current_app.logger.warning(f"Kunde inte hitta eller skapa klient för faktura {fakturanu_id}. Hoppar över.")
            continue

        invoice = Invoice.query.filter_by(fakturanu_id=fakturanu_id).first()
        status = 'betald' if api_invoice.get('paid_at') else 'skickad' if api_invoice.get('sent') else 'utkast'

        if not invoice:
            invoice = Invoice(fakturanu_id=fakturanu_id, company_id=company.id)
            new_invoices += 1
            current_app.logger.debug(f"Skapade ny faktura {fakturanu_id}.")
        elif invoice.status != status:
            updated_invoices += 1
            current_app.logger.debug(f"Uppdaterade faktura {fakturanu_id} på grund av statusändring.")

        invoice.client = client
        invoice.number = api_invoice.get('number')
        invoice.our_reference = api_invoice.get('our_reference')
        invoice.your_reference = api_invoice.get('your_reference')
        invoice.locale = api_invoice.get('locale')
        invoice.currency = api_invoice.get('currency')
        invoice.sum = float(api_invoice.get('sum', 0.0))
        invoice.net = float(api_invoice.get('net', 0.0))
        invoice.tax = float(api_invoice.get('tax', 0.0))
        invoice.status = status
        invoice.reverse_charge = api_invoice.get('reverse_charge', False)
        invoice.date = datetime.strptime(api_invoice['date'], '%Y-%m-%d').date() if api_invoice.get('date') else None
        invoice.paid_at = datetime.strptime(api_invoice['paid_at'], '%Y-%m-%d').date() if api_invoice.get(
            'paid_at') else None

        if invoice.date:
            days_to_due = api_invoice.get('days', 30)
            invoice.due_date = invoice.date + timedelta(days=days_to_due)

        # Uppdatera rader (rows)
        InvoiceRow.query.filter_by(invoice_id=invoice.id).delete()
        for row_data in api_invoice.get('rows', []):
            new_row = InvoiceRow(
                invoice=invoice,
                product_id=row_data.get('product_id'),
                product_code=row_data.get('product_code'),
                product_name=row_data.get('product_name'),
                product_unit=row_data.get('product_unit'),
                discount=float(row_data.get('discount', 0.0)),
                amount=float(row_data.get('amount', 0.0)),
                price=float(row_data.get('product_price', 0.0)),
                tax_rate=int(row_data.get('product_tax', 0))
            )
            db.session.add(new_row)

        db.session.add(invoice)
        current_app.logger.debug(f"Lade till/ uppdaterade faktura {fakturanu_id} i sessionen.")

    db.session.commit()
    current_app.logger.info(
        f"Synkronisering slutförd: {new_invoices} nya fakturor, {updated_invoices} uppdaterade, {new_clients} nya klienter.")
    flash(
        f'{new_invoices} nya fakturor, {updated_invoices} uppdaterade fakturor och {new_clients} nya klienter synkroniserades.',
        'success')

    return redirect(url_for('main.invoices', company_id=company.id))


@bp.route('/api/invoice/<int:invoice_id>/toggle_reverse_charge', methods=['POST'])
def toggle_reverse_charge(invoice_id):
    """Växlar status för omvänd skattskyldighet för en faktura."""
    invoice = Invoice.query.get_or_404(invoice_id)
    data = request.get_json()
    new_status = data.get('reverse_charge')

    if isinstance(new_status, bool):
        invoice.reverse_charge = new_status
        db.session.commit()
        current_app.logger.info(f"Uppdaterade 'reverse_charge' till {new_status} för faktura {invoice.id}.")
        return jsonify({'success': True, 'reverse_charge': invoice.reverse_charge})

    return jsonify({'error': 'Ogiltig status skickad.'}), 400


@bp.route('/company/<int:company_id>/verifikationer', methods=['GET'])
def verifikationer_page(company_id):
    """Visar en lista över alla bokförda verifikationer för ett företag."""
    company = Company.query.get_or_404(company_id)
    transactions = booking_service.get_verifikationer(company_id)
    return render_template(
        'verifikationer.html',
        company=company,
        transactions=transactions,
        kontoplan=KONTOPLAN
    )


@bp.route('/company/<int:company_id>/bilagor', methods=['GET'])
def bilagor_page(company_id):
    """Visar en sida med alla uppladdade bilagor för ett företag."""
    company = Company.query.get_or_404(company_id)
    all_bilagor = booking_service.get_all_bilagor(company_id)
    return render_template(
        'bilagor.html',
        company=company,
        all_bilagor=all_bilagor,
        kontoplan=KONTOPLAN
    )


@bp.route('/company/<int:company_id>/momsrapport', methods=['GET'])
def momsrapport_page(company_id):
    """Genererar och visar en momsrapport för en vald period."""
    company = Company.query.get_or_404(company_id)

    available_years = db.session.query(extract('year', BankTransaction.bokforingsdag)).distinct().order_by(
        extract('year', BankTransaction.bokforingsdag).desc()).all()
    available_years = [y[0] for y in available_years if y[0] is not None]

    selected_year = request.args.get('year', str(datetime.now().year) if available_years else '', type=int)
    selected_quarter = request.args.get('quarter', '')
    selected_month = request.args.get('month', '')

    query = BankTransaction.query.filter_by(company_id=company_id, status='processed')

    report_period = str(selected_year)
    if selected_year:
        query = query.filter(extract('year', BankTransaction.bokforingsdag) == selected_year)

    if selected_quarter:
        report_period += f" Kvartal {selected_quarter}"
        start_month = (int(selected_quarter) - 1) * 3 + 1
        end_month = start_month + 2
        query = query.filter(extract('month', BankTransaction.bokforingsdag).between(start_month, end_month))
    elif selected_month:
        report_period += f" Månad {selected_month}"
        query = query.filter(extract('month', BankTransaction.bokforingsdag) == int(selected_month))

    transactions = query.all()

    moms_data = {}
    total_utgaende = 0
    total_ingende = 0

    moms_konton = {
        '2611': 'Utgående moms (25%)', '2612': 'Utgående moms (12%)', '2613': 'Utgående moms (6%)',
        '2641': 'Ingående moms (25%)', '2642': 'Ingående moms (12%)', '2643': 'Ingående moms (6%)'
    }

    for konto_nr, desc in moms_konton.items():
        moms_data[konto_nr] = {'description': desc, 'utgaende': 0, 'ingende': 0}

    for trans in transactions:
        for entry in trans.entries:
            if entry.konto in moms_konton:
                if entry.konto.startswith('261'):
                    moms_data[entry.konto]['utgaende'] += entry.kredit
                    total_utgaende += entry.kredit
                elif entry.konto.startswith('264'):
                    moms_data[entry.konto]['ingende'] += entry.debet
                    total_ingende += entry.debet

    return render_template(
        'momsrapport.html',
        company=company,
        moms_data=moms_data,
        total_utgaende=total_utgaende,
        total_ingende=total_ingende,
        available_years=available_years,
        selected_year=selected_year,
        selected_quarter=selected_quarter,
        selected_month=selected_month,
        report_period=report_period,
        KONTOPLAN=KONTOPLAN
    )


@bp.route('/company/<int:company_id>/momsrapport/export_xml', methods=['GET'])
def export_moms_xml(company_id):
    """Exporterar momsrapporten som en XML-fil för Skatteverket."""
    company = Company.query.get_or_404(company_id)

    selected_year = request.args.get('year', type=int)
    selected_quarter = request.args.get('quarter', '')
    selected_month = request.args.get('month', '')

    query = BookkeepingEntry.query.join(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.status == 'processed'
    )

    period_str = ""
    if selected_year:
        query = query.filter(extract('year', BankTransaction.bokforingsdag) == selected_year)
        period_str = str(selected_year)

    if selected_quarter:
        start_month = (int(selected_quarter) - 1) * 3 + 1
        end_month = start_month + 2
        query = query.filter(extract('month', BankTransaction.bokforingsdag).between(start_month, end_month))
    elif selected_month:
        query = query.filter(extract('month', BankTransaction.bokforingsdag) == int(selected_month))
        period_str += str(selected_month).zfill(2)
    else:
        period_str += "12"

    entries = query.all()

    xml_data = {
        'ForsMomsEjAnnan': sum(e.kredit for e in entries if e.konto.startswith('30')),
        'MomsUtgHog': sum(e.kredit for e in entries if e.konto == '2611'),
        'MomsUtgMedel': sum(e.kredit for e in entries if e.konto == '2612'),
        'MomsUtgLag': sum(e.kredit for e in entries if e.konto == '2613'),
        'MomsIngAvdr': sum(e.debet for e in entries if e.konto.startswith('264')),
    }

    total_utg_moms = xml_data.get('MomsUtgHog', 0) + xml_data.get('MomsUtgMedel', 0) + xml_data.get('MomsUtgLag', 0)
    total_ing_moms = xml_data.get('MomsIngAvdr', 0)
    xml_data['MomsBetala'] = total_utg_moms - total_ing_moms

    root = ET.Element('eSKDUpload', Version="6.0")
    ET.SubElement(root, 'OrgNr').text = company.org_nummer
    moms_element = ET.SubElement(root, 'Moms')
    ET.SubElement(moms_element, 'Period').text = period_str

    for key, value in xml_data.items():
        if value != 0:
            ET.SubElement(moms_element, key).text = str(int(value))

    xml_str = ET.tostring(root, 'ISO-8859-1')
    dom = minidom.parseString(xml_str)
    pretty_xml_as_string = dom.toprettyxml(indent="  ", encoding="ISO-8859-1")

    return Response(
        pretty_xml_as_string,
        mimetype='application/xml',
        headers={'Content-Disposition': f'attachment;filename=momsrapport_{company.org_nummer}_{period_str}.xml'}
    )


@bp.route('/ai_settings_page', methods=['GET'])
def ai_settings_page():
    """Visar sidan för AI-inställningar."""
    return render_template('ai_settings.html', kontoplan=KONTOPLAN)
