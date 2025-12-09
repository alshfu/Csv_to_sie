import codecs
from datetime import datetime


def _sanitize_for_cp437(text):
    """
    Sanitizes a string to be compatible with CP437 encoding.
    Replaces characters that cannot be encoded with '?'.
    """
    if not isinstance(text, str):
        text = str(text)  # Ensure it's a string first

    # Attempt to encode and decode to replace unsupported characters
    # with '?' (or similar replacement character defined by the codec)
    # The 'replace' error handler is key here.
    return text.encode('cp437', errors='replace').decode('cp437')


def validate_and_write(filename, lines):
    """
    Writes a list of lines to a file with CP437 encoding.
    Raises a ValueError if an encoding error occurs.
    """
    try:
        with codecs.open(filename, 'w', encoding='cp437') as f:
            for line in lines:
                f.write(line + '\n')
    except UnicodeEncodeError as e:
        raise ValueError(f"Encoding error for Swedish characters: {e}. Ensure input is CP437-compatible.")


def generate_sie_file(filename, company_data, verifications):
    """
    Generates a SIE 4B file based on the provided data.

    Args:
        filename (str): The name of the SIE file to generate (e.g., 'output.si').
        company_data (dict): A dictionary with company information.
        verifications (list): A list of verification dictionaries.

    Raises:
        ValueError: If a verification is unbalanced or input is invalid.
    """
    # Step 1: Validate inputs
    for ver in verifications:
        total = sum(trans['amount'] for trans in ver['transactions'])
        if abs(total) > 1e-6:
            raise ValueError(
                f"Verification {ver.get('series', '')}{ver.get('number', '')} is unbalanced: sum = {total}")

        # Validate that all transaction accounts exist in the account plan
        for trans in ver['transactions']:
            if trans['account'] not in company_data.get('accounts', {}):
                raise ValueError(
                    f"Account {trans['account']} in verification {ver.get('number', '')} not found in account plan.")

    # Step 2: Build lines for the SIE file
    lines = [
        '#FLAGGA 0',
        f'#PROGRAM "BLM SIE Generator" 1.0',
        '#FORMAT PC8',
        f'#GEN {datetime.now().strftime("%Y%m%d")}',
        f'#SIETYP 4',
        f'#FNAMN "{_sanitize_for_cp437(company_data["company_name"])}"',
        f'#ORGNR {_sanitize_for_cp437(company_data["org_number"])}',
        f'#RAR 0 {company_data["fiscal_year_start"]} {company_data["fiscal_year_end"]}',
        f'#KPTYP {_sanitize_for_cp437(company_data.get("account_plan_type", "BAS95"))}',
    ]

    # Add accounts
    for acc_num, acc_details in sorted(company_data.get('accounts', {}).items()):
        lines.append(f'#KONTO {acc_num} "{_sanitize_for_cp437(acc_details["name"])}"')
        if "type" in acc_details:
            lines.append(f'#KTYP {acc_num} {_sanitize_for_cp437(acc_details["type"])}')

    # Add verifications
    for ver in verifications:
        ver_parts = [
            f'#VER',
            f'"{_sanitize_for_cp437(ver["series"])}"',
            f'"{_sanitize_for_cp437(ver["number"])}"',
            ver["date"]
        ]
        ver_text = ver.get("text", "")
        if ver_text:
            ver_parts.append(f'"{_sanitize_for_cp437(ver_text)}"')

        lines.append(" ".join(ver_parts))
        lines.append('{')
        for trans in ver['transactions']:
            # Format object string. It must always be present.
            obj_str = '{}'
            if trans.get('objects'):
                obj_items = " ".join([f'{k} "{_sanitize_for_cp437(v)}"' for k, v in trans["objects"].items()])
                if obj_items:
                    obj_str = f'{{{obj_items}}}'

            # Get the verification date to use for the transaction date
            trans_date = ver["date"]

            trans_parts = [
                f'#TRANS',
                str(trans["account"]),
                obj_str,
                f'{trans["amount"]:.2f}',
                trans_date
            ]

            trans_text = trans.get("trans_text", "")
            if trans_text:
                trans_parts.append(f'"{_sanitize_for_cp437(trans_text)}"')

            lines.append(" ".join(trans_parts))
        lines.append('}')

    # Step 3: Write the lines to the file with correct encoding
    validate_and_write(filename, lines)

    print(f"SIE file '{filename}' generated successfully.")


# Example Usage (can be removed or adapted)
if __name__ == '__main__':
    # Sample data based on the technical description
    company = {
        "company_name": "Åkers Företag AB – Test",
        "org_number": "556123-4567",
        "fiscal_year_start": "20250101",
        "fiscal_year_end": "20251231",
        "currency": "SEK",
        "account_plan_type": "BAS95",
        "accounts": {
            1910: {"name": "Kassa", "type": "T"},
            2440: {"name": "Leverantörsskulder", "type": "S"},
            4010: {"name": "Köpta varor och tjänster", "type": "K"},
        }
    }

    verifications_data = [
        {
            "series": "A",
            "number": "1",
            "date": "20251201",
            "text": "Faktura från leverantör Örebro AB – Test",
            "transactions": [
                {"account": 4010, "amount": 1000.00, "trans_text": "Inköp material – Test"},
                {"account": 2440, "amount": -1000.00, "trans_text": "Skuld till lev"},
            ]
        },
        {
            "series": "A",
            "number": "2",
            "date": "20251205",
            "text": "",  # Empty text
            "transactions": [
                {"account": 2440, "amount": 1000.00, "trans_text": ""},  # Empty trans_text
                {"account": 1910, "amount": -1000.00},  # Missing trans_text
            ]
        }
    ]

    try:
        generate_sie_file("test_output.si", company, verifications_data)
    except ValueError as e:
        print(f"Error: {e}")
