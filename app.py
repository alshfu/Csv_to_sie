import os
from flask import Flask, render_template, request, redirect, url_for, flash, make_response, jsonify
from models import db, Company, BankTransaction, BookkeepingEntry, Bilaga
import pandas as pd
from datetime import datetime
import math

# --- Импортируем наши .py файлы ---
from bilaga_processor import save_bilaga_file
from accounting_config import KONTOPLAN, ASSOCIATION_MAP, get_contra_account
from pdf_reader import parse_xl_jbm_invoice

# --- Настройка Flask ---
basedir = os.path.abspath(os.path.dirname(__file__))
instance_folder = os.path.join(basedir, 'instance')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-super-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "instance", "app.db")}'
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')
app.config['DEBUG'] = True
db.init_app(app)


@app.before_request
def create_tables():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(instance_folder, exist_ok=True)
    with app.app_context():
        db.create_all()


def helper_clean_currency(text):
    """Вспомогательная функция для очистки и преобразования денежных сумм."""
    if not text:
        return None
    try:
        cleaned = str(text).replace(' ', '').replace(',', '.')
        return float(cleaned)
    except (ValueError, TypeError):
        return None


# --- Маршруты ---

@app.route('/', methods=['GET', 'POST'])
def index():
    """Главная страница для создания и просмотра компаний."""
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
        return redirect(url_for('index'))

    companies = Company.query.all()
    return render_template('companies.html', companies=companies)


@app.route('/company/<int:company_id>', methods=['GET'])
def bokforing_page(company_id):
    """Страница для работы с транзакциями и приложениями (bilagor)."""
    company = Company.query.get_or_404(company_id)
    transactions = BankTransaction.query.filter_by(
        company_id=company_id, status='unprocessed'
    ).order_by(BankTransaction.bokforingsdag.desc()).all()
    unassigned_bilagor = Bilaga.query.filter_by(
        company_id=company_id, status='unassigned'
    ).order_by(Bilaga.id.desc()).all()

    return render_template(
        'transactions.html',
        company=company,
        transactions=transactions,
        unassigned_bilagor=unassigned_bilagor,
        kontoplan=KONTOPLAN,
        association_map=ASSOCIATION_MAP
    )


@app.route('/company/<int:company_id>/verifikationer', methods=['GET'])
def verifikationer_page(company_id):
    """Страница для просмотра обработанных транзакций (верификаций)."""
    company = Company.query.get_or_404(company_id)
    transactions = BankTransaction.query.filter_by(
        company_id=company_id, status='processed'
    ).order_by(BankTransaction.bokforingsdag.desc()).all()

    return render_template(
        'verifikationer.html',
        company=company,
        transactions=transactions,
        kontoplan=KONTOPLAN,
        association_map=ASSOCIATION_MAP
    )


@app.route('/company/<int:company_id>/upload_csv', methods=['POST'])
def upload_csv(company_id):
    """Обрабатывает загрузку CSV файла с банковскими транзакциями."""
    if 'csv_file' not in request.files:
        flash("Ingen fil vald", "danger")
        return redirect(url_for('bokforing_page', company_id=company_id))

    file = request.files['csv_file']
    if file.filename == '' or not file.filename.endswith('.csv'):
        flash("Ogiltig filtyp (endast .csv tillåts)", "danger")
        return redirect(url_for('bokforing_page', company_id=company_id))

    try:
        df = pd.read_csv(file, sep=';', header=1, decimal=',', encoding='latin-1')
        df = df.dropna(subset=['Bokföringsdag'])

        for _, row in df.iterrows():
            amount = round(float(row['Insättning/Uttag']), 2)
            referens_text = str(row['Referens'])
            contra_konto = get_contra_account(referens_text, amount)

            new_trans = BankTransaction(
                company_id=company_id,
                bokforingsdag=datetime.strptime(row['Bokföringsdag'], '%Y-%m-%d').date(),
                referens=referens_text,
                belopp=amount,
                status='unprocessed'
            )
            db.session.add(new_trans)
            db.session.flush()  # Получаем ID для new_trans

            if amount > 0:  # Входящий
                entry_bank = BookkeepingEntry(bank_transaction_id=new_trans.id, konto='1930', debet=amount, kredit=0)
                entry_contra = BookkeepingEntry(bank_transaction_id=new_trans.id, konto=contra_konto, debet=0,
                                                kredit=amount)
            else:  # Исходящий
                entry_bank = BookkeepingEntry(bank_transaction_id=new_trans.id, konto='1930', debet=0, kredit=-amount)
                entry_contra = BookkeepingEntry(bank_transaction_id=new_trans.id, konto=contra_konto, debet=-amount,
                                                kredit=0)

            db.session.add_all([entry_bank, entry_contra])

        db.session.commit()
        flash("CSV-filen har laddats upp och transaktioner har skapats.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Fel vid bearbetning av CSV: {e}", "danger")

    return redirect(url_for('bokforing_page', company_id=company_id))


@app.route('/multi_upload_bilagor/<int:company_id>', methods=['POST'])
def multi_upload_bilagor(company_id):
    if 'files' not in request.files:
        return jsonify({'error': 'Inga filer valda'}), 400

    files = request.files.getlist('files')
    uploaded_files_data = []

    for file in files:
        if file.filename == '':
            continue

        try:
            filename, relative_filepath = save_bilaga_file(
                file,
                company_id,
                app.config['UPLOAD_FOLDER']
            )

            parsed_data = None
            if filename.lower().endswith('.pdf'):
                try:
                    absolute_filepath = os.path.join(app.config['UPLOAD_FOLDER'], relative_filepath)
                    parsed_data = parse_xl_jbm_invoice(absolute_filepath)
                except Exception as e:
                    print(f"--- Warning: PDF parser failed for {filename}. Error: {e} ---")
                    parsed_data = None

            new_bilaga = Bilaga(
                company_id=company_id,
                filename=filename,
                filepath=relative_filepath,
                status='unassigned'
            )

            if parsed_data:
                brutto = helper_clean_currency(parsed_data.get('summa_brutto'))
                netto = helper_clean_currency(parsed_data.get('netto'))
                final_moms = None

                if brutto is not None and netto is not None:
                    final_moms = round(brutto - netto, 2)

                new_bilaga.bilaga_date = datetime.strptime(parsed_data['fakturadatum'],
                                                           '%Y-%m-%d').date() if parsed_data.get(
                    'fakturadatum') else None
                new_bilaga.brutto_amount = brutto
                new_bilaga.netto_amount = netto
                new_bilaga.moms_amount = final_moms

                # Попытка 1: Угадать по строкам заказа (для XL JBM)
                if parsed_data.get('orders') and parsed_data['orders'][0]['items']:
                    first_item_name = parsed_data['orders'][0]['items'][0].get('benamning', '').lower()
                    for key, konto_nr in ASSOCIATION_MAP.items():
                        if key in first_item_name:
                            new_bilaga.suggested_konto = konto_nr  # Сохраняем номер счета
                            break

            #
            # ===============================================================
            #  ВОТ ИСПРАВЛЕНИЕ: Попытка 2 (Резервная) - Угадать по ИМЕНИ ФАЙЛА
            # ===============================================================
            #
            # Если счет НЕ был найден на Попытке 1...
            if not new_bilaga.suggested_konto:
                fn_lower = file.filename.lower()  # ...проверяем имя файла
                for key, konto_nr in ASSOCIATION_MAP.items():
                    if key in fn_lower:
                        new_bilaga.suggested_konto = konto_nr
                        break  # Нашли первое совпадение

            db.session.add(new_bilaga)
            db.session.commit()

            uploaded_files_data.append({
                'id': new_bilaga.id,
                'filename': new_bilaga.filename,
                'url': url_for('static', filename=os.path.join('uploads', new_bilaga.filepath)),
                'bilaga_date': new_bilaga.bilaga_date.strftime('%Y-%m-%d') if new_bilaga.bilaga_date else None,
                'brutto_amount': new_bilaga.brutto_amount,
                'netto_amount': new_bilaga.netto_amount,
                'moms_amount': new_bilaga.moms_amount,
                'suggested_konto': new_bilaga.suggested_konto  # <-- Теперь это поле будет заполнено!
            })
        except Exception as e:
            db.session.rollback()
            print(f"!!! ОШИБКА в multi_upload_bilagor: {e}")
            return jsonify({'error': str(e)}), 500

    return jsonify(uploaded_files_data), 200


@app.route('/update_bilaga_metadata/<int:bilaga_id>', methods=['POST'])
def update_bilaga_metadata(bilaga_id):
    """Обновляет метаданные для bilaga."""
    try:
        bilaga = Bilaga.query.get_or_404(bilaga_id)
        data = request.json

        if 'bilaga_date' in data and data['bilaga_date']:
            bilaga.bilaga_date = datetime.strptime(data['bilaga_date'], '%Y-%m-%d').date()
        if 'brutto_amount' in data:
            bilaga.brutto_amount = helper_clean_currency(data['brutto_amount'])
        if 'moms_amount' in data:
            bilaga.moms_amount = helper_clean_currency(data['moms_amount'])
        if 'suggested_konto' in data:
            bilaga.suggested_konto = data['suggested_konto']

        if bilaga.brutto_amount is not None and bilaga.moms_amount is not None:
            bilaga.netto_amount = round(bilaga.brutto_amount - bilaga.moms_amount, 2)

        db.session.commit()
        return jsonify({'message': 'Bilaga uppdaterad'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/link_bilaga', methods=['POST'])
def link_bilaga():
    """Привязывает bilaga к транзакции."""
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


@app.route('/upload_bilaga/<int:trans_id>', methods=['POST'])
def upload_bilaga(trans_id):
    """Загружает один файл bilaga для конкретной транзакции."""
    try:
        transaction = BankTransaction.query.get_or_404(trans_id)
        if 'bilaga_file' not in request.files:
            return jsonify({'error': 'Ingen fil'}), 400

        file = request.files['bilaga_file']
        base_upload_path = os.path.join(basedir, app.config['UPLOAD_FOLDER'])
        original_filename, relative_filepath = save_bilaga_file(file, transaction.company_id, base_upload_path)

        new_bilaga = Bilaga(
            transaction_id=trans_id,
            filename=original_filename,
            filepath=relative_filepath
        )
        db.session.add(new_bilaga)
        db.session.commit()

        return jsonify({
            'message': 'Filen har laddats upp!',
            'id': new_bilaga.id,
            'filename': new_bilaga.filename,
            'url': url_for('static', filename=new_bilaga.filepath)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        print(f"!!! ОШИБКА в upload_bilaga: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/delete_bilaga/<int:bilaga_id>', methods=['DELETE'])
def delete_bilaga(bilaga_id):
    """Удаляет bilaga (файл и запись в БД)."""
    try:
        bilaga = Bilaga.query.get_or_404(bilaga_id)
        base_upload_path = app.config['UPLOAD_FOLDER']
        file_to_delete = os.path.join(base_upload_path, bilaga.filepath)

        if os.path.exists(file_to_delete):
            os.remove(file_to_delete)

        db.session.delete(bilaga)
        db.session.commit()
        return jsonify({'message': 'Bilaga borttagen'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"!!! ОШИБКА в delete_bilaga: {e}")
        return jsonify({'error': str(e)}), 500


# --- API для модального окна ---

@app.route('/get_entries/<int:trans_id>', methods=['GET'])
def get_entries(trans_id):
    """Возвращает бухгалтерские проводки для транзакции."""
    transaction = BankTransaction.query.get_or_404(trans_id)
    entries = [{
        'id': entry.id,
        'konto': entry.konto,
        'debet': entry.debet,
        'kredit': entry.kredit
    } for entry in transaction.entries]
    return jsonify(entries)


@app.route('/save_entries/<int:trans_id>', methods=['POST'])
def save_entries(trans_id):
    """Сохраняет измененные бухгалтерские проводки."""
    transaction = BankTransaction.query.get_or_404(trans_id)
    entries_data = request.json.get('entries', [])
    try:
        total_debet = sum(float(e.get('debet', 0) or 0) for e in entries_data)
        total_kredit = sum(float(e.get('kredit', 0) or 0) for e in entries_data)

        if not math.isclose(total_debet, total_kredit, abs_tol=0.01):
            return jsonify({'error': f'Obalans! Debet ({total_debet}) matchar inte Kredit ({total_kredit})'}), 400

        BookkeepingEntry.query.filter_by(bank_transaction_id=trans_id).delete()

        for entry in entries_data:
            if entry.get('konto'):
                db.session.add(BookkeepingEntry(
                    bank_transaction_id=trans_id,
                    konto=entry['konto'],
                    debet=float(entry.get('debet', 0) or 0),
                    kredit=float(entry.get('kredit', 0) or 0)
                ))

        transaction.status = 'processed'
        db.session.commit()
        return jsonify({'message': 'Sparat!', 'processed_id': trans_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/get_bilagor/<int:trans_id>', methods=['GET'])
def get_bilagor(trans_id):
    """
    Hämtar en lista över alla bilagor som är kopplade
    till en specifik banktransaktion.
    """
    transaction = BankTransaction.query.get_or_404(trans_id)
    bilagor_list = []

    # transaction.attachments är 'attachments' relationen från models.py
    for b in transaction.attachments:
        bilagor_list.append({
            'id': b.id,
            'filename': b.filename,
            #
            # KORRIGERING:
            # Använder f-string och .replace() för att skapa en giltig webbadress
            # istället för os.path.join().
            #
            'url': url_for('static', filename=f'uploads/{b.filepath.replace(os.path.sep, "/")}')
        })
    return jsonify(bilagor_list)


# --- Генерация SIE ---

def generate_sie_content(company_id):
    """Собирает данные и генерирует содержимое SIE файла."""
    company = Company.query.get_or_404(company_id)
    transactions = BankTransaction.query.filter_by(company_id=company_id).order_by(BankTransaction.bokforingsdag).all()

    if not transactions:
        return None, "Inga transaktioner att exportera"

    first_date = transactions[0].bokforingsdag
    year_start = f"{first_date.year}0101"
    year_end = f"{first_date.year}1231"

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


@app.route('/company/<int:company_id>/generate_sie', methods=['POST'])
def generate_sie(company_id):
    """Запускает генерацию SIE файла и отдает его пользователю."""
    content, error = generate_sie_content(company_id)
    if error:
        flash(error, "danger")
        return redirect(url_for('bokforing_page', company_id=company_id))

    filename = f"import_{company_id}_{datetime.now().strftime('%Y%m%d')}.si"
    response = make_response(content)
    response.charset = 'cp437'  # Кодировка для SIE
    response.mimetype = 'text/plain'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response


if __name__ == '__main__':
    app.run(debug=True)
