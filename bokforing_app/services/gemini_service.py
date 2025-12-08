# -*- coding: utf-8 -*-
"""
Service för att kommunicera med Google Gemini API.

Denna modul ansvarar för all interaktion med Googles generativa AI-modell, Gemini.
Den bygger upp specifika prompts för att få bokföringsförslag för både
banktransaktioner och kundfakturor. Modulen inkluderar även en robust
retry-mekanism för att hantera instabila nätverksanslutningar.
"""
import os
import json
import time  # För tidsmätning
from typing import Dict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import ConnectionError, ProxyError  # För fallback-hantering
from flask import current_app
from bokforing_app.models import BankTransaction, Invoice
from bokforing_app.services.accounting_config import KONTOPLAN
from bokforing_app.services import proxy_service  # Korrigerad: Absolut import


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
        allowed_methods=["POST", "GET"],  # Ändrat till lista för kompatibilitet
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
        response = session.post(url, json=payload, timeout=120)  # Ökat timeout
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


def get_suggestion_for_invoice(invoice: Invoice, general_rules: str) -> Dict:
    """
    Bygger en prompt för en kundfaktura och anropar Gemini API.
    """
    kontoplan_str = "\n".join([f"{k} - {v}" for k, v in KONTOPLAN.items()])

    if invoice.company.accounting_method == 'faktura':
        bokforingsdatum = invoice.date.strftime('%Y-%m-%d')
        method_instructions = (
            f"- Företaget använder FAKTURAMETODEN.\n"
            f"- Bokför en kundfordran på konto 1510.\n"
            f"- Bokföringsdatum ska vara fakturadatumet ({bokforingsdatum})."
        )
    else:  # kontant
        bokforingsdatum = (invoice.paid_at or invoice.date).strftime('%Y-%m-%d')
        method_instructions = (
            f"- Företaget använder KONTANTMETODEN.\n"
            f"- Bokför betalningen direkt mot ett tillgångskonto, vanligtvis 1930 (Företagskonto).\n"
            f"- Bokföringsdatum ska vara betalningsdatumet ({bokforingsdatum})."
        )

    reverse_charge_instructions = ""
    if invoice.reverse_charge:
        reverse_charge_instructions = (
            "- VIKTIGT: Denna faktura har OMVÄND SKATTSKYLDIGHET.\n"
            "- Ingen utgående moms (konto 26xx) ska bokföras.\n"
            "- Använd ett försäljningskonto för omvänd skattskyldighet, t.ex. 3231."
        )

    prompt = f"""Analysera följande kundfaktura och skapa ett bokföringsförslag. Svara ENDAST med ett JSON-objekt.
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
      {{"account": "1510", "debit": 1250.00, "credit": 0}},
      {{"account": "2611", "debit": 0, "credit": 250.00}},
      {{"account": "3001", "debit": 0, "credit": 1000.00}}
    ]
  }}
}}
"""
    return _call_gemini_api(prompt)


def get_bokforing_suggestion_from_gemini(transaction: BankTransaction, general_rules: str, specific_rule: str) -> Dict:
    """
    Bygger en prompt för en banktransaktion och ber om både ett förslag och en återanvändbar regel.
    """
    kontoplan_str = "\n".join([f"{k} - {v}" for k, v in KONTOPLAN.items()])
    original_amount = transaction.belopp

    prompt = f"""Analysera följande banktransaktion. Svara ENDAST med ett JSON-objekt.
JSON-objektet måste ha två huvudnycklar: "suggestion" och "rule".

1.  `suggestion`: Ett konkret bokföringsförslag för just denna transaktion.
    - Använd exakta belopp. Summan av debet och kredit måste balansera.
    - Inkludera en `description`.
    - Använd nycklarna 'account', 'debit', 'credit'.

2.  `rule`: En generell regel för framtida liknande transaktioner.
    - I regelns `entries`, använd matematiska uttryck med platshållaren `ABS_AMOUNT` och `ORIGINAL_AMOUNT`.
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
- Om en inbetalning (positivt belopp) inte kan identifieras, anta att det är en betalning från en kund för en tjänst 
eller vara med 25% moms. Dela upp beloppet i försäljning (konto 3001 eller 3041) och utgående moms (konto 2611).
"""

    gemini_response = _call_gemini_api(prompt)
    if 'suggestion' in gemini_response and 'rule' not in gemini_response:
        current_app.logger.warning("Gemini returnerade en suggestion men ingen regel för en transaktion.")
        gemini_response['rule'] = {'description': 'Generell regel ej skapad', 'entries': []}

    return gemini_response
