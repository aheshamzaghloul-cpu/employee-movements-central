"""Contracts for ticket-image staging, persistence, and official PDF inclusion."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = (ROOT / 'employee_movements' / 'models.py').read_text(encoding='utf-8')
ROUTES = (ROOT / 'employee_movements' / 'blueprints' / 'missions.py').read_text(encoding='utf-8')
DOCS = (ROOT / 'employee_movements' / 'services' / 'mission_documents.py').read_text(encoding='utf-8')
BOOTSTRAP = (ROOT / 'employee_movements' / 'bootstrap.py').read_text(encoding='utf-8')
PAGE = (ROOT / 'employee_movements' / 'templates' / 'mission_from_screenshot.html').read_text(encoding='utf-8')
EDIT_PAGE = (ROOT / 'employee_movements' / 'templates' / 'mission_edit.html').read_text(encoding='utf-8')


def test_uploaded_ticket_has_separate_lazy_loaded_attachment_and_temporary_draft_tables():
    assert "__tablename__ = 'mission_ticket_image'" in MODELS
    assert "__tablename__ = 'mission_ticket_image_draft'" in MODELS
    assert "UniqueConstraint('movement_id', name='uq_mission_ticket_image_movement')" in MODELS
    assert 'image_data = db.Column(db.LargeBinary, nullable=False)' in MODELS
    assert 'sha256 = db.Column(db.String(64), nullable=False)' in MODELS
    assert 'MissionTicketImageDraft.created_at < cutoff' in ROUTES


def test_scan_stages_image_and_create_links_it_transactionally_to_mission():
    scan = ROUTES.split('def mission_from_screenshot_scan():', 1)[1].split("@bp.post('/missions/from-screenshot/create')", 1)[0]
    create = ROUTES.split('def mission_from_screenshot_create():', 1)[1].split("@bp.get('/reports/assignments/mission-edit", 1)[0]
    assert 'normalize_ticket_image(image_bytes)' in scan
    assert 'MissionTicketImageDraft(' in scan
    assert 'image_draft_token = secrets.token_urlsafe(32)' in scan
    assert 'token=image_draft_token' in scan
    assert 'MissionTicketImage.query.filter_by(movement_id=m.id).first()' in ROUTES
    assert 'MissionTicketImage(' in create
    assert 'image_data=ticket_image_draft.image_data' in create
    assert 'db.session.delete(ticket_image_draft)' in create
    assert 'ticket_image_required' in create
    assert 'uploaded_by=me().id' in create


def test_image_drafts_expire_and_are_cleaned_on_startup():
    assert 'timedelta(minutes=30)' in ROUTES
    assert 'def _cleanup_expired_mission_ticket_image_drafts()' in BOOTSTRAP
    assert '_cleanup_expired_mission_ticket_image_drafts()' in BOOTSTRAP
    assert 'MissionTicketImageDraft.query.filter(MissionTicketImageDraft.created_at < cutoff).delete' in BOOTSTRAP


def test_official_mission_pdf_appends_image_page_without_changing_form_page():
    assert 'ticket_image_data=None' in DOCS
    assert 'if ticket_image_data:' in DOCS
    assert '_append_ticket_image_page(doc, ticket_image_data, mission, employee, root_path)' in DOCS
    assert 'doc.new_page(-1, width=595.32, height=841.92)' in DOCS
    assert 'page.insert_image(image_rect, stream=payload, keep_proportion=True)' in DOCS
    assert ROUTES.count('ticket_image_data=ticket_image.image_data if ticket_image else None') == 2


def test_user_is_told_about_temporary_storage_and_pdf_attachment():
    assert 'تُحفظ الصورة مؤقتًا في قاعدة البيانات لمدة تصل إلى 30 دقيقة' in PAGE
    assert 'تظهر كصفحة ثانية في ملف PDF الرسمي' in PAGE
    assert 'name="ticket_image_draft_token"' in PAGE
    assert 'name="ticket_image_required"' in PAGE


def test_existing_missions_can_receive_or_replace_ticket_image_without_duplicate_movement():
    image_route = ROUTES.split("def mission_ticket_image_save(movement_id):", 1)[1].split("def _mission_center_return_url", 1)[0]
    assert "@bp.post('/reports/assignments/mission-ticket-image/<int:movement_id>')" in ROUTES
    assert "can('manage_movements')" in image_route and 'can_manage_movement(m)' in image_route
    assert 'normalize_ticket_image(raw_image)' in image_route
    assert 'MissionTicketImage.query.filter_by(movement_id=m.id).first()' in image_route
    assert "log('UPDATE', 'Movement', m.id, 'إرفاق أو استبدال صورة تيكيت المأمورية')" in image_route
    assert 'mission_ticket_image_save' in EDIT_PAGE
    assert 'name="ticket_image"' in EDIT_PAGE
    assert 'إرفاق صورة مأمورية سابقة لم تكن محفوظة' in EDIT_PAGE
    edit_helper = ROUTES.split('def _render_mission_edit_form(', 1)[1].split("@bp.get('/reports/assignments/mission-edit/", 1)[0]
    assert 'ticket_image_present=MissionTicketImage.query.filter_by(movement_id=m.id).first() is not None' in edit_helper
