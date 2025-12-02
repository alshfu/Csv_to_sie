import os
import json
from typing import Optional
from pydantic import BaseModel, Field
import httpx
import base64


# --- 1. Pydantic-modeller ---

class Kund(BaseModel):
    kundnummer: Optional[str] = None
    namn: Optional[str] = None
    orgnr: Optional[str] = None
    adress: Optional[str] = None


class Saljare(BaseModel):
    namn: Optional[str] = None
    orgnr: Optional[str] = None
    momsregnr: Optional[str] = None
    bankgiro: Optional[str] = None


class InvoiceDataStrict(BaseModel):
    fakturanr: Optional[str] = None
    fakturadatum: Optional[str] = None
    forfallodag: Optional[str] = None
    ocr: Optional[str] = None
    total_netto: Optional[str] = None
    total_moms: Optional[str] = None
    total_brutto: Optional[str] = None
    att_betala: Optional[str] = None
    kund: Optional[Kund] = None
    saljare: Optional[Saljare] = None
    information: Optional[str] = None


# --- 2. Huvudfunktion för att anropa Gemini direkt med httpx ---

def extract_exact_json_from_pdf(pdf_path: str) -> str:
    """
    Skickar PDF-data till Gemini REST API med httpx och returnerar en JSON-sträng.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return json.dumps({"error": "GEMINI_API_KEY not set in environment"})

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
            return json.dumps({"error": "Proxy support requires 'httpx-socks'. Please run 'pip install httpx-socks'."})
        except Exception as e:
            return json.dumps({"error": f"Failed to configure SOCKS5 proxy: {e}"})

    try:
        with open(pdf_path, "rb") as f:
            pdf_content_base64 = base64.b64encode(f.read()).decode('utf-8')
    except FileNotFoundError:
        return json.dumps({"error": f"File not found: {pdf_path}"})
    except Exception as e:
        return json.dumps({"error": f"Failed to read or encode file: {e}"})

    # Prompt som instruerar AI:n att svara med JSON
    prompt = f"""
    Analysera följande faktura. Extrahera datan och svara ENDAST med en JSON-struktur.
    Använd exakt detta schema: {InvoiceDataStrict.model_json_schema()}
    """

    # Använder den stabila 'gemini-pro-vision'-modellen
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key={api_key}"

    # Förenklad payload
    payload = {
        "contents": [
            {
                "parts": [
                    {"inline_data": {"mime_type": "application/pdf", "data": pdf_content_base64}},
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        with httpx.Client(transport=transport) as client:
            response = client.post(url, json=payload, timeout=120)
            response.raise_for_status()

            api_response = response.json()
            text_response = api_response['candidates'][0]['content']['parts'][0]['text']

            # Rensa bort markdown och validera JSON
            cleaned_text = text_response.replace("```json", "").replace("```", "").strip()
            json.loads(cleaned_text)
            return cleaned_text

    except httpx.RequestError as e:
        return json.dumps({"error": f"Request to Gemini API failed: {e}"})
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"Gemini API returned an error: {e.response.status_code} {e.response.text}"})
    except (KeyError, IndexError):
        return json.dumps({"error": f"Unexpected API response format: {response.text}"})
    except json.JSONDecodeError:
        return json.dumps({"error": f"AI returned invalid JSON: {text_response}"})
    except Exception as e:
        return json.dumps({"error": f"An unexpected error occurred: {str(e)}"})


# --- 3. Exempel ---
if __name__ == "__main__":
    pass
