"""Canonical wire encoding used for every message, signature input and stored record.

Supported values: None, bool, non-negative int below 2**64, bytes, str, list, and
dict with str keys. Dict keys are written in sorted order and the decoder rejects
anything that is not canonical, so ``enc(dec(b)) == b`` for every accepted input.

Also provides ``sstr`` and ``u32``, the encodings used inside PRF inputs.
"""
from __future__ import annotations

import struct
from typing import Any

from .errors import WireError

_T_NONE, _T_FALSE, _T_TRUE, _T_INT, _T_BYTES, _T_STR, _T_LIST, _T_DICT = range(8)
_MAX_DEPTH = 32


def u32(value: int) -> bytes:
    """Big endian unsigned 32-bit integer."""
    return struct.pack(">I", value)


def u64(value: int) -> bytes:
    """Big endian unsigned 64-bit integer."""
    return struct.pack(">Q", value)


def sstr(text: str) -> bytes:
    """Length-prefixed string: u32 byte length followed by UTF-8 bytes."""
    raw = text.encode("utf-8")
    return u32(len(raw)) + raw


def _enc_into(obj: Any, out: bytearray, depth: int) -> None:
    if depth > _MAX_DEPTH:
        raise WireError("nesting too deep")
    if obj is None:
        out.append(_T_NONE)
    elif obj is True:
        out.append(_T_TRUE)
    elif obj is False:
        out.append(_T_FALSE)
    elif isinstance(obj, int):
        if not 0 <= obj < 2**64:
            raise WireError("integer out of range")
        out.append(_T_INT)
        out += u64(obj)
    elif isinstance(obj, (bytes, bytearray, memoryview)):
        raw = bytes(obj)
        out.append(_T_BYTES)
        out += u32(len(raw))
        out += raw
    elif isinstance(obj, str):
        raw = obj.encode("utf-8")
        out.append(_T_STR)
        out += u32(len(raw))
        out += raw
    elif isinstance(obj, (list, tuple)):
        out.append(_T_LIST)
        out += u32(len(obj))
        for item in obj:
            _enc_into(item, out, depth + 1)
    elif isinstance(obj, dict):
        out.append(_T_DICT)
        out += u32(len(obj))
        for key in sorted(obj):
            if not isinstance(key, str):
                raise WireError("dict keys must be str")
            raw = key.encode("utf-8")
            out += u32(len(raw))
            out += raw
            _enc_into(obj[key], out, depth + 1)
    else:
        raise WireError(f"unsupported type {type(obj).__name__}")


def enc(obj: Any) -> bytes:
    """Encode a value canonically."""
    out = bytearray()
    _enc_into(obj, out, 0)
    return bytes(out)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def take(self, n: int) -> bytes:
        end = self.pos + n
        if n < 0 or end > len(self.data):
            raise WireError("truncated input")
        chunk = self.data[self.pos:end]
        self.pos = end
        return chunk

    def u32(self) -> int:
        return struct.unpack(">I", self.take(4))[0]


def _dec_from(reader: _Reader, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        raise WireError("nesting too deep")
    tag = reader.take(1)[0]
    if tag == _T_NONE:
        return None
    if tag == _T_TRUE:
        return True
    if tag == _T_FALSE:
        return False
    if tag == _T_INT:
        return struct.unpack(">Q", reader.take(8))[0]
    if tag == _T_BYTES:
        return reader.take(reader.u32())
    if tag == _T_STR:
        try:
            return reader.take(reader.u32()).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WireError("invalid UTF-8") from exc
    if tag == _T_LIST:
        return [_dec_from(reader, depth + 1) for _ in range(reader.u32())]
    if tag == _T_DICT:
        result: dict[str, Any] = {}
        last: str | None = None
        for _ in range(reader.u32()):
            try:
                key = reader.take(reader.u32()).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise WireError("invalid UTF-8 key") from exc
            if last is not None and key <= last:
                raise WireError("dict keys not in canonical order")
            last = key
            result[key] = _dec_from(reader, depth + 1)
        return result
    raise WireError(f"unknown tag {tag}")


def dec(data: bytes) -> Any:
    """Decode a canonical value. Raises WireError on any deviation."""
    reader = _Reader(bytes(data))
    value = _dec_from(reader, 0)
    if reader.pos != len(reader.data):
        raise WireError("trailing bytes")
    return value
