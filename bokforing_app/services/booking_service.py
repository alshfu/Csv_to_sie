# -*- coding: utf-8 -*-

"""
Модуль booking_service.py

Этот модуль содержит основную бизнес-логику для обработки банковских транзакций
и квитанций (bilagor) в приложении. Он включает функции для:
- Получения данных о компании (транзакции, неприсвоенные квитанции).
- Обработки загруженных CSV-файлов с банковскими выписками.
- Обработки загруженных файлов квитанций (PDF, изображения) с использованием PDF-парсера.
- Обновления метаданных квитанций.
- Проведения бухгалтерских проводок для квитанций.
- Удаления квитанций.

Взаимодействует с базой данных через SQLAlchemy (db) и использует другие сервисы
(pdf_reader, file_service) для выполнения своих задач.
"""

import pandas as pd
from datetime import datetime
import math
import os
from flask import current_app
from bokforing_app import db
from bokforing_app.models import BankTransaction, BookkeepingEntry, Bilaga
from bokforing_app.services.accounting_config import KONTOPLAN, ASSOCIATION_MAP, get_contra_account
from bokforing_app.services.pdf_reader import parse_xl_jbm_invoice
from bokforing_app.services.file_service import save_bilaga_file


# --- Функции для получения данных (используются контроллерами) ---

def get_company_data(company_id):
    """
    Получает неприсвоенные банковские транзакции и квитанции для указанной компании.

    Args:
        company_id (int): ID компании.

    Returns:
        tuple: Кортеж из двух списков: (transactions, unassigned_bilagor).
    """
    # Запрашиваем банковские транзакции со статусом 'unprocessed' (необработанные)
    transactions = BankTransaction.query.filter_by(
        company_id=company_id,
        status='unprocessed'
    ).order_by(BankTransaction.bokforingsdag.desc()).all()

    # Запрашиваем квитанции со статусом 'unassigned' (неприсвоенные)
    unassigned_bilagor = Bilaga.query.filter_by(
        company_id=company_id,
        status='unassigned'
    ).order_by(Bilaga.id.desc()).all()

    return transactions, unassigned_bilagor


def get_verifikationer(company_id):
    """
    Получает все обработанные банковские транзакции (верификации) для указанной компании.

    Args:
        company_id (int): ID компании.

    Returns:
        list: Список объектов BankTransaction со статусом 'processed'.
    """
    return BankTransaction.query.filter_by(
        company_id=company_id,
        status='processed'
    ).order_by(BankTransaction.bokforingsdag.desc()).all()


def get_all_bilagor(company_id):
    """
    Получает все квитанции для указанной компании, отсортированные по статусу и дате.

    Args:
        company_id (int): ID компании.

    Returns:
        list: Список объектов Bilaga.
    """
    return Bilaga.query.filter_by(
        company_id=company_id
    ).order_by(Bilaga.status.asc(), Bilaga.fakturadatum.desc()).all()


# --- Логика для импорта CSV ---

def process_csv_upload(file, company_id):
    """
    Обрабатывает загруженный CSV-файл с банковскими транзакциями.

    Читает CSV, создает объекты BankTransaction и BookkeepingEntry,
    и сохраняет их в базу данных.

    Args:
        file (FileStorage): Объект файла, загруженный через Flask request.
        company_id (int): ID компании, к которой относятся транзакции.
    """
    # Чтение CSV-файла с использованием pandas
    # sep=';': разделитель столбцов - точка с запятой
    # header=1: заголовок находится во второй строке (индекс 1)
    # decimal=',': десятичный разделитель - запятая
    # encoding='latin-1': указание кодировки для корректного чтения символов
    df = pd.read_csv(file, sep=';', header=1, decimal=',', encoding='latin-1')
    
    # Удаляем строки, где отсутствует 'Bokföringsdag' (дата проводки)
    df = df.dropna(subset=['Bokföringsdag'])

    # Итерируемся по каждой строке DataFrame
    for _, row in df.iterrows():
        # Извлекаем сумму транзакции и округляем до двух знаков после запятой
        amount = round(float(row['Insättning/Uttag']), 2)
        # Извлекаем текст ссылки/описания
        referens_text = str(row['Referens'])
        # Определяем корреспондирующий счет на основе текста и суммы
        contra_konto = get_contra_account(referens_text, amount)

        # Создаем новую банковскую транзакцию
        new_trans = BankTransaction(
            company_id=company_id,
            # Преобразуем строку даты в объект date
            bokforingsdag=datetime.strptime(row['Bokföringsdag'], '%Y-%m-%d').date(),
            referens=referens_text,
            belopp=amount,
            status='unprocessed' # Изначально транзакция необработана
        )
        db.session.add(new_trans)
        db.session.flush() # Получаем ID новой транзакции до коммита

        # Создаем бухгалтерские проводки (дебет/кредит)
        if amount > 0: # Если это поступление (Insättning)
            # Дебет по счету банка (1930) на сумму поступления
            entry_bank = BookkeepingEntry(bank_transaction_id=new_trans.id, konto='1930', debet=amount, kredit=0)
            # Кредит по корреспондирующему счету на сумму поступления
            entry_contra = BookkeepingEntry(bank_transaction_id=new_trans.id, konto=contra_konto, debet=0, kredit=amount)
        else: # Если это расход (Uttag)
            # Кредит по счету банка (1930) на сумму расхода (абсолютное значение)
            entry_bank = BookkeepingEntry(bank_transaction_id=new_trans.id, konto='1930', debet=0, kredit=-amount)
            # Дебет по корреспондирующему счету на сумму расхода (абсолютное значение)
            entry_contra = BookkeepingEntry(bank_transaction_id=new_trans.id, konto=contra_konto, debet=-amount, kredit=0)

        db.session.add_all([entry_bank, entry_contra])

    db.session.commit() # Сохраняем все изменения в базу данных


# --- Логика для обработки квитанций (Bilaga) ---

def helper_clean_currency(text):
    """
    Вспомогательная функция для очистки и преобразования строкового представления валюты в float.

    Удаляет пробелы и заменяет запятые на точки для корректного преобразования в число.

    Args:
        text (str | None): Строка, содержащая числовое значение валюты.

    Returns:
        float | None: Числовое значение валюты или None, если преобразование невозможно.
    """
    if not text: return None
    try:
        # Удаляем пробелы и заменяем запятую на точку для float-преобразования
        cleaned = str(text).replace(' ', '').replace(',', '.')
        return float(cleaned)
    except Exception:
        return None

def process_bilaga_upload(file, company_id, base_upload_path):
    """
    Обрабатывает загруженный файл квитанции (bilaga).

    Сохраняет файл, парсит его (если это PDF), извлекает метаданные
    и создает новую запись Bilaga в базе данных.

    Args:
        file (FileStorage): Объект файла, загруженный через Flask request.
        company_id (int): ID компании, к которой относится квитанция.
        base_upload_path (str): Базовый путь для сохранения файлов.

    Returns:
        Bilaga: Созданный и сохраненный объект Bilaga.
    """
    # Сохраняем файл квитанции на диск
    filename, relative_filepath, absolute_filepath = save_bilaga_file(
        file, company_id, base_upload_path
    )
    
    parsed_data = None
    # Если файл является PDF, пытаемся извлечь данные с помощью парсера
    if filename.lower().endswith('.pdf'):
        try:
            parsed_data = parse_xl_jbm_invoice(absolute_filepath)
        except Exception as e:
            # Логируем ошибку парсинга, но не прерываем процесс
            print(f"--- Warning: PDF parser failed for {filename}. Error: {e} ---")

    # Создаем новый объект Bilaga
    new_bilaga = Bilaga(
        company_id=company_id,
        filename=filename,
        filepath=relative_filepath,
        status='unassigned' # Новая квитанция изначально неприсвоена
    )
    
    # Если данные успешно извлечены из PDF, заполняем поля Bilaga
    if parsed_data:
        # Извлекаем и очищаем суммы. Используем 'att_betala' как запасной вариант для brutto.
        brutto = helper_clean_currency(parsed_data.get('total_brutto'))
        if not brutto:
             brutto = helper_clean_currency(parsed_data.get('att_betala'))
        
        netto = helper_clean_currency(parsed_data.get('total_netto'))
        
        final_moms = None
        # Если есть brutto и netto, вычисляем moms. Это более надежно.
        if brutto is not None and netto is not None:
            final_moms = round(brutto - netto, 2)
        else:
            # Иначе берем moms напрямую из парсера (менее надежно)
            final_moms = helper_clean_currency(parsed_data.get('total_moms'))

        # Присваиваем извлеченные суммы объекту Bilaga
        new_bilaga.brutto_amount = brutto
        new_bilaga.netto_amount = netto
        new_bilaga.moms_amount = final_moms

        # Извлекаем и присваиваем даты, номера счетов и OCR
        new_bilaga.fakturadatum = datetime.strptime(parsed_data['fakturadatum'], '%Y-%m-%d').date() if parsed_data.get('fakturadatum') else None
        new_bilaga.forfallodag = datetime.strptime(parsed_data['forfallodag'], '%Y-%m-%d').date() if parsed_data.get('forfallodag') else None
        new_bilaga.fakturanr = parsed_data.get('fakturanr')
        new_bilaga.ocr = parsed_data.get('ocr')

        # Извлекаем данные продавца
        saljare = parsed_data.get('saljare', {})
        new_bilaga.saljare_namn = saljare.get('namn')
        new_bilaga.saljare_orgnr = saljare.get('orgnr')
        new_bilaga.saljare_bankgiro = saljare.get('bankgiro')

        # Извлекаем данные клиента
        kund = parsed_data.get('kund', {})
        new_bilaga.kund_namn = kund.get('namn')
        new_bilaga.kund_orgnr = kund.get('orgnr')
        new_bilaga.kund_nummer = kund.get('kundnummer')
        
        # Пытаемся угадать счет (konto) на основе содержимого заказа или имени продавца
        if parsed_data.get('orders') and parsed_data['orders'][0]['items']:
            first_item_name = parsed_data['orders'][0]['items'][0].get('benamning', '').lower()
            for key, konto_nr in ASSOCIATION_MAP.items():
                if key in first_item_name:
                    new_bilaga.suggested_konto = konto_nr
                    break
        
        # Если счет не угадан по заказу, пробуем по имени продавца
        if not new_bilaga.suggested_konto and new_bilaga.saljare_namn:
             fn_lower = new_bilaga.saljare_namn.lower()
             for key, konto_nr in ASSOCIATION_MAP.items():
                if key in fn_lower:
                    new_bilaga.suggested_konto = konto_nr
                    break

    db.session.add(new_bilaga) # Добавляем новый объект Bilaga в сессию базы данных
    db.session.commit() # Сохраняем изменения в базу данных
    
    return new_bilaga # Возвращаем созданный объект


def update_bilaga_metadata_service(bilaga_id, data):
    """
    Обновляет метаданные существующей квитанции (Bilaga).

    Args:
        bilaga_id (int): ID квитанции для обновления.
        data (dict): Словарь с новыми метаданными.

    Returns:
        Bilaga: Обновленный объект Bilaga.
    """
    # Находим квитанцию по ID, или выбрасываем 404 ошибку
    bilaga = Bilaga.query.get_or_404(bilaga_id)
    
    # Обновляем даты и номера
    bilaga.fakturadatum = datetime.strptime(data['fakturadatum'], '%Y-%m-%d').date() if data.get('fakturadatum') else None
    bilaga.forfallodag = datetime.strptime(data['forfallodag'], '%Y-%m-%d').date() if data.get('forfallodag') else None
    bilaga.fakturanr = data.get('fakturanr')
    bilaga.ocr = data.get('ocr')
    
    # Обновляем данные продавца
    bilaga.saljare_namn = data.get('saljare_namn')
    bilaga.saljare_orgnr = data.get('saljare_orgnr')
    bilaga.saljare_bankgiro = data.get('saljare_bankgiro')
    
    # Обновляем данные клиента
    bilaga.kund_namn = data.get('kund_namn')
    bilaga.kund_orgnr = data.get('kund_orgnr')
    bilaga.kund_nummer = data.get('kund_nummer')
    
    # Очищаем и обновляем суммы
    brutto = helper_clean_currency(data.get('brutto_amount'))
    moms = helper_clean_currency(data.get('moms_amount'))
    
    bilaga.brutto_amount = brutto
    bilaga.moms_amount = moms
    
    # Пересчитываем netto на основе brutto и moms для обеспечения консистентности
    if brutto is not None and moms is not None:
         bilaga.netto_amount = round(brutto - moms, 2)
    
    # Обновляем предложенный счет
    bilaga.suggested_konto = data.get('suggested_konto')
        
    db.session.commit() # Сохраняем все изменения в базу данных
    return bilaga # Возвращаем обновленный объект


def bokfor_bilaga_service(bilaga_id, entries_data):
    """
    Проводит бухгалтерскую операцию для квитанции.

    Создает новую банковскую транзакцию (как "ручную" верификацию),
    создает бухгалтерские проводки на основе предоставленных данных,
    и связывает их с квитанцией, меняя ее статус на 'assigned'.

    Args:
        bilaga_id (int): ID квитанции для проводки.
        entries_data (list): Список словарей, каждый из которых содержит данные для BookkeepingEntry
                             (konto, debet, kredit).

    Returns:
        int: ID созданной банковской транзакции (верификации).

    Raises:
        Exception: Если квитанция уже была проведена или если проводки несбалансированы.
    """
    # 1. Проверка статуса квитанции
    bilaga = Bilaga.query.get_or_404(bilaga_id)
    if bilaga.status == 'assigned':
        raise Exception('Denna bilaga är redan bokförd.') # Квитанция уже проведена

    # 2. Валидация баланса проводок
    # Суммируем дебеты и кредиты из предоставленных данных
    total_debet = sum(helper_clean_currency(e.get('debet', 0)) for e in entries_data)
    total_kredit = sum(helper_clean_currency(e.get('kredit', 0)) for e in entries_data)

    # Проверяем, что дебет равен кредиту (с небольшой погрешностью для float) и не равен нулю
    if not math.isclose(total_debet, total_kredit, abs_tol=0.01) or total_debet == 0:
        raise Exception(f'Obalans! Debet ({total_debet}) matchar inte Kredit ({total_kredit}).')

    # 3. Создаем "ручную" (не-банковскую) верификацию
    # Это специальная транзакция, которая не влияет на реальный банковский счет,
    # но служит контейнером для бухгалтерских проводок, связанных с квитанцией.
    manual_ver = BankTransaction(
        company_id=bilaga.company_id,
        # Используем дату квитанции или текущую дату, если дата квитанции отсутствует
        bokforingsdag=bilaga.fakturadatum or datetime.now().date(),
        referens=f"Faktura: {bilaga.filename}",
        belopp=0.00,  # Сумма 0.00, так как это не реальная банковская операция
        status='processed'  # Сразу помечаем как обработанную
    )
    db.session.add(manual_ver)
    db.session.flush()  # Получаем ID новой верификации

    # 4. Создаем строки бухгалтерии (BookkeepingEntry) на основе данных из модального окна
    for entry in entries_data:
        if entry.get('konto'): # Убеждаемся, что счет указан
            new_entry = BookkeepingEntry(
                bank_transaction_id=manual_ver.id, # Привязываем к созданной верификации
                konto=entry['konto'],
                debet=helper_clean_currency(entry.get('debet', 0)),
                kredit=helper_clean_currency(entry.get('kredit', 0))
            )
            db.session.add(new_entry)

    # 5. Привязываем квитанцию к верификации и обновляем ее статус
    bilaga.bank_transaction_id = manual_ver.id
    bilaga.status = 'assigned' # Квитанция теперь присвоена и обработана

    db.session.commit() # Сохраняем все изменения в базу данных
    return manual_ver.id # Возвращаем ID новой верификации

def delete_bilaga_service(bilaga_id):
    """
    Удаляет квитанцию (Bilaga) и связанный с ней файл.

    Args:
        bilaga_id (int): ID квитанции для удаления.
    """
    bilaga = Bilaga.query.get_or_404(bilaga_id)
    
    # Составляем путь к файлу для удаления
    file_to_delete = os.path.join(current_app.config['UPLOAD_FOLDER'], bilaga.filepath)
    if os.path.exists(file_to_delete):
        os.remove(file_to_delete)
    
    # Удаляем запись из базы данных
    db.session.delete(bilaga)
    db.session.commit()
