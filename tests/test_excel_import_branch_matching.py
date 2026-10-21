from employee_movements.services.excel_import_schema import EMP_IMPORT_HEADERS, _auto_map_headers


def test_generic_english_code_header_maps_to_employee_code_not_branch_code():
    mapping = _auto_map_headers(
        ['Governorate', 'Branch', 'Code', 'Name', 'Job Title', 'Hire Date'],
        EMP_IMPORT_HEADERS,
    )
    assert mapping['job_code'] == 3
    assert 'branch_code' not in mapping


def test_short_ambiguous_arabic_code_header_requires_explicit_mapping():
    mapping = _auto_map_headers(
        ['المحافظة', 'الفرع', 'كود', 'اسم الموظف', 'الوظيفة', 'تاريخ التعيين'],
        EMP_IMPORT_HEADERS,
    )
    assert 'branch_code' not in mapping
    assert mapping['name'] == 4
