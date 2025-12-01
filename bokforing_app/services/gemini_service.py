# -*- coding: utf-8 -*-
import os
import json
from typing import List, Optional
import httpx
from bokforing_app.models import BankTransaction
from bokforing_app.services.accounting_config import KONTOPLAN

def get_bokforing_suggestion_from_gemini(transaction: BankTransaction, general_rules: str, specific_rule: str) -> str:
    """
    Skickar transaktionsdata, kontoplan och regler till Gemini REST API för att få ett bokföringsförslag.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return json.dumps({"error": "GEMINI_API_KEY är inte satt i systemmiljön."})

    proxy_url = os.getenv("SOCKS5_PROXY")
    transport = None
    if proxy_url:
        try:
            from httpx_socks import SyncSocks5Transport
            parts = proxy_url.replace("socks5://", "").split(":")
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 1080
            transport = SyncSocks5Transport(host=host, port=port)
        except ImportError:
            return json.dumps({"error": "Proxysupport kräver 'httpx-socks'. Kör 'pip install httpx-socks'."})
        except Exception as e:
            return json.dumps({"error": f"Kunde inte konfigurera SOCKS5-proxy: {e}"})

    kontoplan_str = "\n".join([f"{k} - {v}" for k, v in KONTOPLAN.items()])

    prompt = f"""
    Analysera följande banktransaktion och ge ett bokföringsförslag.
    Svara ENDAST med en JSON-struktur, utan extra text eller markdown.
    JSON-objektet ska innehålla en 'description' (str) och en lista med 'entries' (objekt med 'konto', 'debet', 'kredit').

    Här är de tillgängliga kontona från kontoplanen. Använd ENDAST dessa konton i ditt förslag:
    ---
    {kontoplan_str}
    ---
    """

    if specific_rule:
        prompt += f"""
    VIKTIG SPECIFIK REGEL FÖR DENNA TRANSKATION:
    ---
    {specific_rule}
    ---
    """

    if general_rules:
        prompt += f"""
    Här är ytterligare allmänna regler du ALLTID måste följa:
    ---
    {general_rules}
    ---
    """

    prompt += f"""
    Transaktion:
    - Datum: {transaction.bokforingsdag.strftime('%Y-%m-%d')}
    - Referens: "{transaction.referens}"
    - Belopp: {transaction.belopp} SEK

    Instruktioner:
    1.  Välj det mest passande motkontot från listan ovan baserat på referenstexten och eventuella specifika regler.
    2.  Bankkontot är ALLTID '1930'.
    3.  Se till att summan av debet och kredit är i balans.
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        with httpx.Client(transport=transport) as client:
            response = client.post(url, json=payload, timeout=60)
            response.raise_for_status()

            api_response = response.json()
            text_response = api_response['candidates'][0]['content']['parts'][0]['text']
            
            cleaned_text = text_response.replace("```json", "").replace("```", "").strip()
            json.loads(cleaned_text)
            return cleaned_text

    except httpx.RequestError as e:
        return json.dumps({"error": f"Anrop till Gemini API misslyckades: {e}"})
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"Gemini API returnerade ett fel: {e.response.status_code} {e.response.text}"})
    except (KeyError, IndexError):
        return json.dumps({"error": f"Oväntat API-svarformat: {response.text}"})
    except json.JSONDecodeError:
        return json.dumps({"error": f"AI returnerade ogiltig JSON: {text_response}"})
    except Exception as e:
        return json.dumps({"error": f"Ett oväntat fel inträffade: {str(e)}"})
