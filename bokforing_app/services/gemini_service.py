# -*- coding: utf-8 -*-
import os
import json
from typing import Dict
import httpx
from flask import current_app
from bokforing_app.models import BankTransaction
from bokforing_app.services.accounting_config import KONTOPLAN

def get_bokforing_suggestion_from_gemini(transaction: BankTransaction, general_rules: str, specific_rule: str) -> Dict:
    """
    Skickar transaktionsdata till Gemini och ber om både ett specifikt förslag
    och en generell, återanvändbar regel.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY är inte satt i systemmiljön."}

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
            current_app.logger.warning(
                "SOCKS5_PROXY är satt men 'httpx-socks' är inte installerat. "
                "Fortsätter utan proxy. Kör 'pip install httpx-socks' för att aktivera proxy."
            )
            transport = None
        except Exception as e:
            return {"error": f"Kunde inte konfigurera SOCKS5-proxy: {e}"}

    kontoplan_str = "\n".join([f"{k} - {v}" for k, v in KONTOPLAN.items()])
    belopp = abs(transaction.belopp)

    prompt = f"""
    Analysera följande banktransaktion. Svara ENDAST med ett JSON-objekt.
    JSON-objektet måste ha två huvudnycklar: "suggestion" och "rule".

    1.  `suggestion`: Ett konkret bokföringsförslag för just denna transaktion.
        - Använd exakta belopp. Summan av debet och kredit måste balansera.
        - Inkludera en `description`.

    2.  `rule`: En generell regel för framtida liknande transaktioner.
        - I regelns `entries`, använd matematiska uttryck med platshållaren `TOTAL` för att representera transaktionsbeloppet.
        - Exempel för 25% moms: `TOTAL / 1.25` för kostnaden och `TOTAL - (TOTAL / 1.25)` för momsen.
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
    - Belopp: {transaction.belopp} SEK (Absolutbelopp att använda: {belopp})
    - Bankkonto är ALLTID '1930'.

    Exempel på svar för ett köp på OKQ8 för 500 SEK:
    {{
      "suggestion": {{
        "description": "Köp av drivmedel hos OKQ8",
        "entries": [
          {{"konto": "5611", "debet": 400.00, "kredit": 0}},
          {{"konto": "2641", "debet": 100.00, "kredit": 0}},
          {{"konto": "1930", "debet": 0, "kredit": 500.00}}
        ]
      }},
      "rule": {{
        "description": "Drivmedel (25% moms)",
        "entries": [
          {{"konto": "5611", "debet": "TOTAL * 0.8", "kredit": "0"}},
          {{"konto": "2641", "debet": "TOTAL * 0.2", "kredit": "0"}},
          {{"konto": "1930", "debet": "0", "kredit": "TOTAL"}}
        ]
      }}
    }}
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        with httpx.Client(transport=transport) as client:
            response = client.post(url, json=payload, timeout=90)
            response.raise_for_status()

            api_response = response.json()
            text_response = api_response['candidates'][0]['content']['parts'][0]['text']
            
            cleaned_text = text_response.replace("```json", "").replace("```", "").strip()
            parsed_json = json.loads(cleaned_text)
            if 'suggestion' not in parsed_json or 'rule' not in parsed_json:
                raise json.JSONDecodeError("Svaret saknar 'suggestion' eller 'rule'.", cleaned_text, 0)
            
            return parsed_json

    except httpx.RequestError as e:
        return {"error": f"Anrop till Gemini API misslyckades: {e}"}
    except httpx.HTTPStatusError as e:
        return {"error": f"Gemini API returnerade ett fel: {e.response.status_code} {e.response.text}"}
    except (KeyError, IndexError):
        return {"error": f"Oväntat API-svarformat: {response.text if 'response' in locals() else 'Inget svar'}"}
    except json.JSONDecodeError as e:
        return {"error": f"AI returnerade ogiltig JSON: {e.msg} - Svar: {e.doc}"}
    except Exception as e:
        return {"error": f"Ett oväntat fel inträffade: {str(e)}"}
