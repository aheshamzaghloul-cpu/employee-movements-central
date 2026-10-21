"""Compatibility exports for assistant result renderers.

Read helpers, movement reports, and directory/branch responses live in focused
modules. This facade preserves the established import names used by routes and
other application modules.
"""

from . import render_read as _render_read
from .topic_options import topic_options

_load_candidate_records = _render_read._load_candidate_records
_latest_current_movements = _render_read._latest_current_movements
_movement_status_text = _render_read._movement_status_text
_visible_branch = _render_read._visible_branch
employee_status_text = _render_read.employee_status_text
render_branch_entry = _render_read.render_branch_entry
render_read = _render_read.render_read

__all__ = [
    "employee_status_text",
    "render_branch_entry",
    "render_read",
    "topic_options",
]
