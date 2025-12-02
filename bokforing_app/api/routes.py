import datetime
import json
from flask import jsonify, request, url_for, current_app, make_response, flash, redirect
from bokforing_app.api import bp
from bokforing_app import db
from bokforing_app.models import Company, BankTransaction, BookkeepingEntry, Bilaga, Association, Setting, Konto
import bokforing_app.services.booking_service as booking_service
import bokforing_app.services.sie_service as sie_service
import bokforing_app.services.gemini_service as gemini_service
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


# --- API för Bokföring (Modal & Verifikationer) ---
@bp.route('/verifikation/<int:trans_id>', methods=['GET'])
def get_verifikation(trans_id):
    trans = BankTransaction.query.get_or_404(trans_id)
    
    # Hämta original bankhändelse-data om det är en importerad transaktion
    bank_event_data = None
    if trans.status != 'manual': # Antag att manuellt skapade har en specifik status
        bank_event_data = {
            'date': trans.bokforingsdag.strftime('%Y-%m-%d'),
            'ref': trans.referens,
            'amount': trans.belopp
        }

    return jsonify({
        'id': trans.id,
        'bokforingsdag': trans.bokforingsdag.strftime('%Y-%m-%d'),
        'referens': trans.referens,
        'entries': [{'konto': e.konto, 'debet': e.debet, 'kredit': e.kredit} for e in trans.entries],
        'attachments': [{'id': b.id, 'filename': b.filename, 'url': url_for('static', filename=f'uploads/{b.filepath.replace(os.path.sep, "/")}')} for b in trans.attachments],
        'bank_event': bank_event_data
    })

@bp.route('/company/<int:company_id>/verifikation', methods=['POST'])
def create_verifikation(company_id):
    data = request.json
    try:
        # Validering
        if not data.get('bokforingsdag') or not data.get('referens'):
            raise ValueError("Datum och referens är obligatoriska.")
        
        total_debet = sum(float(e.get('debet', 0)) for e in data['entries'])
        total_kredit = sum(float(e.get('kredit', 0)) for e in data['entries'])
        if abs(total_debet - total_kredit) > 0.01:
            raise ValueError("Obalans! Debet och kredit summerar inte till samma värde.")

        # Skapa en "manuell" transaktion
        new_trans = BankTransaction(
            company_id=company_id,
            bokforingsdag=datetime.datetime.strptime(data['bokforingsdag'], '%Y-%m-%d').date(),
            referens=data['referens'],
            belopp=total_debet, # Totala omslutningen
            status='processed' # eller 'manual'
        )
        db.session.add(new_trans)
        db.session.flush() # För att få ett ID till new_trans

        for entry_data in data['entries']:
            new_entry = BookkeepingEntry(
                bank_transaction_id=new_trans.id,
                konto=entry_data['konto'],
                debet=float(entry_data.get('debet', 0)),
                kredit=float(entry_data.get('kredit', 0))
            )
            db.session.add(new_entry)
        
        db.session.commit()
        return jsonify({'message': 'Verifikation skapad!', 'id': new_trans.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/verifikation/<int:trans_id>', methods=['PUT'])
def update_verifikation(trans_id):
    trans = BankTransaction.query.get_or_404(trans_id)
    data = request.json
    try:
        # Validering
        if not data.get('bokforingsdag') or not data.get('referens'):
            raise ValueError("Datum och referens är obligatoriska.")
        
        total_debet = sum(float(e.get('debet', 0)) for e in data['entries'])
        total_kredit = sum(float(e.get('kredit', 0)) for e in data['entries'])
        if abs(total_debet - total_kredit) > 0.01:
            raise ValueError("Obalans! Debet och kredit summerar inte till samma värde.")

        # Uppdatera transaktionen
        trans.bokforingsdag = datetime.datetime.strptime(data['bokforingsdag'], '%Y-%m-%d').date()
        trans.referens = data['referens']
        trans.belopp = total_debet # Totala omslutningen

        # Ta bort gamla entries och lägg till nya
        BookkeepingEntry.query.filter_by(bank_transaction_id=trans_id).delete()
        for entry_data in data['entries']:
            new_entry = BookkeepingEntry(
                bank_transaction_id=trans_id,
                konto=entry_data['konto'],
                debet=float(entry_data.get('debet', 0)),
                kredit=float(entry_data.get('kredit', 0))
            )
            db.session.add(new_entry)
            
        db.session.commit()
        return jsonify({'message': 'Verifikation uppdaterad!', 'id': trans.id}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/verifikation/<int:trans_id>', methods=['DELETE'])
def delete_verifikation(trans_id):
    trans = BankTransaction.query.get_or_404(trans_id)
    try:
        # Frikoppla eventuella bilagor
        Bilaga.query.filter_by(bank_transaction_id=trans_id).update({'bank_transaction_id': None, 'status': 'unassigned'})
        # Radera transaktionen och dess entries (via cascade)
        db.session.delete(trans)
        db.session.commit()
        return jsonify({'message': 'Verifikation har raderats permanent.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/bilagor/<int:trans_id>', methods=['GET'])
def get_bilagor(trans_id):
    transaction = BankTransaction.query.get_or_404(trans_id)
    bilagor_list = [{'id': b.id, 'filename': b.filename, 'url': url_for('static', filename=f'uploads/{b.filepath.replace(os.path.sep, "/")}')} for b in transaction.attachments]
    return jsonify(bilagor_list)


@bp.route('/api/bilaga/link', methods=['POST'])
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

# --- API för Gemini AI ---
@bp.route('/transaction/<int:trans_id>/ask_gemini', methods=['POST'])
def ask_gemini_for_suggestion(trans_id):
    transaction = BankTransaction.query.get_or_404(trans_id)
    try:
        general_rules_setting = Setting.query.filter_by(key='gemini_custom_prompt').first()
        general_rules = general_rules_setting.value if general_rules_setting else ''
        
        specific_rule = ''
        if transaction.referens:
            association = Association.query.filter_by(keyword=transaction.referens.strip()).first()
            if association and association.rule:
                specific_rule = association.rule

        suggestion_json_str = gemini_service.get_bokforing_suggestion_from_gemini(transaction, general_rules, specific_rule)
        suggestion_data = json.loads(suggestion_json_str)
        
        if 'error' in suggestion_data:
            return jsonify(suggestion_data), 500
            
        return jsonify(suggestion_data), 200
    except Exception as e:
        return jsonify({'error': f"Ett oväntat fel inträffade: {str(e)}"}), 500

@bp.route('/batch_book_with_ai', methods=['POST'])
def batch_book_with_ai():
    data = request.get_json()
    transaction_ids = data.get('transaction_ids', [])
    if not transaction_ids:
        return jsonify({'error': 'Inga transaktioner valda'}), 400

    success_ids = []
    errors = []

    general_rules_setting = Setting.query.filter_by(key='gemini_custom_prompt').first()
    general_rules = general_rules_setting.value if general_rules_setting else ''
    all_associations = {a.keyword: a.rule for a in Association.query.all()}

    for trans_id in transaction_ids:
        db.session.begin_nested()
        try:
            transaction = db.session.query(BankTransaction).get(trans_id)
            if not transaction or transaction.status != 'unprocessed':
                db.session.rollback()
                continue

            specific_rule = ''
            if transaction.referens:
                specific_rule = all_associations.get(transaction.referens.strip(), '')

            suggestion_json_str = gemini_service.get_bokforing_suggestion_from_gemini(transaction, general_rules, specific_rule)
            suggestion_data = json.loads(suggestion_json_str)
            if 'error' in suggestion_data:
                raise Exception(suggestion_data['error'])

            entries_data = suggestion_data.get('entries', [])
            BookkeepingEntry.query.filter_by(bank_transaction_id=trans_id).delete()
            
            total_debet = sum(float(e.get('debet', 0)) for e in entries_data)
            total_kredit = sum(float(e.get('kredit', 0)) for e in entries_data)

            if abs(total_debet - total_kredit) > 0.01 or total_debet == 0:
                raise Exception("Obalans från AI-förslag")

            for entry_data in entries_data:
                new_entry = BookkeepingEntry(bank_transaction_id=trans_id, konto=entry_data['konto'], debet=float(entry_data.get('debet', 0)), kredit=float(entry_data.get('kredit', 0)))
                db.session.add(new_entry)
            
            if transaction.referens:
                main_account_entry = next((e for e in entries_data if e.get('konto') != '1930'), None)
                if main_account_entry:
                    keyword = transaction.referens.strip()
                    if keyword not in all_associations:
                        new_association = Association(keyword=keyword, konto_nr=main_account_entry.get('konto'))
                        db.session.add(new_association)
                        all_associations[keyword] = ''

            transaction.status = 'processed'
            db.session.commit()
            success_ids.append(trans_id)

        except Exception as e:
            db.session.rollback()
            errors.append({'id': trans_id, 'error': str(e)})

    return jsonify({'success_ids': success_ids, 'errors': errors}), 200


# --- API för SIE ---
@bp.route('/company/<int:company_id>/generate_sie', methods=['POST'])
def generate_sie(company_id):
    content, error = sie_service.generate_sie_content(company_id)
    if error:
        flash(error, "danger")
        return redirect(url_for('main.bokforing_page', company_id=company_id))
    filename = f"import_{company_id}_{datetime.datetime.now().strftime('%Y%m%d')}.si"
    response = make_response(content)
    response.charset = 'cp437'
    response.mimetype = 'text/plain'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

# --- API för AI-inställningar ---
@bp.route('/ai_settings', methods=['GET'])
def get_ai_settings():
    associations = Association.query.order_by(Association.keyword).all()
    
    grouped_associations = {}
    for a in associations:
        if a.konto_nr not in grouped_associations:
            grouped_associations[a.konto_nr] = []
        grouped_associations[a.konto_nr].append({
            'id': a.id,
            'keyword': a.keyword,
            'rule': a.rule
        })

    prompt_setting = Setting.query.filter_by(key='gemini_custom_prompt').first()
    prompt_data = prompt_setting.value if prompt_setting else ''
    
    return jsonify({
        'associations_by_account': grouped_associations,
        'gemini_custom_prompt': prompt_data
    })

@bp.route('/ai_settings/prompt', methods=['POST'])
def save_ai_prompt():
    data = request.json
    prompt_text = data.get('prompt', '')
    
    setting = Setting.query.filter_by(key='gemini_custom_prompt').first()
    if setting:
        setting.value = prompt_text
    else:
        setting = Setting(key='gemini_custom_prompt', value=prompt_text)
        db.session.add(setting)
    
    db.session.commit()
    return jsonify({'message': 'AI-prompt sparad!'})

@bp.route('/ai_settings/association', methods=['POST'])
def add_association():
    data = request.json
    keyword = data.get('keyword')
    konto_nr = data.get('konto_nr')
    rule = data.get('rule')

    if not keyword or not konto_nr:
        return jsonify({'error': 'Nyckelord och konto är obligatoriska.'}), 400
    
    existing = Association.query.filter_by(keyword=keyword).first()
    if existing:
        return jsonify({'error': f'Nyckelordet "{keyword}" är redan kopplat till konto {existing.konto_nr}.'}), 409

    new_association = Association(keyword=keyword, konto_nr=konto_nr, rule=rule)
    db.session.add(new_association)
    db.session.commit()
    
    return jsonify({
        'message': 'Association tillagd!',
        'association': { 'id': new_association.id, 'keyword': new_association.keyword, 'rule': new_association.rule }
    }), 201

@bp.route('/ai_settings/association/<int:assoc_id>', methods=['PUT'])
def update_association(assoc_id):
    association = Association.query.get_or_404(assoc_id)
    data = request.json
    
    new_keyword = data.get('keyword', association.keyword)
    
    existing = Association.query.filter(Association.keyword == new_keyword, Association.id != assoc_id).first()
    if existing:
        return jsonify({'error': f'Nyckelordet "{new_keyword}" är redan kopplat till konto {existing.konto_nr}.'}), 409

    association.keyword = new_keyword
    association.rule = data.get('rule', association.rule)
    
    db.session.commit()
    return jsonify({'message': 'Association uppdaterad!'})

@bp.route('/ai_settings/association/<int:assoc_id>', methods=['DELETE'])
def delete_association(assoc_id):
    association = Association.query.get_or_404(assoc_id)
    db.session.delete(association)
    db.session.commit()
    return jsonify({'message': 'Association borttagen!'})
