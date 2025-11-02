import os
from flask import Flask, render_template, request, redirect, url_for, flash, make_response, jsonify
from models import db, Company, BankTransaction, BookkeepingEntry, Bilaga
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, make_response, jsonify
from models import db, Company, BankTransaction, BookkeepingEntry, Bilaga
from datetime import datetime
import math

# --- Настройка Flask (без изменений) ---
basedir = os.path.abspath(os.path.dirname(__file__))
instance_folder = os.path.join(basedir, 'instance')
db_path = os.path.join(instance_folder, 'app.db')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-super-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
db.init_app(app)

ASSOCIATION_MAP = {
    'lön': '1613',
    'skatteverket': '1630',
    'lån': '1680',
    'utlägg': '2893',
    'avräkning': '2893',
    'avr': '2893',
    'bankavgift': '6570',  # 'bank' слишком общее, 'bankavgift' (комиссия) лучше
    'leverantör': '2440',
    'försäljning': '3041',
    # 'moms' обрабатывается отдельно ниже
}

DEFAULT_KONTO_DEBIT = '1798'  # (Для Uttag / Исходящий)
DEFAULT_KONTO_KREDIT = '1799'  # (Для Insättning / Входящий)


def get_contra_account(referens, amount):
    """
    Анализирует описание транзакции и сумму,
    чтобы найти правильный контра-счет.
    """
    text = referens.lower()

    # 1. Сначала НДС (moms) - у него особый приоритет
    if 'moms' in text:
        if amount > 0:  # Insättning (входящий) -> utgående moms
            return '2611'
        else:  # Uttag (исходящий) -> ingående moms
            return '2641'

    # 2. Поиск по остальным ключевым словам
    for keyword, account in ASSOCIATION_MAP.items():
        if keyword in text:
            return account

    # 3. Если ничего не найдено, используем счет по умолчанию
    if amount > 0:
        return DEFAULT_KONTO_KREDIT  # 1799
    else:
        return DEFAULT_KONTO_DEBIT  # 1798


@app.before_request
def create_tables():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(instance_folder, exist_ok=True)
    with app.app_context():
        db.create_all()


# --- Страница 1: Фирмы (без изменений) ---
@app.route('/', methods=['GET', 'POST'])
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
            flash(f"Fel: {e}", "danger")
        return redirect(url_for('index'))

    companies = Company.query.all()
    return render_template('companies.html', companies=companies)


# --- Страница 2: Загрузка (без изменений) ---
@app.route('/company/<int:company_id>', methods=['GET'])
def upload_page(company_id):
    company = Company.query.get_or_404(company_id)
    # Показываем ВСЕ транзакции.
    # Сортируем по статусу (unprocessed будут первыми) и дате.
    transactions = BankTransaction.query.filter_by(
        company_id=company_id
    ).order_by(BankTransaction.status.desc(), BankTransaction.bokforingsdag.desc()).all()

    return render_template('transactions.html', company=company, transactions=transactions)


@app.route('/company/<int:company_id>/upload_csv', methods=['POST'])
def upload_csv(company_id):
    company = Company.query.get_or_404(company_id)

    if 'csv_file' not in request.files:
        flash("Ingen fil vald", "danger")
        return redirect(url_for('upload_page', company_id=company_id))

    file = request.files['csv_file']
    if file.filename == '' or not file.filename.endswith('.csv'):
        flash("Ogiltig filtyp (kräver .csv)", "danger")
        return redirect(url_for('upload_page', company_id=company_id))

    try:
        df = pd.read_csv(file, sep=';', header=1, decimal=',', encoding='latin-1')
        df = df.dropna(subset=['Bokföringsdag'])

        for _, row in df.iterrows():
            amount = float(row['Insättning/Uttag'])
            amount = round(amount, 2)
            referens_text = str(row['Referens'])

            # --- ВЫЗЫВАЕМ НОВУЮ "УМНУЮ" ФУНКЦИЮ ---
            contra_konto = get_contra_account(referens_text, amount)
            # --- --- --- --- --- --- --- --- ---

            # 1. Создаем "мастер" транзакцию
            new_trans = BankTransaction(
                company_id=company.id,
                bokforingsdag=datetime.strptime(row['Bokföringsdag'], '%Y-%m-%d').date(),
                referens=referens_text,
                belopp=amount,
                status='unprocessed'  # Статус "unprocessed", даже если счет найден
            )
            db.session.add(new_trans)
            db.session.flush()

            # 2. Создаем бух. записи (с правильным контра-счетом)
            if amount > 0:
                # Insättning (Входящий)
                # D 1930, K <contra_konto>
                entry_bank = BookkeepingEntry(bank_transaction_id=new_trans.id, konto='1930', debet=amount, kredit=0)
                entry_contra = BookkeepingEntry(bank_transaction_id=new_trans.id, konto=contra_konto, debet=0,
                                                kredit=amount)
            else:
                # Uttag (Исходящий)
                # K 1930, D <contra_konto>
                entry_bank = BookkeepingEntry(bank_transaction_id=new_trans.id, konto='1930', debet=0, kredit=-amount)
                entry_contra = BookkeepingEntry(bank_transaction_id=new_trans.id, konto=contra_konto, debet=-amount,
                                                kredit=0)

            db.session.add_all([entry_bank, entry_contra])

        db.session.commit()
        flash("CSV-filen har laddats upp och transaktioner har skapats.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Fel vid bearbetning av CSV: {e}", "danger")

    return redirect(url_for('upload_page', company_id=company_id))


# --- API для модального окна (без изменений) ---
@app.route('/get_entries/<int:trans_id>', methods=['GET'])
def get_entries(trans_id):
    transaction = BankTransaction.query.get_or_404(trans_id)
    entries = []
    for entry in transaction.entries:
        entries.append({
            'id': entry.id,
            'konto': entry.konto,
            'debet': entry.debet,
            'kredit': entry.kredit
        })
    return jsonify(entries)


@app.route('/save_entries/<int:trans_id>', methods=['POST'])
def save_entries(trans_id):
    transaction = BankTransaction.query.get_or_404(trans_id)
    data = request.json
    entries_data = data.get('entries')

    if not entries_data:
        return jsonify({'error': 'Inga rader att spara'}), 400

    try:
        # 1. Проверяем баланс
        total_debet = 0.0
        total_kredit = 0.0
        for entry in entries_data:
            total_debet += float(entry.get('debet', 0) or 0)
            total_kredit += float(entry.get('kredit', 0) or 0)

        if not math.isclose(total_debet, total_kredit, abs_tol=0.01):
            return jsonify({'error': f'Obalans! Debet ({total_debet}) matchar inte Kredit ({total_kredit})'}), 400

        # 2. Удаляем старые записи
        BookkeepingEntry.query.filter_by(bank_transaction_id=trans_id).delete()

        # 3. Создаем новые записи
        for entry in entries_data:
            if not entry.get('konto'):
                continue

            new_entry = BookkeepingEntry(
                bank_transaction_id=trans_id,
                konto=entry['konto'],
                debet=float(entry.get('debet', 0) or 0),
                kredit=float(entry.get('kredit', 0) or 0)
            )
            db.session.add(new_entry)

        # 4. Помечаем транзакцию как обработанную
        transaction.status = 'processed'

        db.session.commit()
        return jsonify({'message': 'Sparat!', 'processed_id': trans_id})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# --- Генерация SIE (без изменений) ---
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

    konton = set()
    for t in transactions:
        for entry in t.entries:
            konton.add(entry.konto)

    sie_data = []

    # Заголовки
    sie_data.append('#FLAGGA 0')
    sie_data.append('#PROGRAM "CSV-to-SIE App" 1.0')
    sie_data.append('#FORMAT PC8')
    sie_data.append(f'#GEN {datetime.now().strftime("%Y%m%d")} "Admin"')
    sie_data.append('#SIETYP 4')
    sie_data.append(f'#FNAMN "{company.name}"')
    sie_data.append(f'#ORGNR {company.org_nummer}')
    postadr = f'"{company.postkod} {company.ort}"'
    sie_data.append(f'#ADRESS "" "{company.gata}" {postadr} ""')
    sie_data.append(f'#RAR 0 {year_start} {year_end}')

    # Контоплан
    for konto_nr in sorted(list(konton)):
        # ВАЖНО: для реального SIE-файла здесь нужно настоящее имя счета
        # Сейчас мы просто используем номер
        sie_data.append(f'#KONTO {konto_nr} "Konto {konto_nr}"')

        # Транзакции
    ver_nr = 1

    for trans in transactions:
        ver_date = trans.bokforingsdag.strftime('%Y%m%d')
        ver_text = str(trans.referens).replace('"', '')

        sie_data.append(f'#VER "B" {ver_nr} {ver_date} "{ver_text}"')
        sie_data.append('{')

        for entry in trans.entries:
            belopp = 0.0
            if entry.debet > 0:
                belopp = entry.debet
            elif entry.kredit > 0:
                belopp = -entry.kredit

            if belopp == 0.0:
                continue

            sie_data.append(f'#TRANS {entry.konto} {{}} {belopp:.2f}')

        sie_data.append('}')
        ver_nr += 1

    return "\r\n".join(sie_data), None


# --- Маршрут генерации SIE (без изменений) ---
@app.route('/company/<int:company_id>/generate_sie', methods=['POST'])
def generate_sie(company_id):
    content, error = generate_sie_content(company_id)

    if error:
        flash(error, "danger")
        return redirect(url_for('upload_page', company_id=company_id))

    filename = f"import_{company_id}_{datetime.now().strftime('%Y%m%d')}.si"

    response = make_response(content)
    response.charset = 'cp437'
    response.mimetype = 'text/plain'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'

    return response


@app.route('/get_bilagor/<int:trans_id>', methods=['GET'])
def get_bilagor(trans_id):
    """Отдает список загруженных bilagor для транзакции."""
    transaction = BankTransaction.query.get_or_404(trans_id)
    bilagor_list = []

    # transaction.attachments - это 'attachments' из models.py
    for b in transaction.attachments:
        bilagor_list.append({
            'id': b.id,
            'filename': b.filename,
            # 'filepath' в БД = 'company_1/faktura.pdf'
            # url_for('static', filename=...) создаст /static/uploads/company_1/faktura.pdf
            'url': url_for('static', filename=os.path.join('uploads', b.filepath))
        })
    return jsonify(bilagor_list)


@app.route('/upload_bilaga/<int:trans_id>', methods=['POST'])
@app.route('/upload_bilaga/<int:trans_id>', methods=['POST'])
def upload_bilaga(trans_id):
    """Загружает новый файл bilaga для транзакции."""
    try:
        transaction = BankTransaction.query.get_or_404(trans_id)

        if 'bilaga_file' not in request.files:
            return jsonify({'error': 'Ingen fil'}), 400

        file = request.files['bilaga_file']

        #
        # ===============================================================
        #  ИСПРАВЛЕНИЕ ЗДЕСЬ
        # ===============================================================
        #

        # 1. Получаем АБСОЛЮТНЫЙ путь к главной папке 'uploads'
        #    (app.config['UPLOAD_FOLDER'] у нас = 'static/uploads')
        base_upload_path = os.path.join(basedir, app.config['UPLOAD_FOLDER'])

        # 2. Передаем этот путь в нашу helper-функцию
        filename, relative_filepath = save_bilaga_file(
            file,
            transaction.company_id,
            base_upload_path  # <--- НОВЫЙ АРГУМЕНТ
        )

        #
        # ===============================================================
        #  КОНЕЦ ИСПРАВЛЕНИЯ
        # ===============================================================
        #

        # 2. Сохраняем запись в БД (здесь нет изменений)
        new_bilaga = Bilaga(
            transaction_id=trans_id,
            filename=filename,
            filepath=relative_filepath
        )
        db.session.add(new_bilaga)
        db.session.commit()

        # 3. Отправляем JSON-ответ обратно в JS (здесь нет изменений)
        return jsonify({
            'message': 'Filen har laddats upp!',
            'id': new_bilaga.id,
            'filename': new_bilaga.filename,
            'url': url_for('static', filename=os.path.join('uploads', new_bilaga.filepath))
        })

    except Exception as e:
        db.session.rollback()
        # Добавим лог ошибки в консоль, чтобы видеть, что случилось
        print(f"!!! ОШИБКА в upload_bilaga: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/delete_bilaga/<int:bilaga_id>', methods=['DELETE'])
def delete_bilaga(bilaga_id):
    try:
        bilaga = Bilaga.query.get_or_404(bilaga_id)

        # Находим абсолютный путь к файлу
        # (basedir должен быть определен вверху вашего app.py)
        base_upload_path = os.path.join(basedir, app.config['UPLOAD_FOLDER'])
        # bilaga.filepath = 'company_1/faktura.pdf'
        file_to_delete = os.path.join(base_upload_path, bilaga.filepath)

        # 1. Удаляем файл с диска
        if os.path.exists(file_to_delete):
            os.remove(file_to_delete)

        # 2. Удаляем запись из БД
        db.session.delete(bilaga)
        db.session.commit()

        return jsonify({'message': 'Bilaga borttagen'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"!!! ОШИБКА в delete_bilaga: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
