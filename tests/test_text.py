from employee_movements.assistant.text import extract_date, normalize_digits, normalize_for_search


def test_hamza_and_taa_marbuta_are_unified():
    assert normalize_for_search('إجازة') == normalize_for_search('اجازه')


def test_alef_maqsura_and_yaa_are_unified():
    assert normalize_for_search('منى') == normalize_for_search('مني')


def test_diacritics_and_tatweel_removed():
    assert normalize_for_search('مُحَمَّد') == normalize_for_search('محمد')
    assert normalize_for_search('مـحـمد') == 'محمد'


def test_arabic_indic_digits():
    assert normalize_digits('٢٠٢٥') == '2025'


def test_extract_date_pads_parts():
    assert extract_date('من 2025/3/7 إلى') == '2025-03-07'
    assert extract_date('بدون تاريخ') is None
