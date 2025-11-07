import pdfplumber
import re
import json


def clean_text(text):
    """Вспомогательная функция для очистки текста от лишних пробелов."""
    if text:
        return re.sub(r'\s+', ' ', text).strip()
    return None


def safe_search(pattern, text, re_flags=0):
    """
    Безопасно выполняет re.search и возвращает group(1) или None.
    """
    match = re.search(pattern, text, re_flags)
    if match:
        try:
            return clean_text(match.group(1))
        except IndexError:
            return clean_text(match.group(0))
    return None


def parse_xl_jbm_invoice(pdf_path):
    """
    Парсит PDF-счет от XL JBM, извлекая ключевую информацию и строки заказа.

    :param pdf_path: Путь к PDF-файлу счета.
    :return: Словарь с извлеченными данными.
    """
    invoice_data = {
        "fakturanr": None,
        "fakturadatum": None,
        "forfallodag": None,
        "ocr": None,
        "total_netto": None,
        "total_moms": None,
        "total_brutto": None,
        "att_betala": None,
        "kund": {
            "kundnummer": None,
            "namn": None,
            "orgnr": None,
            "adress": None
        },
        "saljare": {
            "namn": "XL-BYGG JBM Jämjö",
            "orgnr": None,
            "momsregnr": None,
            "bankgiro": None
        },
        "orders": []
    }

    full_text = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
            if not page_text:
                continue

            full_text += page_text + "\n"

            # --- Извлечение данных из таблиц (строки заказа) ---
            tables = page.extract_tables()
            for table in tables:
                if not (table and table[0] and table[0][0]):
                    continue

                header_raw = table[0][0]
                if not header_raw:
                    continue

                # Более "мягкая" проверка
                header = clean_text(header_raw.replace("\n", " "))

                # --- DEBUG PRINT ---
                print(f"--- DEBUG: Найдена таблица, заголовок: '{header}' ---")

                if header and "artikelnr" in header.lower():
                    print(f"--- INFO: Найдена таблица ЗАКАЗА на стр. {page_num + 1} ---")
                    current_order_items = []
                    for row in table[1:]:
                        if not row or len(row) < 9:
                            continue
                        if row[0] and ("Alla priser" in row[0] or (row[1] and "Delsumma" in row[1])):
                            break
                        item = {
                            "artikelnr": clean_text(row[0]),
                            "benämning": clean_text(row[1]),
                            "antal": clean_text(row[3]),
                            "enhet": clean_text(row[4]),
                            "apris": clean_text(row[5]),
                            "rabatt": clean_text(row[7]),
                            "belopp": clean_text(row[8])
                        }
                        if item["artikelnr"] or item["benämning"]:
                            current_order_items.append(item)

                    if current_order_items:
                        order_nr_match = re.search(r"ORDER - (\d+)", page_text)
                        projekt_match = re.search(r"Projekt\s*([^\n]+)", page_text)
                        invoice_data["orders"].append({
                            "order_nr": clean_text(order_nr_match.group(1)) if order_nr_match else None,
                            "projekt": clean_text(projekt_match.group(1)) if projekt_match else None,
                            "items": current_order_items
                        })

    # --- Извлечение ключевых данных ---

    invoice_data["fakturanr"] = safe_search(r"Fakturanr\s+(\d+)", full_text, re.IGNORECASE)
    invoice_data["fakturadatum"] = safe_search(r"Fakturadatum\s+(\d{4}-\d{2}-\d{2})", full_text, re.IGNORECASE)

    # --- Данные клиента (Kund) --- [ИСПРАВЛЕННЫЙ БЛОК] ---
    try:
        kund_match = re.search(
            r"Kundnummer\s+Ert orgnr\s*\n\s*(\d+)\s+(\d{10})",
            full_text
        )
        if kund_match:
            invoice_data["kund"]["kundnummer"] = clean_text(kund_match.group(1))
            invoice_data["kund"]["orgnr"] = clean_text(kund_match.group(2))

        # Исправлено: \n заменен на \s+ (любой пробел)
        # ([^\n]+) - захватывает "все, что не является переносом строки" (т.е. одну строку)
        address_match = re.search(
            r"(TMR Bygg & Renovering AB)\s+([^\n]+)\s+([^\n]+)",
            full_text
        )
        if address_match and re.match(r"\d{3}\s*\d{2}", address_match.group(3)):
            invoice_data["kund"]["namn"] = clean_text(address_match.group(1))
            invoice_data["kund"][
                "adress"] = f"{clean_text(address_match.group(2))}, {clean_text(address_match.group(3))}"
    except Exception as e:
        print(f"--- Warning: Could not parse client info (Error: {e}). Safely skipping. ---")

    # --- Данные продавца (Säljare) ---
    try:
        seller_match = re.search(r"(\d{6}-\d{4}),\s*Godkänd för F-skatt\s+(\d{4}-\d{4})", full_text)
        if seller_match:
            invoice_data["saljare"]["orgnr"] = clean_text(seller_match.group(1))
            invoice_data["saljare"]["bankgiro"] = clean_text(seller_match.group(2))

        invoice_data["saljare"]["momsregnr"] = safe_search(r"Momsregnr[\s\S]*?(SE\d+)", full_text)
    except Exception as e:
        print(f"--- Warning: Could not parse seller info (Error: {e}). Safely skipping. ---")

    # --- Итоговые суммы (Netto, Moms, Brutto) --- [ИСПРАВЛЕННЫЙ БЛОК] ---
    try:
        # Ищем Netto. [ \d]+? - ищет цифры и пробелы (но не запятые!)
        invoice_data["total_netto"] = safe_search(r"Netto\s+Moms \(25%\)[\s\S]*?\n\s*([ \d]+?,\d{2})", full_text,
                                                  re.IGNORECASE)

        # Ищем Moms (второе число)
        invoice_data["total_moms"] = safe_search(r"Moms \(25%\)[\s\S]*?\n\s*[ \d]+?,\d{2}\s+([ \d]+?,\d{2})", full_text,
                                                 re.IGNORECASE)

        # Ищем Summa
        invoice_data["total_brutto"] = safe_search(r"Summa\n[\s\S]*?([ \d]+?,\d{2})\s*SEK", full_text, re.IGNORECASE)

        if not invoice_data["total_brutto"]:
            invoice_data["total_brutto"] = safe_search(r"([ \d]+?,\d{2})\s*SEK", full_text)

    except Exception as e:
        print(f"--- Warning: Could not parse totals (Error: {e}). Safely skipping. ---")

    # --- Данные для оплаты (OCR, Att betala) ---
    try:
        payment_header_match = re.search(
            r"Förfallodag\s+Bankgiro\s+(?:Plusgiro\s+)?OCR \(Anges vid betalning\)\s+Att betala",
            full_text,
            re.IGNORECASE
        )
        if payment_header_match:
            text_after_headers = full_text[payment_header_match.end():]
            value_match = re.search(
                r"^\s*(\S+)\s+(\S+)\s+(?:Plusgiro\s+)?(\d+)\s+([\d\s,]+?,\d{2})\s*SEK",
                text_after_headers,
                re.MULTILINE
            )
            if value_match:
                invoice_data["forfallodag"] = clean_text(value_match.group(1))
                if not invoice_data["saljare"]["bankgiro"]:
                    invoice_data["saljare"]["bankgiro"] = clean_text(value_match.group(2))
                invoice_data["ocr"] = clean_text(value_match.group(3))
                invoice_data["att_betala"] = clean_text(value_match.group(4))
    except Exception as e:
        print(f"--- Warning: Could not parse payment info (Error: {e}). Safely skipping. ---")

    # Запасные варианты
    if not invoice_data["att_betala"] and invoice_data["total_brutto"]:
        invoice_data["att_betala"] = invoice_data["total_brutto"]
    if not invoice_data["total_brutto"] and invoice_data["att_betala"]:
        invoice_data["total_brutto"] = invoice_data["att_betala"]

    return invoice_data


# --- ПРИМЕР ИСПОЛЬЗОВАНИЯ ---

if __name__ == "__main__":
    #
    # ⚠️ ОБЯЗАТЕЛЬНО ИЗМЕНИТЕ ЭТОТ ПУТЬ ⚠️
    #
    file_path = "bokforing_app/static/uploads/company_1/faktura-641180.pdf"

    try:
        data = parse_xl_jbm_invoice(file_path)
        print(json.dumps(data, indent=2, ensure_ascii=False))

    except FileNotFoundError:
        print(f"ОШИБКА: Файл не найден по пути: {file_path}")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
