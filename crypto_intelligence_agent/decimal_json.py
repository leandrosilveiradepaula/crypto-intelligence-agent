"""Exact JSON numeric boundary for Kraken public research data.

Python's standard json.loads decodes non-integral JSON numbers to binary
float by default. This module preserves the source's numeric text using
Decimal without any network, trading, or third-party dependencies.

This is a *precision* guarantee about decoding, not a guarantee of
exchange-reported accuracy, candle-volume units or market-data licensing.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any

from .market_data import DataValidationError


MAX_PUBLIC_JSON_BYTES = 4_194_304
MAX_NUMBER_DIGITS = 40
MAX_NUMBER_TOKEN_LENGTH = 96
MAX_EXPONENT = 35
MIN_EXPONENT = -24
_FIXED_POSITIVE = re.compile(r"(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,24})?")


def _validate_source_decimal(value: Decimal, label: str) -> Decimal:
    if not value.is_finite():
        raise DataValidationError(f"{label} is not finite")
    tup = value.as_tuple()
    if (len(tup.digits) > MAX_NUMBER_DIGITS
            or value.adjusted() > MAX_EXPONENT
            or tup.exponent < MIN_EXPONENT):
        raise DataValidationError(f"{label} exceeds supported exact JSON numeric bounds")
    return value


def _parse_float_token(token: str) -> Decimal:
    if len(token) > MAX_NUMBER_TOKEN_LENGTH:
        raise DataValidationError("JSON fractional number token is too long")
    try:
        value = Decimal(token)
    except InvalidOperation as error:
        raise DataValidationError("JSON fractional number is malformed") from error
    return _validate_source_decimal(value, "JSON fractional number")


def _parse_int_token(token: str) -> int:
    if len(token.lstrip("-")) > MAX_NUMBER_DIGITS:
        raise DataValidationError("JSON integer has too many digits")
    return int(token)


def _reject_nonfinite_constant(token: str) -> None:
    raise DataValidationError("nonstandard NaN/Infinity constants are forbidden")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DataValidationError("duplicate market JSON keys are forbidden")
        result[key] = value
    return result


def decode_public_market_json_exact(
    raw: str | bytes, *, max_bytes: int = MAX_PUBLIC_JSON_BYTES,
) -> dict[str, Any]:
    """Decode a bounded public JSON OBJECT with Decimal for fractional numbers.

    The caller is responsible for HTTP access, source authenticity and age.
    """
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_PUBLIC_JSON_BYTES:
        raise ValueError("max_bytes must be within the public read-only budget")
    if not isinstance(raw, (str, bytes)):
        raise DataValidationError("public market JSON must be UTF-8 text or bytes")
    if isinstance(raw, str):
        try:
            payload = raw.encode("utf-8")
        except UnicodeEncodeError as error:
            raise DataValidationError("invalid UTF-8 market JSON") from error
    else:
        payload = raw
    if len(payload) == 0 or len(payload) > max_bytes:
        raise DataValidationError("market JSON body is empty or oversized")
    try:
        value = json.loads(
            payload,
            parse_float=_parse_float_token,
            parse_int=_parse_int_token,
            parse_constant=_reject_nonfinite_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise DataValidationError("malformed public market JSON") from error
    if not isinstance(value, dict):
        raise DataValidationError("public market JSON root must be an object")
    return value


def positive_market_decimal(value: Any, label: str) -> Decimal:
    """Require exact Decimal/int/fixed-point string; never accept Python float.

    Once raw JSON was decoded to binary float, its original decimal digits
    cannot be recovered. The caller MUST go back to the source and decode
    through decode_public_market_json_exact instead of faking precision.
    """
    if type(value) is bool or value is None:
        raise DataValidationError(f"{label} missing or boolean")
    if isinstance(value, Decimal):
        parsed = value
    elif type(value) is int:
        if len(str(abs(value))) > MAX_NUMBER_DIGITS:
            raise DataValidationError(f"{label} integer exceeds supported size")
        parsed = Decimal(value)
    elif type(value) is str and _FIXED_POSITIVE.fullmatch(value) is not None:
        parsed = Decimal(value)
    else:
        raise DataValidationError(f"{label} requires exact Decimal/int/fixed-point string, never float")
    _validate_source_decimal(parsed, label)
    if parsed <= 0:
        raise DataValidationError(f"{label} must be positive")
    return parsed
