from flask import render_template, request, flash, redirect, url_for
from bokforing_app.main import bp
from bokforing_app.models import Company
from bokforing_app import db
from bokforing_app.services.accounting_config import KONTOPLAN, ASSOCIATION_MAP
import bokforing_app.services.booking_service as booking_service


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
            flash(f"Företag '{new_company.name}' skapat.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Fel vid skapande av företag: {e}", "danger")
        return redirect(url_for('main.index'))

    companies = Company.query.all()
    return render_template('companies.html', companies=companies)


@bp.route('/company/<int:company_id>', methods=['GET'])
def bokforing_page(company_id):
    company = Company.query.get_or_404(company_id)
    # Anropa Service Layer
    transactions, unassigned_bilagor = booking_service.get_company_data(company_id)

    return render_template(
        'transactions.html',
        company=company,
        transactions=transactions,
        unassigned_bilagor=unassigned_bilagor,
        kontoplan=KONTOPLAN,
        association_map=ASSOCIATION_MAP
    )


@bp.route('/company/<int:company_id>/verifikationer', methods=['GET'])
def verifikationer_page(company_id):
    company = Company.query.get_or_404(company_id)
    # Anropa Service Layer
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
    # Anropa Service Layer
    all_bilagor = booking_service.get_all_bilagor(company_id)

    return render_template(
        'bilagor.html',
        company=company,
        all_bilagor=all_bilagor,
        kontoplan=KONTOPLAN,
        association_map=ASSOCIATION_MAP
    )