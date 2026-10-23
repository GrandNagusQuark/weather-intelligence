"""Useful diagnostics made only from static source vocabulary and numeric codes.

Never serialize exception text, arguments, source lines, paths, locals or URLs.
The identical validation module and catalog are shipped with the private inbox.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from .diagnostic_catalog import CATALOG

MESSAGES = CATALOG['messages']
MESSAGE_IDS = {value: key for key, value in MESSAGES.items()}
EXCEPTION_TYPES = frozenset(CATALOG['exceptions'])
ROOT = Path(__file__).parent
FIELDS = {'event', 'causes', 'frames'}
CAUSE_FIELDS = {'type', 'reason', 'http_status', 'errno', 'exit_code'}


def _number(value, low, high):
    return value if type(value) is int and low <= value <= high else None


def _attribute(error, name):
    try:
        return getattr(error, name, None)
    except Exception:
        return None


def _frame(filename, function, line):
    path = Path(filename)
    # Absolute paths are inspected only locally and are never put in a report.
    if path.parent != ROOT or path.suffix != '.py':
        return None
    module = path.stem
    if function not in CATALOG['functions'].get(module, ()) or not _number(line, 1, 100000):
        return None
    return {'module': module, 'function': function, 'line': line}


def build_diagnostics(record):
    error = getattr(record, 'wi_exception', None)
    if not isinstance(error, BaseException):
        error = record.exc_info[1] if record.exc_info and record.exc_info[1] else sys.exc_info()[1]
    if not isinstance(error, BaseException):
        # Existing callers sometimes pass the exception as a log argument.
        error = next((item for item in record.args if isinstance(item, BaseException)), None) if isinstance(record.args, tuple) else None
    causes, frames, visited = [], [], set()
    while isinstance(error, BaseException) and id(error) not in visited and len(causes) < 3:
        visited.add(id(error))
        name = type(error).__name__
        message = error.args[0] if error.args and isinstance(error.args[0], str) else None
        causes.append({'type': name if name in EXCEPTION_TYPES else 'Error',
            'reason': MESSAGE_IDS.get(message),
            'http_status': _number(_attribute(error, 'status') or _attribute(error, 'code'), 100, 599),
            'errno': _number(_attribute(error, 'errno'), -65535, 65535),
            'exit_code': _number(_attribute(error, 'returncode'), -2147483648, 2147483647)})
        trace = error.__traceback__
        while trace:
            code = trace.tb_frame.f_code
            frame = _frame(code.co_filename, code.co_name, trace.tb_lineno)
            if frame and frame not in frames:
                frames.append(frame)
            trace = trace.tb_next
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    if not frames:
        frame = _frame(record.pathname, record.funcName, record.lineno)
        if frame:
            frames.append(frame)
    return validate_diagnostics({'event': MESSAGE_IDS.get(record.msg) if isinstance(record.msg, str) else None,
                                 'causes': causes, 'frames': frames[-8:]})


def validate_diagnostics(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('Invalid diagnostic details')
    if value['event'] is not None and (not isinstance(value['event'], str) or value['event'] not in MESSAGES):
        raise ValueError('Invalid diagnostic event')
    if not isinstance(value['causes'], list) or len(value['causes']) > 3 or not isinstance(value['frames'], list) or len(value['frames']) > 8:
        raise ValueError('Invalid diagnostic details')
    for cause in value['causes']:
        if not isinstance(cause, dict) or set(cause) != CAUSE_FIELDS or not isinstance(cause['type'], str) or cause['type'] not in EXCEPTION_TYPES:
            raise ValueError('Invalid diagnostic cause')
        if cause['reason'] is not None and (not isinstance(cause['reason'], str) or cause['reason'] not in MESSAGES):
            raise ValueError('Invalid diagnostic reason')
        for field, low, high in (('http_status', 100, 599), ('errno', -65535, 65535), ('exit_code', -2147483648, 2147483647)):
            if cause[field] is not None and _number(cause[field], low, high) is None:
                raise ValueError('Invalid diagnostic code')
    for frame in value['frames']:
        if (not isinstance(frame, dict) or set(frame) != {'module', 'function', 'line'}
                or not isinstance(frame['module'], str) or not isinstance(frame['function'], str)
                or frame['function'] not in CATALOG['functions'].get(frame['module'], ())
                or _number(frame['line'], 1, 100000) is None):
            raise ValueError('Invalid diagnostic location')
    return json.loads(json.dumps(value))
