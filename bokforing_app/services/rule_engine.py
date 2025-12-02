# bokforing_app/services/rule_engine.py
from typing import List, Dict, Any
from bokforing_app.models import BankTransaction

def apply_rule(transaction: BankTransaction, rule: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Applicerar en given regel på en transaktion för att generera bokföringsposter.

    Args:
        transaction: BankTransaction-objektet som regeln ska appliceras på.
        rule: En dictionary som representerar regeln, t.ex. från en Association.

    Returns:
        En lista av dictionaries, där varje dictionary är en bokföringspost.
    """
    if not rule or 'entries' not in rule:
        raise ValueError("Ogiltigt regelformat. 'entries' saknas.")

    # Definiera de tillgängliga platshållarna
    eval_context = {
        'ABS_AMOUNT': abs(transaction.belopp),
        'ORIGINAL_AMOUNT': transaction.belopp
    }

    generated_entries = []
    for entry_template in rule['entries']:
        try:
            debet_str = entry_template.get('debet', '0')
            kredit_str = entry_template.get('kredit', '0')

            # Ersätt den gamla platshållaren 'TOTAL' för bakåtkompatibilitet
            debet_str = debet_str.replace('TOTAL', 'ABS_AMOUNT')
            kredit_str = kredit_str.replace('TOTAL', 'ABS_AMOUNT')

            # Evaluera uttrycken på ett säkert sätt
            debet = eval(str(debet_str), {"__builtins__": None}, eval_context)
            kredit = eval(str(kredit_str), {"__builtins__": None}, eval_context)

            generated_entries.append({
                'konto': entry_template['konto'],
                'debet': round(float(debet), 2),
                'kredit': round(float(kredit), 2)
            })
        except Exception as e:
            raise ValueError(f"Fel vid evaluering av regeluttryck: '{debet_str}' eller '{kredit_str}'. Fel: {e}")

    # Validera balansen
    total_debet = sum(e['debet'] for e in generated_entries)
    total_kredit = sum(e['kredit'] for e in generated_entries)

    if abs(total_debet - total_kredit) > 0.01:
        raise ValueError(f"Regeln skapade obalans. Debet: {total_debet}, Kredit: {total_kredit}")

    return generated_entries
