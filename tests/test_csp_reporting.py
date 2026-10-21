"""CSP migration/report endpoint smoke tests (Flask test suite)."""
import json


def test_report_only_header_is_opt_in_and_non_blocking(app, client):
    app.config['CSP_REPORT_ONLY'] = True
    response = client.get('/login')
    assert response.status_code == 200
    assert 'Content-Security-Policy' in response.headers
    report_policy = response.headers['Content-Security-Policy-Report-Only']
    assert "script-src 'self'" in report_policy
    assert 'report-uri /csp-report' in report_policy


def test_csp_report_accepts_browser_report_without_csrf(client):
    payload = {'csp-report': {
        'effective-directive': 'script-src-elem',
        'blocked-uri': 'https://example.invalid/script.js?secret=discard-me',
        'source-file': 'https://employee.example.invalid/home?private=discard-me',
        'status-code': 200,
    }}
    response = client.post(
        '/csp-report',
        data=json.dumps(payload),
        content_type='application/csp-report',
    )
    assert response.status_code == 204
    assert response.headers['Cache-Control'] == 'no-store'


def test_csp_report_rejects_unsupported_content_type(client):
    response = client.post('/csp-report', data='not a report', content_type='text/plain')
    assert response.status_code == 415


def test_csp_report_does_not_log_query_strings(client, caplog):
    caplog.set_level("INFO")
    payload = {'csp-report': {
        'effective-directive': 'script-src-elem',
        'blocked-uri': 'https://example.invalid/script.js?secret=discard-me',
        'source-file': 'https://employee.example.invalid/home?private=discard-me',
        'status-code': 200,
    }}
    response = client.post('/csp-report', data=json.dumps(payload), content_type='application/csp-report')
    assert response.status_code == 204
    assert 'discard-me' not in caplog.text


def test_csp_report_body_is_capped(client):
    response = client.post('/csp-report', data=('x' * (33 * 1024)), content_type='application/json')
    assert response.status_code == 413
