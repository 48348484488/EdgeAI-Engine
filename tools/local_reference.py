"""Optional loopback-only llama-server adapter; standard library, no cloud fallback.

The adapter never downloads, starts a server, executes model tool calls, follows
redirects, or sends source files. An explicit caller supplies prompt text only.
CPU/energy of the *server* are unknown, not inferred from client measurements.
"""
from __future__ import annotations
import http.client
import ipaddress
import json
import math
import time
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 2 * 1024 * 1024

class ReferenceError(RuntimeError):
    """An unavailable backend or an invalid HTTP contract, not a model answer."""


def validate_endpoint(endpoint: str) -> tuple[str, int]:
    if not isinstance(endpoint, str) or any(ord(c) < 33 for c in endpoint):
        raise ValueError('endpoint must be a plain loopback HTTP URL')
    u = urlsplit(endpoint)
    if (u.scheme != 'http' or u.username is not None or u.password is not None
            or u.query or u.fragment or u.path not in ('', '/', '/v1', '/v1/')):
        raise ValueError('use http://127.0.0.1:PORT/v1 without credentials or query')
    host = u.hostname
    if host == 'localhost':
        host = '127.0.0.1'  # No DNS or hosts-file ambiguity.
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError('only literal loopback addresses or localhost allowed') from exc
    if not addr.is_loopback:
        raise ValueError('remote inference is disabled; only loopback allowed')
    port = u.port if u.port is not None else 80
    if not 1 <= port <= 65535:
        raise ValueError('invalid port')
    return str(addr), port


class LocalReferenceClient:
    def __init__(self, endpoint: str = 'http://127.0.0.1:8080/v1', *, timeout: float = 30):
        self.host, self.port = validate_endpoint(endpoint)
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 120:
            raise ValueError('socket timeout must be finite and in (0, 120] seconds')
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        # http.client ignores proxy environment variables and never follows redirects.
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        body = None if payload is None else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        try:
            connection.request(method, path, body=body, headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
            response = connection.getresponse()
            if response.status != 200:
                raise ReferenceError(f'local reference returned HTTP {response.status}; no redirect/fallback performed')
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ReferenceError('reference response exceeds 2 MiB')
            try:
                obj = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise ReferenceError('invalid JSON from local reference') from exc
            if not isinstance(obj, dict):
                raise ReferenceError('reference response must be a JSON object')
            return obj
        except (OSError, http.client.HTTPException) as exc:
            raise ReferenceError(f'local reference unavailable at {self.host}:{self.port}: {exc}') from exc
        finally:
            connection.close()

    def model_ids(self) -> list[str]:
        rows = self._request('GET', '/v1/models').get('data')
        if not isinstance(rows, list):
            raise ReferenceError('invalid /v1/models response')
        ids = [row.get('id') for row in rows if isinstance(row, dict)]
        if not ids or any(not isinstance(x, str) or not x for x in ids):
            raise ReferenceError('server did not provide a valid model id')
        return ids

    def ask(self, prompt: str, *, model: str | None = None, max_tokens: int = 32) -> dict:
        if not isinstance(prompt, str) or len(prompt.encode('utf-8')) > 65536:
            raise ValueError('prompt must be UTF-8 text of at most 65536 bytes')
        if type(max_tokens) is not int or not 1 <= max_tokens <= 512:
            raise ValueError('max_tokens must be integer in 1..512')
        if model is not None and (not isinstance(model, str) or not model or len(model) > 512):
            raise ValueError('invalid model id')
        start = time.perf_counter()
        if model is None:
            ids = self.model_ids()
            if len(ids) != 1:
                raise ReferenceError('multiple models available; choose an explicit model id')
            model = ids[0]
        payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                   'max_tokens': max_tokens, 'temperature': 0, 'seed': 0,
                   'stream': False, 'cache_prompt': False}
        obj = self._request('POST', '/v1/chat/completions', payload)
        choices = obj.get('choices')
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ReferenceError('missing completion choice')
        message = choices[0].get('message')
        if not isinstance(message, dict) or not isinstance(message.get('content'), str):
            raise ReferenceError('completion has no textual content; tool-only replies are not executed')
        result = {'backend': 'llama-server-reference', 'text': message['content'],
                  'model': obj.get('model', model), 'requested_model': model,
                  'finish_reason': choices[0].get('finish_reason'),
                  'wall_seconds': time.perf_counter() - start,
                  'server_cpu_seconds': None, 'energy_joules': None,
                  'server_already_running': True, 'max_tokens': max_tokens,
                  'usage': obj.get('usage'), 'server_timings': obj.get('timings')}
        # JSON is stored as data; no generated code, filenames or calls are executed.
        return result
