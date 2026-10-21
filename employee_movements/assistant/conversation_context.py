"""Outbound conversation-context packing for Gemini-backed assistant flows.

Only sanitized user-authored turns are packed. Assistant answers can contain live
employee and movement data, so they are never forwarded to the external model.
"""
from __future__ import annotations

MAX_CONVERSATION_TURNS = 20
MAX_CONVERSATION_CHARS = 16000
MAX_HISTORY_MESSAGES = 60
MAX_CONTEXT_TURNS = 20
MAX_HISTORY_TEXT_CHARS = 1800


def build_agent_contents(prior_chat, prompt):
    """Pack the recent sanitized user turns for the tool-selecting agent."""
    # Keep conversational continuity without forwarding assistant replies that may
    # contain live employee/movement data. Pack recent user turns into one clear
    # context message so follow-ups are interpreted against the whole request.
    prior = []
    for item in (prior_chat or [])[-30:]:
        if item.get("role") != "user":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            prior.append(text[:1200])
    prior = prior[-MAX_CONVERSATION_TURNS:]
    current_section = "رسالة المستخدم الحالية:\n" + str(prompt or "").strip()[:4000]
    # Reserve space for the current request and fill remaining space from the
    # newest prior turns backwards. Never let older context cut off the prompt.
    budget = MAX_CONVERSATION_CHARS - len(current_section) - 2
    selected = []
    used = 0
    for value in reversed(prior):
        entry = f"{len(prior) - len(selected)}. {value}"
        cost = len(entry) + (1 if selected else 0)
        if cost > budget - used:
            remaining = budget - used
            if remaining > 8:
                selected.append(entry[:remaining])
            break
        selected.append(entry)
        used += cost
    selected.reverse()
    sections = []
    if selected:
        sections.append("رسائل المستخدم السابقة بالترتيب (الأحدث أقرب للرسالة الحالية):\n" + "\n".join(selected))
    sections.append(current_section)
    packed = "\n\n".join(sections)
    return [{"role": "user", "parts": [{"text": packed[-MAX_CONVERSATION_CHARS:]}]}]


def history_for_language(chat, current_text=''):
    """Pack a compact user-only history for intent extraction."""
    prior = []
    for item in (chat or [])[-MAX_HISTORY_MESSAGES:]:
        if item.get('role') != 'user':
            continue
        text = str(item.get('text') or '').strip()
        if text:
            prior.append(text[:MAX_HISTORY_TEXT_CHARS])
    prior = prior[-MAX_CONTEXT_TURNS:]
    current_section = 'رسالة المستخدم الحالية:\n' + str(current_text or '').strip()[:4000]
    # Reserve space for the current request first. Add the newest prior turns
    # backwards so a long history can never truncate the current request or the
    # most recent context at the front of the packed prompt.
    budget = 16000 - len(current_section) - 2
    selected = []
    used = 0
    for value in reversed(prior):
        entry = f'{len(prior) - len(selected)}. {value}'
        cost = len(entry) + (1 if selected else 0)
        if cost > budget - used:
            remaining = budget - used
            if remaining > 8:
                selected.append(entry[:remaining])
            break
        selected.append(entry)
        used += cost
    selected.reverse()
    sections = []
    if selected:
        sections.append('رسائل المستخدم السابقة بالترتيب (الأحدث أقرب للرسالة الحالية):\n' + '\n'.join(selected))
    sections.append(current_section)
    packed = '\n\n'.join(sections)
    return [{'role': 'user', 'parts': [{'text': packed[-16000:]}]}]
