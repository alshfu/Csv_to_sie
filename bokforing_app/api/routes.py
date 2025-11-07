import datetime

from flask import jsonify, request, url_for, current_app, make_response, flash, redirect
from bokforing_app.api import bp
from bokforing_app import db
from bokforing_app.models import Company, BankTransaction, BookkeepingEntry, Bilaga
import bokforing_app.services.booking_service as booking_service
import bokforing_app.services.sie_service as sie_service
import os


# --- API för CSV ---
@bp.route('/company/<int:company_id>/upload_csv', methods=['POST'])
def upload_csv(company_id):
    if 'csv_file' not in request.files:
        flash("Ingen fil vald", "danger")
    else:
        file = request.files['csv_file']
        if file.filename != '' and file.filename.endswith('.csv'):
            try:
                booking_service.process_csv_upload(file, company_id)
                flash("CSV-filen har laddats upp!", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Fel vid bearbetning av CSV: {e}", "danger")
        else:
            flash("Ogiltig filtyp (kräver .csv)", "danger")

    return redirect(url_for('main.bokforing_page', company_id=company_id))


# --- API för Bilagor ---
@bp.route('/company/<int:company_id>/multi_upload_bilagor', methods=['POST'])
def multi_upload_bilagor(company_id):
    if 'files' not in request.files:
        return jsonify({'error': 'Inga filer valda'}), 400
    
    files = request.files.getlist('files')
    uploaded_files_data = []
    
    for file in files:
        if file.filename == '': continue
        try:
            new_bilaga = booking_service.process_bilaga_upload(
                file, company_id, current_app.config['UPLOAD_FOLDER']
            )
            
            uploaded_files_data.append({
                'id': new_bilaga.id,
                'filename': new_bilaga.filename,
                'url': url_for('static', filename=f'uploads/{new_bilaga.filepath.replace(os.path.sep, "/")}'),
                
                'fakturadatum': new_bilaga.fakturadatum.strftime('%Y-%m-%d') if new_bilaga.fakturadatum else '',
                'forfallodag': new_bilaga.forfallodag.strftime('%Y-%m-%d') if new_bilaga.forfallodag else '',
                'fakturanr': new_bilaga.fakturanr or '',
                'ocr': new_bilaga.ocr or '',
                
                'brutto_amount': new_bilaga.brutto_amount or '',
                'netto_amount': new_bilaga.netto_amount or '',
                'moms_amount': new_bilaga.moms_amount or '',
                
                'saljare_namn': new_bilaga.saljare_namn or '',
                'saljare_orgnr': new_bilaga.saljare_orgnr or '',
                'saljare_bankgiro': new_bilaga.saljare_bankgiro or '',
                
                'kund_namn': new_bilaga.kund_namn or '',
                'kund_orgnr': new_bilaga.kund_orgnr or '',
                'kund_nummer': new_bilaga.kund_nummer or '',
                
                'suggested_konto': new_bilaga.suggested_konto or ''
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
            
    return jsonify(uploaded_files_data), 200

@bp.route('/bilaga/<int:bilaga_id>/metadata', methods=['POST'])
def update_bilaga_metadata(bilaga_id):
    try:
        booking_service.update_bilaga_metadata_service(bilaga_id, request.json)
        return jsonify({'message': 'Bilaga uppdaterad'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/bilaga/<int:bilaga_id>/bokfor', methods=['POST'])
def bokfor_bilaga(bilaga_id):
    try:
        entries_data = request.json.get('entries')
        if not entries_data:
            return jsonify({'error': 'Inga konteringsrader angivna.'}), 400

        ver_id = booking_service.bokfor_bilaga_service(bilaga_id, entries_data)

        return jsonify({'message': 'Bilagan har bokförts!', 'verifikation_id': ver_id}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/bilaga/<int:bilaga_id>', methods=['DELETE'])
def delete_bilaga(bilaga_id):
    try:
        bilaga = Bilaga.query.get_or_404(bilaga_id)
        file_to_delete = os.path.join(current_app.config['UPLOAD_FOLDER'], bilaga.filepath)
        if os.path.exists(file_to_delete):
            os.remove(file_to_delete)
        db.session.delete(bilaga)
        db.session.commit()
        return jsonify({'message': 'Bilaga borttagen'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# --- API för Bokföring (Modal) ---
@bp.route('/entries/<int:trans_id>', methods=['GET'])
def get_entries(trans_id):
    transaction = BankTransaction.query.get_or_404(trans_id)
    entries = [{'id': e.id, 'konto': e.konto, 'debet': e.debet, 'kredit': e.kredit} for e in transaction.entries]
    return jsonify(entries)


@bp.route('/entries/<int:trans_id>', methods=['POST'])
def save_entries(trans_id):
    transaction = BankTransaction.query.get_or_404(trans_id)
    data = request.json
    entries_data = data.get('entries')
    try:
        # ... (Logik för att validera balans och spara entries... kopiera från gamla app.py) ...
        # (Detta bör också flyttas till booking_service.py)
        transaction.status = 'processed'
        db.session.commit()
        return jsonify({'message': 'Sparat!', 'processed_id': trans_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/bilagor/<int:trans_id>', methods=['GET'])
def get_bilagor(trans_id):
    transaction = BankTransaction.query.get_or_404(trans_id)
    bilagor_list = []
    for b in transaction.attachments:
        bilagor_list.append({
            'id': b.id,
            'filename': b.filename,
            'url': url_for('static', filename=f'uploads/{b.filepath.replace(os.path.sep, "/")}')
        })
    return jsonify(bilagor_list)


@bp.route('/bilaga/link', methods=['POST'])
def link_bilaga():
    try:
        data = request.json
        bilaga = Bilaga.query.get_or_404(data.get('bilaga_id'))
        bilaga.bank_transaction_id = data.get('transaction_id')
        bilaga.status = 'assigned'
        db.session.commit()
        return jsonify({'message': 'Bilaga har kopplats!'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# --- API för SIE ---
@bp.route('/company/<int:company_id>/generate_sie', methods=['POST'])
def generate_sie(company_id):
    content, error = sie_service.generate_sie_content(company_id)
    if error:
        flash(error, "danger")
        return redirect(url_for('main.bokforing_page', company_id=company_id))
    filename = f"import_{company_id}_{datetime.now().strftime('%Y%m%d')}.si"
    response = make_response(content)
    response.charset = 'cp437'
    response.mimetype = 'text/plain'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response