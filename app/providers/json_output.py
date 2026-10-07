"""Parse one complete object without repairing, guessing or selecting nested JSON."""
import json
import re

from app.providers.base import ScriptProviderError


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate field')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('non-JSON constant')


def parse_json_object(text: str) -> dict:
    """Allow Markdown fences/harmless prose around ONE valid JSON object.

    Start at the first opening brace and never scan ahead after a parse failure.
    Extra objects, arrays, malformed outer objects and duplicate fields fail.
    """
    try:
        if not isinstance(text, str) or len(text) > 200000:
            raise ValueError()
        text = text.lstrip('\ufeff').strip()
        if re.search(r'</?think(?:ing)?\s*>', text, re.IGNORECASE):
            raise ValueError()
        decoder = json.JSONDecoder(object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        # Only recognize JSON/unlabelled fences; other code blocks are ambiguous.
        if '```' in text:
            match = re.fullmatch(r'([^`]*?)```(.*?)```([^`]*?)', text, re.DOTALL)
            if not match:
                raise ValueError()
            body = match[2].lstrip(' \t')
            if re.match(r'json(?:\s|\{)', body, re.IGNORECASE):
                body = body[4:]
            elif not body.startswith(('\n', '\r\n', '{')):
                raise ValueError()
            text = match[1] + body + match[3]
        start = text.find('{')
        if start < 0:
            raise ValueError()
        result, end = decoder.raw_decode(text, start)
        surrounding = text[:start] + text[end:]
        if not isinstance(result, dict) or any(char in surrounding for char in '{}[]'):
            raise ValueError()
        return result
    except (ValueError, TypeError, RecursionError):
        raise ScriptProviderError('Sağlayıcı tek ve geçerli bir JSON nesnesi döndürmedi. Eksik alanlar tamamlanmadı.', category='invalid_json') from None
