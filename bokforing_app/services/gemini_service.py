# -*- coding: utf-8 -*-
import os
import json
from typing import Dict
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from flask import current_app
from bokforing_app.models import BankTransaction, Invoice
from bokforing_app.services.accounting_config import KONTOPLAN

def requests_retry_session(
    retries=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 503, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def _call_gemini_api(prompt: str) -> Dict:
    """Generic function to call the Gemini API with a given prompt."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        error_msg = "GEMINI_API_KEY är inte satt i systemmiljön."
        current_app.logger.error(error_msg)
        return {"error": error_msg}

    proxy_url = os.getenv("SOCKS5_PROXY")
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    session = requests_retry_session()
    session.proxies = proxies

    try:
        response = session.post(url, json=payload, timeout=90)
        response.raise_for_status()

        api_response = response.json()
        text_response = api_response['candidates'][0]['content']['parts'][0]['text']
        
        cleaned_text = text_response.replace("```json", "").replace("```", "").strip()
        parsed_json = json.loads(cleaned_text)
        if 'suggestion' not in parsed_json:
            raise json.JSONDecodeError("Svaret saknar 'suggestion'.", cleaned_text, 0)
        
        return parsed_json

    except requests.exceptions.RequestException as e:
        error_msg = f"Anrop till Gemini API misslyckades: {e}"
        current_app.logger.error(error_msg)
        return {"error": error_msg}
    except (KeyError, IndexError) as e:
        error_msg = f"Oväntat API-svarformat: {response.text if 'response' in locals() else 'Inget svar'} - {e}"
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

def get_suggestion_for_invoice(invoice: Invoice, general_rules: str) -> Dict:
    """
    Bygger en prompt för en faktura och anropar Gemini API.
    """
    kontoplan_str = "\n".join([f"{k} - {v}" for k, v in KONTOPLAN.items()])
    
    # Bestäm bokföringsdatum och primärt konto baserat på redovisningsmetod
    if invoice.company.accounting_method == 'faktura':
        bokforingsdatum = invoice.date.strftime('%Y-%m-%d')
        method_instructions = f"""
        - Företaget använder FAKTURAMETODEN.
        - Bokför en kundfordran på konto 1510.
        - Bokföringsdatum ska vara fakturadatumet ({bokforingsdatum}).
        """
    else: # kontant
        bokforingsdatum = (invoice.paid_at or invoice.date).strftime('%Y-%m-%d')
        method_instructions = f"""
        - Företaget använder KONTANTMETODEN.
        - Bokför betalningen direkt mot ett tillgångskonto, vanligtvis 1930 (Företagskonto).
        - Bokföringsdatum ska vara betalningsdatumet ({bokforingsdatum}).
        """

    # Hantera omvänd skattskyldighet
    reverse_charge_instructions = ""
    if invoice.reverse_charge:
        reverse_charge_instructions = """
        - VIKTIGT: Denna faktura har OMVÄND SKATTSKYLDIGHET.
        - Ingen utgående moms (konto 26xx) ska bokföras.
        - Använd ett försäljningskonto för omvänd skattskyldighet, t.ex. 3231.
        """

    prompt = f"""
    Analysera följande kundfaktura och skapa ett bokföringsförslag. Svara ENDAST med ett JSON-objekt.
    JSON-objektet måste ha en huvudnyckel: "suggestion".

    `suggestion`: Ett konkret bokföringsförslag för just denna faktura.
        - Använd exakta belopp. Summan av debet och kredit måste balansera.
        - Inkludera en `description`.

    TILLGÄNGLIGA KONTON (använd endast dessa):
    ---
    {kontoplan_str}
    ---
    
    ALLMÄNNA REGLER (följ alltid dessa):
    ---
    {general_rules}
    ---

    INSTRUKTIONER FÖR DENNA FAKTURA:
    {method_instructions}
    {reverse_charge_instructions}

    FAKTURADATA:
    - Fakturanummer: {invoice.number}
    - Kund: {invoice.client.name if invoice.client else 'Okänd'}
    - Fakturadatum: {invoice.date.strftime('%Y-%m-%d')}
    - Betaldatum: {(invoice.paid_at or 'Ej betald')}
    - Summa (inkl. moms): {invoice.sum} SEK
    - Momsbelopp: {invoice.tax} SEK
    - Netto (exkl. moms): {invoice.net} SEK
    - Omvänd skattskyldighet: {'Ja' if invoice.reverse_charge else 'Nej'}

    Exempel på svar för en faktura på 1250 SEK (1000 netto + 250 moms) med fakturametoden:
    {{
      "suggestion": {{
        "description": "Faktura {invoice.number} - {invoice.client.name}",
        "entries": [
          {{"konto": "1510", "debet": 1250.00, "kredit": 0}},
          {{"konto": "2611", "debet": 0, "kredit": 250.00}},
          {{"konto": "3001", "debet": 0, "kredit": 1000.00}}
        ]
      }}
    }}
    """
    return _call_gemini_api(prompt)


def get_bokforing_suggestion_from_gemini(transaction: BankTransaction, general_rules: str, specific_rule: str) -> Dict:
    """
    Skickar transaktionsdata till Gemini och ber om både ett specifikt förslag
    och en generell, återanvändbar regel.
    """
    kontoplan_str = "\n".join([f"{k} - {v}" for k, v in KONTOPLAN.items()])
    original_amount = transaction.belopp # Använd det ursprungliga beloppet med tecken

    prompt = f"""
    Analysera följande banktransaktion. Svara ENDAST med ett JSON-objekt.
    JSON-objektet måste ha två huvudnycklar: "suggestion" och "rule".

    1.  `suggestion`: Ett konkret bokföringsförslag för just denna transaktion.
        - Använd exakta belopp. Summan av debet och kredit måste balansera.
        - Inkludera en `description`.

    2.  `rule`: En generell regel för framtida liknande transaktioner.
        - I regelns `entries`, använd matematiska uttryck med platshållaren `ABS_AMOUNT` för att representera transaktionens *absoluta* belopp.
        - Använd `ORIGINAL_AMOUNT` för att representera transaktionens *ursprungliga* belopp med tecken.
        - Exempel för 25% moms: `ABS_AMOUNT / 1.25` för kostnaden och `ABS_AMOUNT - (ABS_AMOUNT / 1.25)` för momsen.
        - Uttrycken evalueras i Python, så använd giltig syntax (t.ex. `*` för multiplikation).
        - Inkludera en `description` för regeln.

    TILLGÄNGLIGA KONTON (använd endast dessa):
    ---
    {kontoplan_str}
    ---

    SPECIFIK REGEL FÖR DENNA TRANSKATION (om den finns):
    ---
    {specific_rule}
    ---

    ALLMÄNNA REGLER (följ alltid dessa):
    ---
    {general_rules}
    ---

    TRANSKTIONSDATA:
    - Datum: {transaction.bokforingsdag.strftime('%Y-%m-%d')}
    - Referens: "{transaction.referens}"
    - Ursprungligt Belopp: {original_amount} SEK

    VIKTIGA REGLER FÖR BOKFÖRING:
    - Bankkontot '1930' ska ALLTID krediteras om Ursprungligt Belopp är negativt (utbetalning).
    - Bankkontot '1930' ska ALLTID debiteras om Ursprungligt Belopp är positivt (inbetalning).
    - För andra konton (t.ex. kostnader, intäkter, moms), använd det absoluta värdet av beloppet och tilldela debet/kredit baserat på kontotypen.
    """
    
    # Anropar den generiska funktionen men förväntar sig både suggestion och rule
    gemini_response = _call_gemini_api(prompt)
    if 'suggestion' in gemini_response and 'rule' not in gemini_response:
        # Om Gemini bara returnerade suggestion (vilket den inte borde med denna prompt), logga en varning.
        current_app.logger.warning("Gemini returnerade en suggestion men ingen regel för en transaktion.")
        gemini_response['rule'] = {'description': 'Generell regel ej skapad', 'entries': []} # Lägg till en tom regel
    
    return gemini_response
