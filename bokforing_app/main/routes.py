from flask import render_template, request, flash, redirect, url_for
from bokforing_app.main import bp
from bokforing_app.models import Company, BankTransaction, BookkeepingEntry
from bokforing_app import db
from bokforing_app.services.accounting_config import KONTOPLAN, ASSOCIATION_MAP
import bokforing_app.services.booking_service as booking_service
from datetime import datetime
from sqlalchemy import extract

@bp.route('/', methods=['GET', 'POST'])
def index():
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
    company = Company.query.get_or_404(company_id)
    
    # Hämta transaktioner för de olika sektionerna
    unprocessed_transactions = BankTransaction.query.filter_by(
        company_id=company_id,
        status='unprocessed'
    ).order_by(BankTransaction.bokforingsdag.desc()).all()

    pending_duplicates = BankTransaction.query.filter_by(
        company_id=company_id,
        status='pending_duplicate'
    ).order_by(BankTransaction.bokforingsdag.desc()).all()

    unassigned_bilagor = booking_service.get_all_bilagor(company_id)

    return render_template(
        'transactions.html',
        company=company,
        transactions=unprocessed_transactions,
        pending_duplicates=pending_duplicates,
        unassigned_bilagor=unassigned_bilagor,
        kontoplan=KONTOPLAN,
        association_map=ASSOCIATION_MAP
    )


@bp.route('/company/<int:company_id>/verifikationer', methods=['GET'])
def verifikationer_page(company_id):
    company = Company.query.get_or_404(company_id)
    transactions = booking_service.get_verifikationer(company_id)

    return render_template(
        'verifikationer.html',
        company=company,
        transactions=transactions,
        kontoplan=KONTOPLAN,
        association_map=ASSOCIATION_MAP
    )


@bp.route('/company/<int:company_id>/bilagor', methods=['GET'])
def bilagor_page(company_id):
    company = Company.query.get_or_404(company_id)
    all_bilagor = booking_service.get_all_bilagor(company_id)

    return render_template(
        'bilagor.html',
        company=company,
        all_bilagor=all_bilagor,
        kontoplan=KONTOPLAN,
        association_map=ASSOCIATION_MAP
    )

@bp.route('/company/<int:company_id>/momsrapport', methods=['GET'])
def momsrapport_page(company_id):
    company = Company.query.get_or_404(company_id)
    
    available_years = db.session.query(extract('year', BankTransaction.bokforingsdag)).distinct().order_by(extract('year', BankTransaction.bokforingsdag).desc()).all()
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
        moms_data[desc] = {'utgaende': 0, 'ingende': 0}

    for trans in transactions:
        for entry in trans.entries:
            if entry.konto in moms_konton:
                desc = moms_konton[entry.konto]
                if entry.konto.startswith('261'):
                    moms_data[desc]['utgaende'] += entry.kredit
                    total_utgaende += entry.kredit
                elif entry.konto.startswith('264'):
                    moms_data[desc]['ingende'] += entry.debet
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
        report_period=report_period
    )


@bp.route('/ai_settings_page', methods=['GET'])
def ai_settings_page():
    """Sidan för att hantera AI-inställningar."""
    return render_template('ai_settings.html', kontoplan=KONTOPLAN)
