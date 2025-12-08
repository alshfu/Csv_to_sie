# -*- coding: utf-8 -*-

import pandas as pd
from datetime import datetime
import math
import os
import json
from flask import current_app, flash
from bokforing_app import db
from bokforing_app.models import BankTransaction, BookkeepingEntry, Bilaga, Konto, Association
from bokforing_app.services.accounting_config import KONTOPLAN, ASSOCIATION_MAP
from bokforing_app.services.pdf_reader import extract_exact_json_from_pdf
from bokforing_app.services.file_service import save_bilaga_file


def get_company_data(company_id):
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
    return BankTransaction.query.filter_by(
        company_id=company_id,
        status='processed'
    ).order_by(BankTransaction.bokforingsdag.desc()).all()


def get_all_bilagor(company_id):
    return Bilaga.query.filter_by(
        company_id=company_id
    ).order_by(Bilaga.status.asc(), Bilaga.fakturadatum.desc()).all()


def process_csv_upload(file, company_id):
    """
    Bearbetar en uppladdad CSV-fil. Försöker först med det gamla formatet (semikolon-separerad),
    sedan med det nya formatet (komma-separerad).
    Nya transaktioner importeras som 'unprocessed'.
    Dubbletter flaggas som 'pending_duplicate' för manuell granskning.
    """
    try:
        # Försök med det gamla formatet
        file.seek(0)
        df = pd.read_csv(file, sep=';', header=1, decimal=',', encoding='latin-1', quoting=1)
        df = df.dropna(subset=['Bokföringsdag'])
        column_map = {'Bokföringsdag': 'bokforingsdag', 'Referens': 'referens', 'Insättning/Uttag': 'belopp'}
    except Exception:
        try:
            # Försök med det nya formatet
            file.seek(0)
            df = pd.read_csv(file, sep=',', header=None, decimal='.', encoding='utf-8', quoting=1)
            df.columns = ['bokforingsdag', 'referens', 'belopp', 'valuta', 'saldo']
            column_map = {'bokforingsdag': 'bokforingsdag', 'referens': 'referens', 'belopp': 'belopp'}
        except Exception as e:
            raise ValueError(f"Kunde inte läsa CSV-filen med något av de kända formaten. Fel: {e}")

    new_transactions_count = 0
    duplicates_found_count = 0

    existing_transactions = db.session.query(
        BankTransaction.bokforingsdag,
        BankTransaction.referens,
        BankTransaction.belopp
    ).filter_by(company_id=company_id).all()
    
    existing_set = set((t.bokforingsdag, t.referens, t.belopp) for t in existing_transactions)

    for _, row in df.iterrows():
        try:
            bokforingsdag = datetime.strptime(str(row[column_map['bokforingsdag']]), '%Y-%m-%d').date()
            belopp = round(float(row[column_map['belopp']]), 2)
            referens = str(row[column_map['referens']])

            current_transaction_tuple = (bokforingsdag, referens, belopp)
            is_duplicate = current_transaction_tuple in existing_set

            new_trans = BankTransaction(
                company_id=company_id,
                bokforingsdag=bokforingsdag,
                referens=referens,
                belopp=belopp,
                status='pending_duplicate' if is_duplicate else 'unprocessed'
            )
            db.session.add(new_trans)
            
            if is_duplicate:
                duplicates_found_count += 1
            else:
                new_transactions_count += 1
                existing_set.add(current_transaction_tuple)

        except (ValueError, TypeError, KeyError) as e:
            current_app.logger.warning(f"Hoppar över ogiltig rad i CSV: {row}. Fel: {e}")
            continue

    db.session.commit()
    
    return {
        "new": new_transactions_count,
        "duplicates": duplicates_found_count
    }


def helper_clean_currency(text):
    if not text: return None
    try:
        cleaned = str(text).replace(' ', '').replace(',', '.')
        return float(cleaned)
    except (ValueError, TypeError):
        return None

def process_bilaga_upload(file, company_id, base_upload_path):
    filename, relative_filepath, absolute_filepath = save_bilaga_file(
        file, company_id, base_upload_path
    )
    
    parsed_data = None
    if filename.lower().endswith('.pdf'):
        try:
            json_string = extract_exact_json_from_pdf(absolute_filepath)
            parsed_data = json.loads(json_string)
            if 'error' in parsed_data:
                print(f"--- Gemini AI Error for {filename}: {parsed_data['error']} ---")
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
        new_bilaga.fakturanr = parsed_data.get('fakturanr')
        new_bilaga.ocr = parsed_data.get('ocr')
        brutto = helper_clean_currency(parsed_data.get('total_brutto')) or helper_clean_currency(parsed_data.get('att_betala'))
        netto = helper_clean_currency(parsed_data.get('total_netto'))
        final_moms = round(brutto - netto, 2) if brutto is not None and netto is not None else helper_clean_currency(parsed_data.get('total_moms'))
        new_bilaga.brutto_amount = brutto
        new_bilaga.netto_amount = netto
        new_bilaga.moms_amount = final_moms
        try:
            new_bilaga.fakturadatum = datetime.strptime(parsed_data.get('fakturadatum'), '%Y-%m-%d').date() if parsed_data.get('fakturadatum') else None
            new_bilaga.forfallodag = datetime.strptime(parsed_data.get('forfallodag'), '%Y-%m-%d').date() if parsed_data.get('forfallodag') else None
        except (ValueError, TypeError):
            pass
        
        saljare = parsed_data.get('saljare', {})
        new_bilaga.saljare_namn = saljare.get('namn')

    db.session.add(new_bilaga)
    db.session.commit()
    
    return new_bilaga

def update_bilaga_metadata_service(bilaga_id, data):
    bilaga = Bilaga.query.get_or_404(bilaga_id)
    bilaga.fakturadatum = datetime.strptime(data['fakturadatum'], '%Y-%m-%d').date() if data.get('fakturadatum') else None
    bilaga.forfallodag = datetime.strptime(data['forfallodag'], '%Y-%m-%d').date() if data.get('forfallodag') else None
    bilaga.fakturanr = data.get('fakturanr')
    bilaga.ocr = data.get('ocr')
    brutto = helper_clean_currency(data.get('total_brutto'))
    moms = helper_clean_currency(data.get('total_moms'))
    bilaga.brutto_amount = brutto
    bilaga.moms_amount = moms
    if brutto is not None and moms is not None:
         bilaga.netto_amount = round(brutto - moms, 2)
    bilaga.suggested_konto = data.get('suggested_konto')
    db.session.commit()
    return bilaga

def bokfor_bilaga_service(bilaga_id, entries_data):
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
