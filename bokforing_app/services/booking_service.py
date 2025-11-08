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
import json
from flask import current_app
from bokforing_app import db
from bokforing_app.models import BankTransaction, BookkeepingEntry, Bilaga
from bokforing_app.services.accounting_config import KONTOPLAN, ASSOCIATION_MAP, get_contra_account
from bokforing_app.services.pdf_reader import extract_exact_json_from_pdf
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
    transactions = BankTransaction.query.filter_by(
        company_id=company_id,
        status='unprocessed'
    ).order_by(BankTransaction.bokforingsdag.desc()).all()

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
    """
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
        db.session.flush()

        if amount > 0:
            entry_bank = BookkeepingEntry(bank_transaction_id=new_trans.id, konto='1930', debet=amount, kredit=0)
            entry_contra = BookkeepingEntry(bank_transaction_id=new_trans.id, konto=contra_konto, debet=0, kredit=amount)
        else:
            entry_bank = BookkeepingEntry(bank_transaction_id=new_trans.id, konto='1930', debet=0, kredit=-amount)
            entry_contra = BookkeepingEntry(bank_transaction_id=new_trans.id, konto=contra_konto, debet=-amount, kredit=0)

        db.session.add_all([entry_bank, entry_contra])

    db.session.commit()


# --- Логика для обработки квитанций (Bilaga) ---

def helper_clean_currency(text):
    """
    Вспомогательная функция для очистки и преобразования строкового представления валюты в float.
    """
    if not text: return None
    try:
        cleaned = str(text).replace(' ', '').replace(',', '.')
        return float(cleaned)
    except (ValueError, TypeError):
        return None

def process_bilaga_upload(file, company_id, base_upload_path):
    """
    Обрабатывает загруженный файл квитанции, используя Gemini AI для извлечения данных.
    """
    filename, relative_filepath, absolute_filepath = save_bilaga_file(
        file, company_id, base_upload_path
    )
    
    parsed_data = None
    if filename.lower().endswith('.pdf'):
        try:
            # Вызываем новую функцию, которая возвращает JSON-строку
            json_string = extract_exact_json_from_pdf(absolute_filepath)
            # Парсим JSON-строку в словарь Python
            parsed_data = json.loads(json_string)
            if 'error' in parsed_data:
                print(f"--- Gemini AI Error for {filename}: {parsed_data['error']} ---")
                # В случае ошибки от AI, создаем "пустую" квитанцию
                parsed_data = {"saljare": {"namn": "Okänd bilaga (AI Error)"}}

        except Exception as e:
            print(f"--- Critical Error during PDF processing for {filename}: {e} ---")
            parsed_data = {"saljare": {"namn": "Okänd bilaga (Processing Error)"}}

    new_bilaga = Bilaga(
        company_id=company_id,
        filename=filename,
        filepath=relative_filepath,
        status='unassigned'
    )
    
    if parsed_data:
        brutto = helper_clean_currency(parsed_data.get('total_brutto'))
        if not brutto:
             brutto = helper_clean_currency(parsed_data.get('att_betala'))
        
        netto = helper_clean_currency(parsed_data.get('total_netto'))
        
        final_moms = None
        if brutto is not None and netto is not None:
            final_moms = round(brutto - netto, 2)
        else:
            final_moms = helper_clean_currency(parsed_data.get('total_moms'))

        new_bilaga.brutto_amount = brutto
        new_bilaga.netto_amount = netto
        new_bilaga.moms_amount = final_moms

        fakturadatum_str = parsed_data.get('fakturadatum')
        if fakturadatum_str:
            try:
                new_bilaga.fakturadatum = datetime.strptime(fakturadatum_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                new_bilaga.fakturadatum = None

        forfallodag_str = parsed_data.get('forfallodag')
        if forfallodag_str:
            try:
                new_bilaga.forfallodag = datetime.strptime(forfallodag_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                new_bilaga.forfallodag = None

        new_bilaga.fakturanr = parsed_data.get('fakturanr')
        new_bilaga.ocr = parsed_data.get('ocr')

        saljare = parsed_data.get('saljare', {})
        new_bilaga.saljare_namn = saljare.get('namn')
        new_bilaga.saljare_orgnr = saljare.get('orgnr')
        new_bilaga.saljare_bankgiro = saljare.get('bankgiro')

        kund = parsed_data.get('kund', {})
        new_bilaga.kund_namn = kund.get('namn')
        new_bilaga.kund_orgnr = kund.get('orgnr')
        new_bilaga.kund_nummer = kund.get('kundnummer')
        
        orders = parsed_data.get('orders', [])
        if orders and isinstance(orders, list) and len(orders) > 0 and isinstance(orders[0], dict) and orders[0].get('items'):
            first_item_name = orders[0]['items'][0].get('benamning', '').lower()
            for key, konto_nr in ASSOCIATION_MAP.items():
                if key in first_item_name:
                    new_bilaga.suggested_konto = konto_nr
                    break
        
        if not new_bilaga.suggested_konto and new_bilaga.saljare_namn:
             fn_lower = new_bilaga.saljare_namn.lower()
             for key, konto_nr in ASSOCIATION_MAP.items():
                if key in fn_lower:
                    new_bilaga.suggested_konto = konto_nr
                    break

    db.session.add(new_bilaga)
    db.session.commit()
    
    return new_bilaga


def update_bilaga_metadata_service(bilaga_id, data):
    """
    Обновляет метаданные существующей квитанции (Bilaga).
    """
    bilaga = Bilaga.query.get_or_404(bilaga_id)
    
    bilaga.fakturadatum = datetime.strptime(data['fakturadatum'], '%Y-%m-%d').date() if data.get('fakturadatum') else None
    bilaga.forfallodag = datetime.strptime(data['forfallodag'], '%Y-%m-%d').date() if data.get('forfallodag') else None
    bilaga.fakturanr = data.get('fakturanr')
    bilaga.ocr = data.get('ocr')
    
    bilaga.saljare_namn = data.get('saljare_namn')
    bilaga.saljare_orgnr = data.get('saljare_orgnr')
    bilaga.saljare_bankgiro = data.get('saljare_bankgiro')
    
    bilaga.kund_namn = data.get('kund_namn')
    bilaga.kund_orgnr = data.get('kund_orgnr')
    bilaga.kund_nummer = data.get('kund_nummer')
    
    brutto = helper_clean_currency(data.get('brutto_amount'))
    moms = helper_clean_currency(data.get('moms_amount'))
    
    bilaga.brutto_amount = brutto
    bilaga.moms_amount = moms
    
    if brutto is not None and moms is not None:
         bilaga.netto_amount = round(brutto - moms, 2)
    
    bilaga.suggested_konto = data.get('suggested_konto')
        
    db.session.commit()
    return bilaga


def bokfor_bilaga_service(bilaga_id, entries_data):
    """
    Проводит бухгалтерскую операцию для квитанции.
    """
    bilaga = Bilaga.query.get_or_404(bilaga_id)
    if bilaga.status == 'assigned':
        raise Exception('Denna bilaga är redan bokförd.')

    total_debet = sum(helper_clean_currency(e.get('debet', 0)) for e in entries_data)
    total_kredit = sum(helper_clean_currency(e.get('kredit', 0)) for e in entries_data)

    if not math.isclose(total_debet, total_kredit, abs_tol=0.01) or total_debet == 0:
        raise Exception(f'Obalans! Debet ({total_debet}) matchar inte Kredit ({total_kredit}).')

    manual_ver = BankTransaction(
        company_id=bilaga.company_id,
        bokforingsdag=bilaga.fakturadatum or datetime.now().date(),
        referens=f"Faktura: {bilaga.filename}",
        belopp=0.00,
        status='processed'
    )
    db.session.add(manual_ver)
    db.session.flush()

    for entry in entries_data:
        if entry.get('konto'):
            new_entry = BookkeepingEntry(
                bank_transaction_id=manual_ver.id,
                konto=entry['konto'],
                debet=helper_clean_currency(entry.get('debet', 0)),
                kredit=helper_clean_currency(entry.get('kredit', 0))
            )
            db.session.add(new_entry)

    bilaga.bank_transaction_id = manual_ver.id
    bilaga.status = 'assigned'

    db.session.commit()
    return manual_ver.id

def delete_bilaga_service(bilaga_id):
    """
    Удаляет квитанцию (Bilaga) и связанный с ней файл.
    """
    bilaga = Bilaga.query.get_or_404(bilaga_id)
    
    file_to_delete = os.path.join(current_app.config['UPLOAD_FOLDER'], bilaga.filepath)
    if os.path.exists(file_to_delete):
        os.remove(file_to_delete)
    
    db.session.delete(bilaga)
    db.session.commit()
