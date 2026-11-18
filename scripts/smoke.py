#!/usr/bin/env python3
"""Exercise a running Galvanise API with two Clerk session tokens.

Creates uniquely named test accounts/projects; never deletes existing data.
Usage: python3 scripts/smoke.py --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class Client:
    def __init__(self, base: str, token: str = ""):
        self.base = base.rstrip('/')
        self.token = token
        self.opener = urllib.request.build_opener()

    def request(self, method: str, path: str, payload: dict | None = None,
                expected: tuple[int, ...] = (200,), headers: dict | None = None,
                body: bytes | None = None) -> Any:
        hdrs = dict(headers or {})
        if self.token:
            hdrs['Authorization'] = 'Bearer ' + self.token
        if payload is not None:
            body = json.dumps(payload).encode()
            hdrs['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.base + '/api' + path, data=body, headers=hdrs, method=method)
        try:
            response = self.opener.open(req, timeout=60)
        except urllib.error.HTTPError as error:
            response = error
        text = response.read().decode()
        assert response.status in expected, f'{method} {path}: {response.status}, expected {expected}: {text[:500]}'
        if response.headers.get('Content-Type', '').startswith('application/json'):
            return json.loads(text)
        return text

    def upload(self, path: str, name: str, content: bytes, media_type: str = 'text/plain') -> Any:
        boundary = 'galvanise-' + secrets.token_hex(12)
        data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                f'Content-Type: {media_type}\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
        return self.request('POST', path, expected=(200, 201, 202), body=data,
                            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--graph-file', type=Path)
    parser.add_argument('--token', required=True, help='Clerk session token for the owner')
    parser.add_argument('--other-token', required=True, help='Clerk session token for a different user')
    args = parser.parse_args()
    a, b = Client(args.base_url, args.token), Client(args.base_url, args.other_token)
    health = a.request('GET', '/health')
    print('PASS health')
    Client(args.base_url).request('GET', '/projects', expected=(401,))
    user = a.request('GET', '/auth/me')
    other_user = b.request('GET', '/auth/me')
    assert user['id'] != other_user['id'], 'the two Clerk tokens must belong to different users'
    suffix = secrets.token_hex(5)
    print('PASS Clerk bearer authentication')

    project = a.request('POST', '/projects', {
        'name': 'Runtime verification ' + suffix, 'description': 'Automated API smoke test',
        'system_type': 'existing', 'objective': 'Verify persistence and isolation',
    }, (200, 201))
    project_path = '/projects/' + project['id']
    assert a.request('GET', project_path)['name'] == project['name']
    a.request('POST', '/projects', {'name': 'Cross origin', 'system_type': 'new', 'description': '', 'objective': 'Blocked'},
              expected=(403,), headers={'Origin': 'https://untrusted.invalid'})
    for route in ['', '/conversations', '/records', '/documents', '/sources', '/jobs', '/graphs']:
        b.request('GET', project_path + route, expected=(404,))
    print('PASS project persistence, ownership isolation and cross-origin mutation protection')

    conversation = a.request('POST', project_path + '/conversations', {'title': 'Persistent architect chat'}, (200, 201))
    conversation_path = project_path + '/conversations/' + conversation['id']
    assert a.request('GET', conversation_path + '/messages') == []
    if not health.get('ai_configured'):
        a.request('POST', conversation_path + '/chat', {'content': 'Identify supplier volatility'}, expected=(503,))
        a.request('POST', project_path + '/analyse', {}, expected=(503,))
        a.request('POST', project_path + '/architectures/generate', {}, expected=(503,))
        print('PASS missing OpenAI configuration gives actionable 503 errors')

    a.upload(project_path + '/documents', 'requirements.md', b'# Requirements\nSupplier onboarding must preserve purchasing rules.\n')
    deadline = time.monotonic() + 20
    documents: list = []
    while time.monotonic() < deadline:
        documents = a.request('GET', project_path + '/documents')
        if documents:
            break
        time.sleep(0.2)
    assert any(d['name'] == 'requirements.md' for d in documents), 'uploaded document was not ingested'
    print('PASS document upload and background ingestion')

    if args.graph_file:
        imported = a.upload(project_path + '/graphs/import', args.graph_file.name,
                            args.graph_file.read_bytes(), 'application/json')
        graph = a.request('GET', project_path + '/graphs/' + imported['id'])
        assert graph['nodes'], 'imported graph has no nodes'
        assert all(e['source'] in {n['id'] for n in graph['nodes']} and
                   e['target'] in {n['id'] for n in graph['nodes']} for e in graph['edges'])
        print('PASS actual Graphify import and structural graph retrieval')

    demo = a.request('POST', '/projects/demo', {}, (200, 201))
    records = a.request('GET', '/projects/' + demo['id'] + '/records')
    assert records, 'explicit demo seed did not populate knowledge'
    record = next((r for r in records if r['status'] == 'pending'), records[0])
    record_path = '/projects/' + demo['id'] + '/records/' + record['id']
    reviewed = a.request('PATCH', record_path, {'status': 'approved', 'expected_version': record['version']})
    assert reviewed['status'] == 'approved' and reviewed['version'] > record['version']
    a.request('PATCH', record_path, {'status': 'rejected', 'expected_version': record['version']}, expected=(409,))
    assert reviewed['history'], 'review must retain prior version'
    print('PASS explicit synthetic demo, review history and optimistic concurrency')

    assert any(c['id'] == conversation['id'] for c in a.request('GET', project_path + '/conversations'))
    assert a.request('GET', project_path)['id'] == project['id']
    print('PASS persistent project and conversation recovery')
    print('Runtime smoke checks passed. External OpenAI/GitHub calls were not exercised.')


if __name__ == '__main__':
    main()
