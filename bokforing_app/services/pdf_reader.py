import os
import json
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


# --- 1. Точная схема данных (Ваш JSON) ---
# Мы используем Pydantic для гарантии, что Gemini вернет именно эту структуру.

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

class OrderItem(BaseModel):
    artnr: Optional[str] = None
    benamning: Optional[str] = None
    antal: Optional[str] = None
    enhet: Optional[str] = None
    a_pris: Optional[str] = None
    summa: Optional[str] = None

class InvoiceDataStrict(BaseModel):
    fakturanr: Optional[str] = None
    fakturadatum: Optional[str] = None
    forfallodag: Optional[str] = None
    ocr: Optional[str] = None
    total_netto: Optional[str] = None
    total_moms: Optional[str] = None
    total_brutto: Optional[str] = None
    att_betala: Optional[str] = None
    kund: Kund
    saljare: Saljare
    orders: List[OrderItem] = Field(default_factory=list)


# --- 2. Основная функция ---

def extract_exact_json_from_pdf(pdf_path: str) -> str:
    """
    Извлекает данные из PDF строго в формате InvoiceDataStrict и возвращает JSON-строку.
    """
    api_key = ""

    if not api_key:
        return json.dumps({"error": "GEMINI_API_KEY not set in environment"}, indent=2)

    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        return json.dumps({"error": f"Failed to initialize client: {e}"}, indent=2)

    try:
        with open(pdf_path, "rb") as f:
            pdf_content = f.read()
    except FileNotFoundError:
        return json.dumps({"error": f"File not found: {pdf_path}"}, indent=2)

    prompt = """
    Extract data from this invoice.
    Use EXACTLY the provided JSON schema.
    If a value is missing in the document, set it to null.
    Keep original formatting for numbers (e.g. "1 234,50").
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_bytes(data=pdf_content, mime_type="application/pdf"),
                        types.Part.from_text(text=prompt),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=InvoiceDataStrict,
                temperature=0.0
            )
        )
        return response.text
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# --- 3. Пример запуска ---
if __name__ == "__main__":
    pdf_file = "bokforing_app/static/uploads/company_1/faktura-641180.pdf"

    if not os.path.exists(pdf_file):
        print(f"[Error] File not found, please check the path: {pdf_file}")
    else:
        json_output = extract_exact_json_from_pdf(pdf_file)
        print(json_output)
