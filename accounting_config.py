#
# ===============================================================
#  ПЛАН СЧЕТОВ (KONTOPLAN)
# ===============================================================
#
KONTOPLAN = {
    '1613': 'Lön',
    '1630': 'Skatteverket',
    '1680': 'Lån',

    # --- KORRIGERING 1 (Beskrivningarna är bytta) ---
    '1798': 'Avvaktar (Inbetalning)',  # Standard för INKOMMANDE
    '1799': 'Avvaktar (Utbetalning)',  # Standard för UTGÅENDE

    '1930': 'Bankkonto',
    '2440': 'Leverantörsskulder',
    '2611': 'Utgående moms (25%)',
    '2612': 'Utgående moms (12%)',
    '2613': 'Utgående moms (6%)',
    '2641': 'Ingående moms (25%)',
    '2642': 'Ingående moms (12%)',
    '2643': 'Ingående moms (6%)',
    '2893': 'Utlägg/Avräkning',
    '3041': 'Försäljning',
    '5410': 'Förbrukningsinventarier',
    '5611': 'Drivmedel',
    '6250': 'Porto',
    '6570': 'Banktjänster/Bankkostnader',
    '6991': 'Hyra',
}

#
# ===============================================================
#  АССОЦИАТИВНЫЕ ОПРЕДЕЛЕНИЯ
# ===============================================================
#
ASSOCIATION_MAP = {
    # Dina nya regler (de flesta fanns redan):
    'skatteverket': '1630',
    'lån': '1680',
    'bankkostnad': '6570',  # <-- KORRIGERING 2 (Nytt nyckelord)
    'bankkostnader': '6570',  # <-- KORRIGERING 2 (Nytt nyckelord)
    'utlägg': '2893',

    # Gamla regler:
    'lön': '1613',
    'avräkning': '2893',
    'avr': '2893',
    'bankavgift': '6570',
    'banktjänst': '6570',
    'leverantör': '2440',
    'försäljning': '3041',
    'hyra': '6991',
    'drivmedel': '5611',
    'okq8': '5611',
    'ingo': '5611',
}

#
# ===============================================================
#  KORRIGERING 3 (Logiken är bytt)
# ===============================================================
#
DEFAULT_KONTO_DEBIT = '1799'  # Används för Utbetalning (amount < 0)
DEFAULT_KONTO_KREDIT = '1798'  # Används för Inbetalning (amount > 0)


#
# ===============================================================
#  "УМНАЯ" ФУНКЦИЯ (Denna behöver inte ändras)
# ===============================================================
#
def get_contra_account(referens, amount):
    """
    Analyserar transaktionstexten och beloppet
    för att hitta rätt motkonto.
    """
    text = referens.lower()

    # 1. Moms först
    if 'moms' in text:
        if amount > 0:  # Inbetalning -> utgående moms
            return '2611'
        else:  # Utbetalning -> ingående moms
            return '2641'

    # 2. Sök efter nyckelord
    for keyword, account in ASSOCIATION_MAP.items():
        if keyword in text:
            return account

    # 3. Om inget hittas, använd standard
    if amount > 0:
        return DEFAULT_KONTO_KREDIT  # Blir nu 1798
    else:
        return DEFAULT_KONTO_DEBIT  # Blir nu 1799