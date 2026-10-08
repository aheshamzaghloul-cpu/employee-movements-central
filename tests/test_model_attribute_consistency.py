from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'employee_movements' / 'models.py'
TARGET_FILES = [
    path
    for path in (ROOT / 'employee_movements').rglob('*')
    if path.is_file() and path.suffix in {'.py', '.html', '.js'}
    and '__pycache__' not in path.parts
]


def test_movement_destination_relationship_uses_canonical_name():
    models = MODELS.read_text(encoding='utf-8')
    assert "destination = db.relationship('Branch', foreign_keys=[destination_branch_id])" in models

    import re

    for path in TARGET_FILES:
        text = path.read_text(encoding='utf-8')
        assert not re.search(r'\b[A-Za-z_][A-Za-z0-9_]*\.destination_branch\b', text), (
            f'Invalid Movement relationship name found in {path}'
        )


def test_movement_destination_column_remains_canonical():
    models = MODELS.read_text(encoding='utf-8')
    assert 'destination_branch_id = db.Column' in models
