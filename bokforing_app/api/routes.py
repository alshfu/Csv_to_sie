import datetime
import json
from flask import jsonify, request, url_for, current_app, make_response, flash, redirect
from bokforing_app.api import bp
from bokforing_app import db
from bokforing_app.models import Company, BankTransaction, BookkeepingEntry, Bilaga, Association, Setting, Konto
import bokforing_app.services.booking_service as booking_service
import bokforing_app.services.sie_service as sie_service
import bokforing_app.services.gemini_service as gemini_service
from bokforing_app.services.rule_engine import apply_rule
import os

# --- API för CSV ---
@bp.route('/company/<int:company_id>/upload_csv', methods=['POST'])
def upload_csv(company_id):
    if 'csv_file' not in request.files or not request.files['csv_file'].filename:
        flash("Ingen fil vald.", "danger")
        return redirect(url_for('main.bokforing_page', company_id=company_id))

    file = request.files['csv_file']
    if not file.filename.lower().endswith('.csv'):
        flash("Ogiltig filtyp. Endast .csv-filer är tillåtna.", "danger")
        return redirect(url_for('main.bokforing_page', company_id=company_id))

    try:
        stats = booking_service.process_csv_upload(file, company_id)
        
        messages = []
        if stats['new'] > 0:
            messages.append(f"{stats['new']} nya transaktioner har lagts till i 'Obearbetade'.")
        if stats['duplicates'] > 0:
            messages.append(f"{stats['duplicates']} potentiella dubbletter hittades och väntar på din granskning.")
        
        if not messages:
            flash("Inga nya transaktioner att importera hittades i filen.", "info")
        else:
            flash(" ".join(messages), "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Ett fel inträffade vid bearbetning av CSV: {e}", "danger")

    return redirect(url_for('main.bokforing_page', company_id=company_id))

@bp.route('/transaction/handle_duplicate', methods=['POST'])
def handle_duplicate():
    data = request.get_json()
    trans_id = data.get('id')
    action = data.get('action')

    transaction = BankTransaction.query.get_or_404(trans_id)

    if transaction.status != 'pending_duplicate':
        return jsonify({'error': 'Transaktionen är inte en väntande dubblett.'}), 400

    if action == 'approve':
        transaction.status = 'unprocessed'
        db.session.commit()
        return jsonify({'message': 'Transaktionen har godkänts och flyttats till obearbetade.'})
    elif action == 'reject':
        db.session.delete(transaction)
        db.session.commit()
        return jsonify({'message': 'Transaktionen har raderats.'})
    else:
        return jsonify({'error': 'Ogiltig åtgärd.'}), 400

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

# --- API för Bokföring (Modal & Verifikationer) ---
@bp.route('/verifikation/<int:trans_id>', methods=['GET'])
def get_verifikation(trans_id):
    trans = BankTransaction.query.get_or_404(trans_id)
    bank_event_data = None
    if trans.status != 'manual':
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
        if not data.get('bokforingsdag') or not data.get('referens'):
            raise ValueError("Datum och referens är obligatoriska.")
        total_debet = sum(float(e.get('debet', 0)) for e in data['entries'])
        total_kredit = sum(float(e.get('kredit', 0)) for e in data['entries'])
        if abs(total_debet - total_kredit) > 0.01:
            raise ValueError("Obalans! Debet och kredit summerar inte till samma värde.")
        new_trans = BankTransaction(
            company_id=company_id,
            bokforingsdag=datetime.datetime.strptime(data['bokforingsdag'], '%Y-%m-%d').date(),
            referens=data['referens'],
            belopp=total_debet,
            status='processed'
        )
        db.session.add(new_trans)
        db.session.flush()
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
        if not data.get('bokforingsdag') or not data.get('referens'):
            raise ValueError("Datum och referens är obligatoriska.")
        
        total_debet = sum(float(e.get('debet', 0)) for e in data['entries'])
        total_kredit = sum(float(e.get('kredit', 0)) for e in data['entries'])
        if abs(total_debet - total_kredit) > 0.01:
            raise ValueError("Obalans! Debet och kredit summerar inte till samma värde.")

        trans.bokforingsdag = datetime.datetime.strptime(data['bokforingsdag'], '%Y-%m-%d').date()
        trans.referens = data['referens']
        trans.status = 'processed'

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
        Bilaga.query.filter_by(bank_transaction_id=trans_id).update({'bank_transaction_id': None, 'status': 'unassigned'})
        db.session.delete(trans)
        db.session.commit()
        return jsonify({'message': 'Verifikation har raderats permanent.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# --- API för AI & Regelmotor ---
@bp.route('/transaction/<int:trans_id>/ask_gemini', methods=['POST'])
def ask_gemini_for_suggestion(trans_id):
    transaction = BankTransaction.query.get_or_404(trans_id)
    try:
        if transaction.referens:
            association = Association.query.filter_by(keyword=transaction.referens.strip()).first()
            if association and association.rule:
                try:
                    rule_dict = json.loads(association.rule)
                    generated_entries = apply_rule(transaction, rule_dict)
                    return jsonify({
                        "suggestion": {"description": rule_dict.get("description", transaction.referens), "entries": generated_entries},
                        "source": "rule"
                    }), 200
                except Exception as e:
                    current_app.logger.warning(f"Regel för '{transaction.referens}' misslyckades: {e}. Anropar Gemini.")
        
        general_rules_setting = Setting.query.filter_by(key='gemini_custom_prompt').first()
        general_rules = general_rules_setting.value if general_rules_setting else ''
        
        gemini_response = gemini_service.get_bokforing_suggestion_from_gemini(transaction, general_rules, "")
        
        if 'error' in gemini_response:
            return jsonify(gemini_response), 500
            
        if transaction.referens and 'rule' in gemini_response:
            keyword = transaction.referens.strip()
            association = Association.query.filter_by(keyword=keyword).first()
            if not association:
                main_account = next((e['konto'] for e in gemini_response['suggestion']['entries'] if e['konto'] != '1930'), None)
                if main_account:
                    association = Association(keyword=keyword, konto_nr=main_account)
                    db.session.add(association)
            
            if association:
                association.rule = json.dumps(gemini_response['rule'])
                db.session.commit()

        return jsonify({
            "suggestion": gemini_response.get('suggestion'),
            "source": "gemini"
        }), 200

    except Exception as e:
        db.session.rollback()
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
    all_associations = {a.keyword: a for a in Association.query.all()}
    for trans_id in transaction_ids:
        db.session.begin_nested()
        try:
            transaction = db.session.query(BankTransaction).get(trans_id)
            if not transaction or transaction.status != 'unprocessed':
                db.session.rollback()
                continue
            entries_data = None
            keyword = transaction.referens.strip() if transaction.referens else None
            if keyword and keyword in all_associations and all_associations[keyword].rule:
                try:
                    rule_dict = json.loads(all_associations[keyword].rule)
                    entries_data = apply_rule(transaction, rule_dict)
                except Exception as e:
                    current_app.logger.warning(f"Batch: Regel för '{keyword}' misslyckades: {e}. Anropar Gemini.")
            if not entries_data:
                gemini_response = gemini_service.get_bokforing_suggestion_from_gemini(transaction, general_rules, "")
                if 'error' in gemini_response:
                    raise Exception(gemini_response['error'])
                entries_data = gemini_response.get('suggestion', {}).get('entries', [])
                if keyword and 'rule' in gemini_response:
                    association = all_associations.get(keyword)
                    if not association:
                        main_account = next((e['konto'] for e in entries_data if e['konto'] != '1930'), None)
                        if main_account:
                            association = Association(keyword=keyword, konto_nr=main_account)
                            db.session.add(association)
                            all_associations[keyword] = association
                    if association:
                        association.rule = json.dumps(gemini_response['rule'])
            if not entries_data:
                raise Exception("Inget förslag kunde genereras.")
            BookkeepingEntry.query.filter_by(bank_transaction_id=trans_id).delete()
            total_debet = sum(float(e.get('debet', 0)) for e in entries_data)
            total_kredit = sum(float(e.get('kredit', 0)) for e in entries_data)
            if abs(total_debet - total_kredit) > 0.01 or total_debet == 0:
                raise Exception("Obalans i förslaget")
            for entry_data in entries_data:
                new_entry = BookkeepingEntry(bank_transaction_id=trans_id, konto=entry_data['konto'], debet=float(entry_data.get('debet', 0)), kredit=float(entry_data.get('kredit', 0)))
                db.session.add(new_entry)
            transaction.status = 'processed'
            db.session.commit()
            success_ids.append(trans_id)
        except Exception as e:
            db.session.rollback()
            errors.append({'id': trans_id, 'error': str(e)})
    return jsonify({'success_ids': success_ids, 'errors': errors}), 200

# --- API för SIE & AI-inställningar ---
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
