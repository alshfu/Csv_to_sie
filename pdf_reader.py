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
            # Пытаемся вернуть первую захваченную группу
            return clean_text(match.group(1))
        except IndexError:
            # Если нет захватывающей группы, возвращаем все совпадение
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
        "netto": None,  # Сумма "без момса" (без НДС)
        "moms": None,  # НДС
        "summa_brutto": None,  # Итоговая сумма "с момсом" (с НДС)
        "att_betala": None,  # Сумма к оплате (обычно равна summa_brutto)
        "kund": {
            "namn": None,
            "orgnr": None,
            "adress": None
        },
        "orders": []
    }

    full_text = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            # x_tolerance=2 помогает правильно "собрать" текст из табличных ячеек
            page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
            if not page_text:
                continue

            full_text += page_text + "\n"

            # --- Извлечение данных из таблиц (строки заказа) ---
            tables = page.extract_tables()
            for table in tables:
                if not (table and table[0] and table[0][0]):
                    continue

                header = clean_text(table[0][0])
                # Проверяем на 'artikelnr' в любом регистре
                if header and "artikelnr" in header.lower():
                    current_order_items = []
                    for row in table[1:]:  # Пропускаем заголовок
                        if not row or len(row) < 9:
                            continue

                        if row[0] and ("Alla priser" in row[0] or (row[1] and "Delsumma" in row[1])):
                            break  # Останавливаемся на строке "Delsumma"

                        item = {
                            "artikelnr": clean_text(row[0]),
                            "benamning": clean_text(row[1]),
                            "antal": clean_text(row[3]),
                            "enhet": clean_text(row[4]),
                            "apris": clean_text(row[5]),
                            "rabatt": clean_text(row[7]),
                            "belopp": clean_text(row[8])
                        }

                        if item["artikelnr"] or item["benamning"]:
                            current_order_items.append(item)

                    if current_order_items:
                        order_nr_match = re.search(r"ORDER - (\d+)", page_text)
                        projekt_match = re.search(r"Projekt\s*([^\n]+)", page_text)

                        invoice_data["orders"].append({
                            "order_nr": clean_text(order_nr_match.group(1)) if order_nr_match else None,
                            "projekt": clean_text(projekt_match.group(1)) if projekt_match else None,
                            "items": current_order_items
                        })

    # --- Извлечение ключевых данных из всего текста (в основном с 1-й страницы) ---

    invoice_data["fakturanr"] = safe_search(r"Fakturanr\s*(\d+)", full_text, re.IGNORECASE)
    invoice_data["fakturadatum"] = safe_search(r"Fakturadatum\s*(\d{4}-\d{2}-\d{2})", full_text, re.IGNORECASE)
    invoice_data["forfallodag"] = safe_search(r"Förfallodag\s*(\d{4}-\d{2}-\d{2})", full_text, re.IGNORECASE)

    # --- ГИБКИЙ парсинг сумм (с non-greedy '?' и якорем ',\d{2}') ---
    # ([\d\s,]+?,\d{2}) - "не жадно" ищет одно число формата X,XX

    # Сначала пробуем найти 5-колоночную строку (Netto, Moms, Rotavdrag, Öresutj., Summa)
    # (как на вашем скриншоте)
    summary_match = re.search(
        r"\n?\s*([\d\s,]+?,\d{2})\s+([\d\s,]+?,\d{2})\s+([\d\s,]+?,\d{2})\s+([\d\s,]+?,\d{2})\s+([\d\s,]+?,\d{2})\s*SEK",
        full_text
    )

    if summary_match:
        invoice_data["netto"] = clean_text(summary_match.group(1))  # 1-е число
        invoice_data["moms"] = clean_text(summary_match.group(2))  # 2-е число
        # group(3) - Rotavdrag, group(4) - Öresutjämn.
        invoice_data["summa_brutto"] = clean_text(summary_match.group(5))  # 5-е число
    else:
        # Если не нашли 5, пробуем найти 4-колоночную строку (Netto, Moms, Öresutj., Summa)
        # (Вероятно, как в вашем файле faktura-648056.pdf)
        summary_match_4 = re.search(
            r"\n?\s*([\d\s,]+?,\d{2})\s+([\d\s,]+?,\d{2})\s+([\d\s,]+?,\d{2})\s+([\d\s,]+?,\d{2})\s*SEK",
            full_text
        )
        if summary_match_4:
            invoice_data["netto"] = clean_text(summary_match_4.group(1))  # 1-е число
            invoice_data["moms"] = clean_text(summary_match_4.group(2))  # 2-е число
            # group(3) - Öresutjämn.
            invoice_data["summa_brutto"] = clean_text(summary_match_4.group(4))  # 4-е число
        else:
            # Если и это не сработало, используем старый, но ИСПРАВЛЕННЫЙ "запасной" метод
            # (Он ищет по заголовкам, а не по одной строке)
            invoice_data["netto"] = safe_search(r"Netto\s+Moms[\s\S]*?\n\s*([\d\s,]+?,\d{2})", full_text, re.IGNORECASE)
            invoice_data["moms"] = safe_search(r"Moms\s+\(25%\)[\s\S]*?\n\s*[\d\s,]+?,\d{2}\s+([\d\s,]+?,\d{2})",
                                               full_text, re.IGNORECASE)
            invoice_data["summa_brutto"] = safe_search(r"Summa[\s\S]*?([\d\s,]+?,\d{2})\s*SEK", full_text,
                                                       re.IGNORECASE)

    # --- Парсинг OCR и Att Betala (тоже с исправленным regex) ---
    payment_line_match = re.search(
        r"OCR \(Anges vid betalning\)[\s\S]*?Att betala[\s\S]*?\n[\s\S]*?(\d+)\s+([\d\s,]+?,\d{2})\s*SEK",
        full_text,
        re.IGNORECASE
    )

    if payment_line_match:
        invoice_data["ocr"] = clean_text(payment_line_match.group(1))
        invoice_data["att_betala"] = clean_text(payment_line_match.group(2))
    else:
        # Запасной вариант
        invoice_data["ocr"] = safe_search(r"OCR \(Anges vid betalning\)[\s\S]*?(\d+)", full_text, re.IGNORECASE)
        invoice_data["att_betala"] = safe_search(r"Att betala[\s\S]*?([\d\s,]+?,\d{2})\s*SEK", full_text, re.IGNORECASE)

    # --- Безопасный поиск данных клиента ---
    try:
        client_match = re.search(r"(\d{6}-\d{4})\n(.*?)\n(.*?)\n(\d{3}\s*\d{2}\s*.*)", full_text)

        if not client_match:
            client_match = re.search(r"Kundnummer\s*\d+\s*\n(.*?)\n(.*?)\n(\d{3}\s*\d{2}\s*.*)", full_text, re.DOTALL)
            if client_match and len(client_match.groups()) == 3:
                invoice_data["kund"]["namn"] = clean_text(client_match.group(1))
                invoice_data["kund"][
                    "adress"] = f"{clean_text(client_match.group(2))}, {clean_text(client_match.group(3))}"
            else:
                client_match = re.search(r"(TMR Bygg & Renovering AB)\n(.*?)\n(\d{3}\s*\d{2}\s*.*)", full_text)
                if client_match:
                    invoice_data["kund"]["namn"] = clean_text(client_match.group(1))
                    invoice_data["kund"][
                        "adress"] = f"{clean_text(client_match.group(2))}, {clean_text(client_match.group(3))}"

        if client_match and len(client_match.groups()) == 4:
            invoice_data["kund"]["orgnr"] = clean_text(client_match.group(1))
            invoice_data["kund"]["namn"] = clean_text(client_match.group(2))
            invoice_data["kund"]["adress"] = f"{clean_text(client_match.group(3))}, {clean_text(client_match.group(4))}"

    except Exception as e:
        print(f"--- Warning: Could not parse client info (Error: {e}). Safely skipping. ---")
        pass

        # Убедимся, что att_betala и summa_brutto заполнены
    if not invoice_data["att_betala"] and invoice_data["summa_brutto"]:
        invoice_data["att_betala"] = invoice_data["summa_brutto"]
    if not invoice_data["summa_brutto"] and invoice_data["att_betala"]:
        invoice_data["summa_brutto"] = invoice_data["att_betala"]

    return invoice_data


# --- ПРИМЕР ИСПОЛЬЗОВАНИЯ ---

if __name__ == "__main__":
    #
    # ⚠️ ОБЯЗАТЕЛЬНО ИЗМЕНИТЕ ЭТОТ ПУТЬ ⚠️
    #
    file_path = "static/uploads/company_1/faktura-641180.pdf"

    try:
        data = parse_xl_jbm_invoice(file_path)
        print(json.dumps(data, indent=2, ensure_ascii=False))

    except FileNotFoundError:
        print(f"ОШИБКА: Файл не найден по пути: {file_path}")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")