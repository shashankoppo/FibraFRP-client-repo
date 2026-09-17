"""Redaction for diagnostics and AI input; never modify stored customer messages."""
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_KEYS = {'access_token', 'authorization', 'app_secret', 'api_key', 'password', 'secret', 'token'}
CONTENT_KEYS = {'to', 'phone', 'phone_number', 'email', 'body', 'text', 'caption', 'input_text'}


def redact_text(value):
    value = re.sub(r'(?i)\bBearer\s+\S+', 'Bearer [redacted]', str(value or ''))
    value = re.sub(r'(?i)(access_token|app_secret|api_key|password|secret|token)([\s"\x27:=]+)[^\s,"\x27&}]+',
                   r'\1\2[redacted]', value)
    value = re.sub(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', '[email]', value, flags=re.I)
    return re.sub(r'(?<!\w)\+?\d[\d ()-]{8,}\d(?!\w)', '[phone]', value)


def redact(value, content=False):
    if isinstance(value, dict):
        keys = SECRET_KEYS | (CONTENT_KEYS if content else set())
        return {key: '[redacted]' if str(key).lower() in keys else
                item if key in ('id', 'wamid') else redact(item, content=content)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, content=content) for item in value]
    return redact_text(value) if isinstance(value, str) else value


def redact_json(value, content=False):
    try:
        return json.dumps(redact(json.loads(value), content=content), ensure_ascii=True)
    except (ValueError, TypeError):
        return redact_text(value)


def redact_url(value):
    parts = urlsplit(value or '')
    query = [(key, '[redacted]' if key.lower() in SECRET_KEYS else val) for key, val in parse_qsl(parts.query)]
    return urlunsplit((parts.scheme, parts.netloc.rsplit('@', 1)[-1], parts.path, urlencode(query), ''))
