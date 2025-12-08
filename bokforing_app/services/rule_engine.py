# bokforing_app/services/rule_engine.py
from typing import List, Dict, Any
from bokforing_app.models import BankTransaction

def apply_rule(transaction: BankTransaction, rule: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Applicerar en given regel på en transaktion för att generera bokföringsposter.
    Hanterar nu även momsberäkningar och ger tydligare felmeddelanden.
    Är nu mer robust gällande nycklar ('konto' vs 'account', 'debet' vs 'debit', etc.).

    Args:
        transaction: BankTransaction-objektet som regeln ska appliceras på.
        rule: En dictionary som representerar regeln.

    Returns:
        En lista av dictionaries, där varje dictionary är en bokföringspost.
    """
    if not rule or 'entries' not in rule:
        raise ValueError("Ogiltigt regelformat. Huvudnyckeln 'entries' saknas.")

    abs_amount = abs(transaction.belopp)
    vat_rate = rule.get('vat_rate')

    eval_context = {
        'ABS_AMOUNT': abs_amount,
        'ORIGINAL_AMOUNT': transaction.belopp
    }

    if vat_rate is not None and isinstance(vat_rate, (int, float)) and vat_rate > 0:
        vat_multiplier = vat_rate / 100
        net_amount = abs_amount / (1 + vat_multiplier)
        vat_amount = abs_amount - net_amount
        eval_context['NET_AMOUNT'] = net_amount
        eval_context['VAT_AMOUNT'] = vat_amount
    else:
        eval_context['NET_AMOUNT'] = abs_amount
        eval_context['VAT_AMOUNT'] = 0

    generated_entries = []
    for i, entry_template in enumerate(rule['entries']):
        konto_val = entry_template.get('konto') or entry_template.get('account')
        if konto_val is None:
            raise ValueError(f"Post #{i+1} i regeln saknar den obligatoriska nyckeln 'konto' eller 'account'.")
        
        konto = str(konto_val)
        
        try:
            # **KORRIGERING:** Leta efter både svenska och engelska nycklar.
            debet_val = entry_template.get('debet') or entry_template.get('debit') or '0'
            kredit_val = entry_template.get('kredit') or entry_template.get('credit') or '0'
            
            debet_str = str(debet_val)
            kredit_str = str(kredit_val)

            debet_str = debet_str.replace('TOTAL', 'ABS_AMOUNT')
            kredit_str = kredit_str.replace('TOTAL', 'ABS_AMOUNT')

            debet = eval(debet_str, {"__builtins__": None}, eval_context)
            kredit = eval(kredit_str, {"__builtins__": None}, eval_context)

            generated_entries.append({
                'konto': konto,
                'debet': round(float(debet), 2),
                'kredit': round(float(kredit), 2)
            })
        except Exception as e:
            raise ValueError(f"Fel i regel för konto {konto} (post #{i+1}): Kunde inte tolka debet/kredit. Detaljer: {e}")

    total_debet = sum(e['debet'] for e in generated_entries)
    total_kredit = sum(e['kredit'] for e in generated_entries)

    if abs(total_debet - total_kredit) > 0.01:
        diff = round(total_debet - total_kredit, 2)
        if abs(diff) < 0.05:
            if diff > 0:
                entry_to_adjust = max((e for e in generated_entries if e['debet'] > 0), key=lambda x: x['debet'], default=None)
                if entry_to_adjust: entry_to_adjust['debet'] -= diff
            else:
                entry_to_adjust = max((e for e in generated_entries if e['kredit'] > 0), key=lambda x: x['kredit'], default=None)
                if entry_to_adjust: entry_to_adjust['kredit'] += diff
        
        total_debet = sum(e['debet'] for e in generated_entries)
        total_kredit = sum(e['kredit'] for e in generated_entries)
        if abs(total_debet - total_kredit) > 0.01:
            raise ValueError(f"Regeln skapade obalans. Debet: {total_debet:.2f}, Kredit: {total_kredit:.2f}")

    return generated_entries
