#
# ===============================================================
#  ПЛАН СЧЕТОВ (KONTOPLAN) - Единый источник
# ===============================================================
#
KONTOPLAN = {
    '1613': 'Lön',
    '1630': 'Skatteverket',
    '1680': 'Lån',
    '1798': 'Avvaktar (Utbetalning)',  # Счет по умолчанию для исходящих
    '1799': 'Avvaktar (Inbetalning)',  # Счет по умолчанию для входящих
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
    '6570': 'Banktjänster',
    '6991': 'Hyra',
}

#
# ===============================================================
#  АССОЦИАТИВНЫЕ ОПРЕДЕЛЕНИЯ
# ===============================================================
#
ASSOCIATION_MAP = {
    'lön': '1613',
    'skatteverket': '1630',
    'lån': '1680',
    'utlägg': '2893',
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

DEFAULT_KONTO_DEBIT = '1798'
DEFAULT_KONTO_KREDIT = '1799'


#
# ===============================================================
#  "УМНАЯ" ФУНКЦИЯ (мы тоже перенесли ее сюда)
# ===============================================================
#
def get_contra_account(referens, amount):
    """
    Анализирует описание транзакции и сумму,
    чтобы найти правильный контра-счет.
    """
    text = referens.lower()

    # 1. Сначала НДС (moms)
    if 'moms' in text:
        if amount > 0:  # Insättning (входящий) -> utgående moms
            return '2611'
        else:  # Uttag (исходящий) -> ingående moms
            return '2641'

    # 2. Поиск по остальным ключевым словам
    for keyword, account in ASSOCIATION_MAP.items():
        if keyword in text:
            return account

    # 3. Если ничего не найдено, используем счет по умолчанию
    if amount > 0:
        return DEFAULT_KONTO_KREDIT  # 1799
    else:
        return DEFAULT_KONTO_DEBIT  # 1798