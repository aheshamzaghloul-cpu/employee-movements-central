from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'employee_movements' / 'blueprints' / 'missions.py').read_text(encoding='utf-8')
OCR = (ROOT / 'employee_movements' / 'services' / 'ticket_screenshot_ocr.py').read_text(encoding='utf-8')
PAGE = (ROOT / 'employee_movements' / 'templates' / 'mission_from_screenshot.html').read_text(encoding='utf-8')
DOCKER = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
REQUIREMENTS = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
HOOKS = (ROOT / 'employee_movements' / 'hooks.py').read_text(encoding='utf-8')
APP = (ROOT / 'employee_movements' / '__init__.py').read_text(encoding='utf-8')
CONFIG = (ROOT / 'employee_movements' / 'config.py').read_text(encoding='utf-8')


def test_screenshot_feature_uses_local_tesseract_via_stdin_and_only_returns_seven_fields():
    assert '["tesseract", "stdin", "stdout", "-l", "ara+eng"' in OCR
    assert 'extract_ticket_fields(image)' in ROUTES
    assert 'return result' in OCR
    assert '"basic_branch_name", "destination_branch_name", "job_code"' in OCR
    for field in ('destination_is_basic', 'needs_mission', 'from_date', 'to_date'):
        assert f'"{field}"' in OCR
    assert 'image.save(encoded, format="PNG", optimize=True)' in OCR
    assert 'requests' not in OCR and 'GEMINI' not in OCR and 'http://' not in OCR and 'https://' not in OCR
    assert 'can_manage_movement_employee' in ROUTES.split('from ..access import', 1)[1].splitlines()[0]


def test_uploaded_image_is_bounded_and_not_persisted_by_route():
    assert '2 * 1024 * 1024 + 1' in ROUTES
    assert 'MAX_IMAGE_PIXELS' in ROUTES
    assert 'SUPPORTED_FORMATS' in ROUTES
    scan_route = ROUTES.split("def mission_from_screenshot_scan():", 1)[1].split("@bp.post('/missions/from-screenshot/create')", 1)[0]
    assert 'upload.save(' not in scan_route
    assert 'Path(' not in scan_route


def test_mission_creation_requires_both_yes_and_checks_employee_branch_dates_scope_and_overlap():
    assert "should_create_mission(fields.get('destination_is_basic'), fields.get('needs_mission'))" in ROUTES
    assert "_ticket_mission_employee(fields['job_code'])" in ROUTES
    assert 'can_manage_movement_destination(destination, \'انتداب\')' in ROUTES
    assert "basic_branch_alias_match" in ROUTES
    assert "destination.id == employee.branch_id" in ROUTES
    assert "if not from_date or not to_date" in ROUTES
    assert "movement_overlaps(employee.id, 'انتداب', raw_from, raw_to, None)" in ROUTES


def test_review_form_contains_only_the_seven_ticket_fields_and_requires_confirmation():
    for field in ('basic_branch_name', 'destination_branch_id', 'job_code', 'destination_is_basic', 'needs_mission', 'from_date', 'to_date'):
        assert f'name="{field}"' in PAGE
    for forbidden in ('name="username"', 'name="supervisor"', 'name="email"', 'name="ticket_id"'):
        assert forbidden not in PAGE
    assert 'تأكيد البيانات وتسجيل المأمورية' in PAGE


def test_docker_installs_local_arabic_and_english_ocr_without_external_ocr_service():
    assert 'tesseract-ocr-ara' in DOCKER
    assert 'tesseract-ocr-eng' in DOCKER
    assert 'Pillow==12.3.0' in REQUIREMENTS


def test_screenshot_route_gets_its_own_bounded_multipart_limit():
    assert "SCREENSHOT_UPLOAD_MAX_CONTENT_LENGTH': 3 * 1024 * 1024" in CONFIG
    assert "missions.mission_from_screenshot_scan" in HOOKS
    assert "SCREENSHOT_UPLOAD_MAX_CONTENT_LENGTH" in HOOKS


def test_screenshot_upload_is_memory_only_and_audit_log_does_not_write_job_code():
    assert 'class ScreenshotInMemoryRequest(Request)' in HOOKS
    assert "self.endpoint == 'missions.mission_from_screenshot_scan'" in HOOKS
    assert 'return BytesIO()' in HOOKS
    assert 'def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None)' in HOOKS
    assert "return SpooledTemporaryFile(max_size=500 * 1024, mode='w+b')" in HOOKS
    assert 'def _parse_form_data(self, stream)' in HOOKS
    assert 'FormDataParser(' in HOOKS
    assert 'super()._get_file_stream(total_content_length, content_type, filename, content_length)' not in HOOKS
    assert 'ScreenshotInMemoryRequest' in APP
    route = ROUTES.split("def mission_from_screenshot_create():", 1)[1].split("@bp.get('/reports/assignments/mission-edit", 1)[0]
    assert 'إنشاء مأمورية من صورة تيكيت بعد مراجعة الحقول السبعة' in route
    assert 'employee.job_code or fields["job_code"]' not in route
