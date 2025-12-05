# -*- coding: utf-8 -*-
"""
Service för att kommunicera med Google Gemini API.

Denna modul ansvarar för all interaktion med Googles generativa AI-modell, Gemini.
Den bygger upp specifika prompts för att få bokföringsförslag för transaktioner, fakturor och bilagor.
Modulen inkluderar även en robust retry-mekanism för att hantera instabila nätverksanslutningar.
"""
import os
import json
import time
from typing import Dict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import ConnectionError, ProxyError
from flask import current_app
from bokforing_app.models import BankTransaction, Invoice, Bilaga
from bokforing_app.services.accounting_config import KONTOPLAN
from bokforing_app.services import proxy_service


def requests_retry_session(
    retries=5,
    backoff_factor=1,
    status_forcelist=(500, 502, 503, 504),
    session=None,
):
    """
    Skapar en `requests.Session` som automatiskt försöker igen vid nätverksfel.
    """
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["POST", "GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def _call_gemini_api(prompt: str, use_proxy: bool = True) -> Dict:
    """
    Gör det faktiska anropet till Gemini API med en given prompt.
    Inkluderar fallback till ingen proxy vid nätverksfel.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        error_msg = "GEMINI_API_KEY är inte satt i systemmiljön."
        current_app.logger.error(error_msg)
        return {"error": error_msg}

    proxies = proxy_service.get_proxies() if use_proxy else None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    session = requests_retry_session()
    if proxies:
        session.proxies = proxies

    start_time = time.time()

    # --- LOGGNING: Skriv ut frågan till konsolen ---
    print("========================================================")
    print(f"--- FRÅGA TILL GEMINI API (Proxy: {'Ja' if use_proxy else 'Nej'}) ---")
    print(prompt)
    print("========================================================")

    try:
        response = session.post(url, json=payload, timeout=120)
        response.raise_for_status()

        duration = time.time() - start_time
        api_response = response.json()
        text_response = api_response['candidates'][0]['content']['parts'][0]['text']

        cleaned_text = text_response.replace("```json", "").replace("```", "").strip()
        parsed_json = json.loads(cleaned_text)

        # --- LOGGNING: Skriv ut svaret till konsolen ---
        print("========================================================")
        print(f"--- SVAR FRÅN GEMINI API (Tid: {duration:.2f}s) ---")
        print(json.dumps(parsed_json, indent=2, ensure_ascii=False))
        print("========================================================")

        if 'suggestion' not in parsed_json:
            raise json.JSONDecodeError("Svaret saknar 'suggestion'.", cleaned_text, 0)

        return parsed_json

    except (ProxyError, ConnectionError) as e:
        if use_proxy:
            current_app.logger.warning(f"Proxy-relaterat fel i Gemini-anrop: {e}. Försöker igen utan proxy.")
            return _call_gemini_api(prompt, use_proxy=False)
        else:
            error_msg = f"Nätverksfel utan proxy i Gemini-anrop: {e}"
            current_app.logger.error(error_msg)
            return {"error": error_msg}
    except requests.exceptions.RequestException as e:
        error_msg = f"Anrop till Gemini API misslyckades: {e}"
        current_app.logger.error(error_msg)
        return {"error": error_msg}
    except (KeyError, IndexError) as e:
        error_msg = (f"Oväntat API-svarformat: "
                     f"{response.text if 'response' in locals() else 'Inget svar'} - {e}")
        current_app.logger.error(error_msg)
        return {"error": error_msg}
    except json.JSONDecodeError as e:
        error_msg = f"AI returnerade ogiltig JSON: {e.msg} - Svar: {e.doc}"
        current_app.logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Ett oväntat fel inträffade: {str(e)}"
        current_app.logger.error(error_msg)
        return {"error": error_msg}

def _build_prompt_for_invoice(invoice: Invoice, general_rules: str) -> str:
    """
    Bygger en anpassad prompt för fakturor, baserat på metod och typ.
    """
    relevant_konton = {
        '1510': 'Kundfordringar',
        '1930': 'Företagskonto',
        '2611': 'Utgående moms 25%',
        '2612': 'Utgående moms 12%',
        '2613': 'Utgående moms 6%',
        '3001': 'Försäljning 25% moms',
        '3002': 'Försäljning 12% moms',
        '3003': 'Försäljning 6% moms'
    }
    if invoice.reverse_charge:
        relevant_konton['3231'] = 'Försäljning omvänd skattskyldighet'

    relevant_kontoplan_str = "\n".join([f"{k} - {v}" for k, v in relevant_konton.items()])

    if invoice.company.accounting_method == 'faktura':
        method_instructions = (
            "- Använd fakturametoden: Bokför kundfordran (1510) på fakturadatum, utgående moms (261x) och försäljning (300x)."
        )
    else:  # kontant
        method_instructions = (
            "- Använd kontantmetoden: Bokför direkt mot bankkonto (1930) på betalningsdatum, utgående moms (261x) och försäljning (300x)."
        )

    reverse_charge_instructions = (
        "- Omvänd skattskyldighet: Inga utgående moms; använd försäljningskonto för omvänd skatt (t.ex. 3231)." if invoice.reverse_charge else ""
    )

    prompt = f"""Analysera kundfakturan och skapa ett bokföringsförslag. Svara ENDAST med JSON-objekt med nyckel: "suggestion" (inkludera "description" och "entries" med "account", "debit", "credit"). Belopp måste balansera exakt.

Tillgängliga konton (använd endast dessa, anpassat för försäljning):
{relevant_kontoplan_str}

Allmänna regler:
{general_rules}

Instruktioner för bokföringsmetod:
{method_instructions}

Instruktioner för moms och omvänd skattskyldighet:
- Fakturan anses momsbelagd: Inkludera alltid utgående moms (261x) baserat på momsbelopp, om inte omvänd skattskyldighet gäller.
{reverse_charge_instructions}

Fakturadata:
- Nummer: {invoice.number}
- Kund: {invoice.client.name if invoice.client else 'Okänd'}
- Datum: {invoice.date.strftime('%Y-%m-%d')}
- Betaldatum: {invoice.paid_at or 'Ej betald'}
- Summa (inkl. moms): {invoice.sum} SEK
- Moms: {invoice.tax} SEK
- Netto: {invoice.net} SEK
- Omvänd skattskyldighet: {'Ja' if invoice.reverse_charge else 'Nej'}

Exempel (1250 SEK, 1000 netto + 250 moms, fakturametod):
{{"suggestion": {{"description": "Faktura {invoice.number} - {invoice.client.name}", "entries": [{{"account": "1510", "debit": 1250.00, "credit": 0}}, {{"account": "2611", "debit": 0, "credit": 250.00}}, {{"account": "3001", "debit": 0, "credit": 1000.00}}]}}}}
"""
    return prompt

def _build_prompt_for_transaction(transaction: BankTransaction, general_rules: str, specific_rule: str) -> str:
    """
    Bygger en anpassad prompt för transaktioner.
    """
    relevant_konton = {k: v for k, v in KONTOPLAN.items() if k.startswith(('3', '4', '5', '6', '19'))}  # Intäkter, kostnader, bank

    prompt = f"""Analysera banktransaktionen och skapa ett bokföringsförslag. Svara ENDAST med JSON-objekt med nycklar: "suggestion" och "rule".

"suggestion": Konkret förslag för denna transaktion (inkludera "description", "entries" med "account", "debit", "credit"). Belopp måste balansera.

"rule": Generell regel för liknande transaktioner (använd "ABS_AMOUNT" och "ORIGINAL_AMOUNT" i "entries").

Tillgängliga konton (använd endast dessa):
{"\n".join([f"{k} - {v}" for k, v in relevant_konton.items()])}

Specifik regel (om finns):
{specific_rule}

Allmänna regler:
{general_rules}

Transaktionsdata:
- Datum: {transaction.bokforingsdag.strftime('%Y-%m-%d')}
- Referens: "{transaction.referens}"
- Belopp: {transaction.belopp} SEK

Instruktioner:
- Transaktion anses momsbelagd: Inkludera alltid moms (ingående/utgående) baserat på belopp, om relevant.
- Kreditera '1930' vid negativt belopp (utbetalning).
- Debet '1930' vid positivt belopp (inbetalning).
"""
    return prompt

def _build_prompt_for_bilaga(bilaga: Bilaga, general_rules: str) -> str:
    """
    Bygger en anpassad prompt för bilagor (underlag, t.ex. leverantörsfakturor).
    """
    relevant_konton = {k: v for k, v in KONTOPLAN.items() if k.startswith(('4', '5', '6', '26', '19'))}  # Kostnader, ingående moms, bank/fordringar

    if bilaga.company.accounting_method == 'faktura':
        method_instructions = (
            "- Använd fakturametoden: Bokför leverantörsskuld (2440) på fakturadatum, ingående moms (264x) och kostnad (4xxx–6xxx)."
        )
    else:  # kontant
        method_instructions = (
            "- Använd kontantmetoden: Bokför direkt mot bankkonto (1930) på betalningsdatum, ingående moms (264x) och kostnad (4xxx–6xxx)."
        )

    reverse_charge_instructions = (
        "- Omvänd skattskyldighet: Bokför utgående moms som ingående (t.ex. 2614/2645); använd kostnadskonto för omvänd skatt." if bilaga.omvand_skattskyldighet else ""
    )

    prompt = f"""Analysera underlaget (leverantörsfaktura) och skapa ett bokföringsförslag. Svara ENDAST med JSON-objekt med nyckel: "suggestion" (inkludera "description" och "entries" med "account", "debit", "credit"). Belopp måste balansera.

Tillgängliga konton (använd endast dessa, anpassat för inköp):
{"\n".join([f"{k} - {v}" for k, v in relevant_konton.items()])}

Allmänna regler:
{general_rules}

Instruktioner för bokföringsmetod:
{method_instructions}

Instruktioner för moms och omvänd skattskyldighet:
- Underlaget anses momsbelagt: Inkludera alltid ingående moms (264x) baserat på momsbelopp, om inte omvänd skattskyldighet gäller.
{reverse_charge_instructions}

Underlagsdata:
- Fakturanr: {bilaga.fakturanr or 'N/A'}
- Datum: {bilaga.fakturadatum.strftime('%Y-%m-%d') if bilaga.fakturadatum else 'N/A'}
- Förfallodag: {bilaga.forfallodag.strftime('%Y-%m-%d') if bilaga.forfallodag else 'N/A'}
- Brutto: {bilaga.brutto_amount} SEK
- Moms: {bilaga.moms_amount} SEK
- Netto: {bilaga.netto_amount} SEK
- Omvänd skattskyldighet: {'Ja' if bilaga.omvand_skattskyldighet else 'Nej'}

Exempel (1250 SEK, 1000 netto + 250 moms, fakturametod):
{{"suggestion": {{"description": "Leverantörsfaktura {bilaga.fakturanr}", "entries": [{{"account": "2440", "debit": 0, "credit": 1250.00}}, {{"account": "2641", "debit": 250.00, "credit": 0}}, {{"account": "5010", "debit": 1000.00, "credit": 0}}]}}}}
"""
    return prompt

def get_suggestion_for_invoice(invoice: Invoice, general_rules: str) -> Dict:
    """
    Bygger en prompt för en kundfaktura och anropar Gemini API.
    """
    prompt = _build_prompt_for_invoice(invoice, general_rules)
    return _call_gemini_api(prompt)

def get_bokforing_suggestion_from_gemini(transaction: BankTransaction, general_rules: str, specific_rule: str) -> Dict:
    """
    Bygger en prompt för en banktransaktion och ber om både ett förslag och en regel.
    """
    prompt = _build_prompt_for_transaction(transaction, general_rules, specific_rule)
    gemini_response = _call_gemini_api(prompt)
    if 'suggestion' in gemini_response and 'rule' not in gemini_response:
        current_app.logger.warning("Gemini returnerade en suggestion men ingen regel för en transaktion.")
        gemini_response['rule'] = {'description': 'Generell regel ej skapad', 'entries': []}

    return gemini_response

def get_suggestion_for_bilaga(bilaga: Bilaga, general_rules: str) -> Dict:
    """
    Bygger en prompt för ett underlag (bilaga) och anropar Gemini API.
    """
    prompt = _build_prompt_for_bilaga(bilaga, general_rules)
    return _call_gemini_api(prompt)
