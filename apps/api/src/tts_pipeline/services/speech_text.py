"""Deterministic Vietnamese speech text, separate from subtitle display text."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from collections.abc import Mapping


SPEECH_TEXT_NORMALIZER_VERSION = "vi_speech_text_v2"

_URL_RE = re.compile(r"https?://[^\s]+|www\.[^\s]+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"(?<!\w)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?!\w)", re.IGNORECASE)
_DATE_RE = re.compile(r"(?<!\w)(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})(?!\w)")
_ISO_DATE_RE = re.compile(r"(?<!\w)(\d{4})-(\d{1,2})-(\d{1,2})(?!\w)")
_TIME_RE = re.compile(r"(?<!\w)(\d{1,2}):(\d{2})(?!\w)")
_RANGE_RE = re.compile(r"(?<!\w)(-?\d+(?:[.,]\d+)?)\s*[–—-]\s*(-?\d+(?:[.,]\d+)?)(x)?(?!\w)", re.IGNORECASE)
_MUL_RE = re.compile(r"(?<!\w)(\d+)\s*[x×]\s*(\d+)(?!\w)", re.IGNORECASE)
_SLASH_RE = re.compile(r"(?<!\w)(\d+)\s*/\s*(\d+)(?!\w)")
_CURRENCY_RE = re.compile(
    r"(?<!\w)([$€£₫])\s*(-?\d+(?:[.,]\d+)?)(?!\w)|"
    r"(?<!\w)(-?\d+(?:[.,]\d+)?)\s*(đ|vnđ|vnd|usd|eur|\$|€|£)(?!\w)",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(
    r"(?<=\d)\s*(kcal|cal|kg|mg|ml|cm|mm|km|m|g|l|%)(?!\w)",
    re.IGNORECASE,
)
_COMPLEX_MODEL_RE = re.compile(
    r"(?<!\w)(?=[A-Za-z0-9.-]*[A-Za-z])(?=[A-Za-z0-9.-]*\d)[A-Za-z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)+(?!\w)"
)
_ALNUM_MODEL_RE = re.compile(
    r"(?<!\w)(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]+(?!\w)"
)
_NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?(?!\w)")

_DIGITS = {
    "0": "không", "1": "một", "2": "hai", "3": "ba", "4": "bốn",
    "5": "năm", "6": "sáu", "7": "bảy", "8": "tám", "9": "chín",
}
_LETTER_NAMES = {
    "A": "a", "B": "bê", "C": "xê", "D": "đê", "E": "e", "F": "ép",
    "G": "giê", "H": "hát", "I": "i", "J": "giây", "K": "ca", "L": "e lờ",
    "M": "em", "N": "en", "O": "ô", "P": "pê", "Q": "quy", "R": "e rờ",
    "S": "ét", "T": "tê", "U": "u", "V": "vê", "W": "vê kép", "X": "ích",
    "Y": "i dài", "Z": "dét",
}
_UNITS = {
    "kcal": "ki lô ca lo", "cal": "ca lo", "kg": "ki lô gam", "mg": "mi li gam",
    "ml": "mi li lít", "cm": "xen ti mét", "mm": "mi li mét", "km": "ki lô mét",
    "m": "mét", "g": "gam", "l": "lít", "%": "phần trăm",
}
_CURRENCY_NAMES = {"$": "đô la", "€": "ơ rô", "£": "bảng anh", "₫": "đồng", "đ": "đồng", "vnđ": "đồng", "vnd": "đồng", "usd": "đô la", "eur": "ơ rô"}
_MODEL_UNIT_WORDS = frozenset(_UNITS)


@dataclass(frozen=True)
class SpeechText:
    display_text: str
    speech_text: str
    normalizer_version: str
    actions: tuple[str, ...]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["actions"] = list(self.actions)
        return payload


def build_vietnamese_speech_text(
    display_text: str,
    pronunciation_glossary: Mapping[str, str] | None = None,
) -> SpeechText:
    """Expand provider-ambiguous tokens without mutating subtitle authority.

    ``pronunciation_glossary`` is workspace/operator data. It only affects the
    spoken string and is applied before deterministic token expansion.
    """

    display = str(display_text or "")
    text = " ".join(display.split())
    actions: list[str] = []
    placeholders: dict[str, str] = {}

    def hold(value: str, action: str) -> str:
        key = f"__VI_SPEECH_{len(placeholders)}__"
        placeholders[key] = value
        actions.append(action)
        return f" {key} "

    glossary = {
        str(key).strip(): str(value).strip()
        for key, value in dict(pronunciation_glossary or {}).items()
        if str(key).strip() and str(value).strip()
    }
    for source, spoken in sorted(glossary.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(
            rf"(?<![\w.-]){re.escape(source)}(?![\w.-])",
            re.IGNORECASE,
        )
        text, count = pattern.subn(lambda _match: f" {spoken} ", text)
        if count:
            actions.append("apply_pronunciation_glossary")

    text = _URL_RE.sub(lambda match: hold(_spell_web(match.group(0)), "expand_url"), text)
    text = _EMAIL_RE.sub(lambda match: hold(_spell_email(match.group(0)), "expand_email"), text)
    text = _ISO_DATE_RE.sub(lambda match: hold(_date_words(match.group(3), match.group(2), match.group(1)), "expand_date"), text)
    text = _DATE_RE.sub(lambda match: hold(_date_words(match.group(1), match.group(2), match.group(3)), "expand_date"), text)
    text = _TIME_RE.sub(lambda match: hold(f"{_number_to_words(match.group(1))} giờ {_number_to_words(match.group(2))} phút", "expand_time"), text)
    def replace_currency(match: re.Match[str]) -> str:
        actions.append("expand_currency")
        return _replace_currency(match)

    text = _CURRENCY_RE.sub(replace_currency, text)
    text = _RANGE_RE.sub(
        lambda match: hold(
            f"từ {_number_to_words(match.group(1))} đến {_number_to_words(match.group(2))}"
            + (" lần" if match.group(3) else ""),
            "expand_numeric_range",
        ),
        text,
    )
    text = _MUL_RE.sub(lambda match: hold(f"{_number_to_words(match.group(1))} nhân {_number_to_words(match.group(2))}", "expand_multiplication"), text)
    text = _SLASH_RE.sub(lambda match: hold(f"{_number_to_words(match.group(1))} trên {_number_to_words(match.group(2))}", "expand_numeric_slash"), text)

    def replace_unit(match: re.Match[str]) -> str:
        actions.append("expand_unit")
        return " " + _UNITS[match.group(1).casefold()]

    text = _UNIT_RE.sub(replace_unit, text)

    def replace_model(match: re.Match[str]) -> str:
        token = match.group(0)
        if token.casefold() in _MODEL_UNIT_WORDS:
            return token
        actions.append("spell_alphanumeric_model")
        return " ".join(
            _DIGITS[char] if char.isdigit() else _LETTER_NAMES.get(char.upper(), char)
            for char in token
            if char not in "-."
        )

    text = _COMPLEX_MODEL_RE.sub(replace_model, text)
    text = _ALNUM_MODEL_RE.sub(replace_model, text)

    def replace_number(match: re.Match[str]) -> str:
        actions.append("expand_number")
        return _number_to_words(match.group(0))

    text = _NUMBER_RE.sub(replace_number, text)
    for key, value in placeholders.items():
        text = text.replace(key, value)
    text = re.sub(r"\s+", " ", text).strip()
    return SpeechText(
        display_text=display,
        speech_text=text,
        normalizer_version=SPEECH_TEXT_NORMALIZER_VERSION,
        actions=tuple(dict.fromkeys(actions)),
    )


def _replace_currency(match: re.Match[str]) -> str:
    symbol, leading_number, trailing_number, suffix = match.groups()
    raw_number = leading_number or trailing_number or "0"
    currency = symbol or suffix or "đ"
    return f" {_number_to_words(raw_number, locale_grouping=True)} {_CURRENCY_NAMES[currency.casefold()]} "


def _date_words(day: str, month: str, year: str) -> str:
    return f"ngày {_number_to_words(day)} tháng {_number_to_words(month)} năm {_number_to_words(year)}"


def _spell_web(value: str) -> str:
    text = re.sub(r"^https?://", "", value, flags=re.IGNORECASE).replace("www.", "")
    text = re.sub(r"[/]+", " gạch chéo ", text)
    text = text.replace(".", " chấm ").replace("-", " gạch ngang ")
    return "đường dẫn " + " ".join(_spell_model_piece(part) for part in text.split())


def _spell_email(value: str) -> str:
    local, domain = value.split("@", 1)
    domain = domain.replace(".", " chấm ").replace("-", " gạch ngang ")
    return f"{_spell_model_piece(local)} a còng {_spell_model_piece(domain)}"


def _spell_model_piece(value: str) -> str:
    return " ".join(_DIGITS.get(char, _LETTER_NAMES.get(char.upper(), char)) for char in value if char.isalnum())


def _number_to_words(raw: str, *, locale_grouping: bool = False) -> str:
    raw_value = str(raw)
    normalized = raw_value.replace(",", ".")
    if locale_grouping and "," not in raw_value and re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw_value):
        normalized = raw_value.replace(".", "")
    negative = normalized.startswith("-")
    normalized = normalized.lstrip("-")
    integer_raw, dot, decimal_raw = normalized.partition(".")
    integer = int(integer_raw or "0")
    words = _integer_to_words(integer)
    if dot and decimal_raw:
        words = f"{words} phẩy " + " ".join(_DIGITS[char] for char in decimal_raw if char.isdigit())
    return f"âm {words}" if negative else words


def _integer_to_words(value: int) -> str:
    number = max(0, int(value))
    if number == 0:
        return _DIGITS["0"]
    if number >= 1_000_000_000:
        return " ".join(_DIGITS[char] for char in str(number))
    groups: list[int] = []
    while number:
        groups.append(number % 1000)
        number //= 1000
    scale = ("", "nghìn", "triệu")
    parts: list[str] = []
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if not group:
            continue
        words = _under_thousand(group, full=bool(parts and group < 100))
        if scale[index]:
            words = f"{words} {scale[index]}"
        parts.append(words)
    return " ".join(parts)


def _under_thousand(value: int, *, full: bool) -> str:
    hundreds, remainder = divmod(int(value), 100)
    tens, ones = divmod(remainder, 10)
    parts: list[str] = []
    if hundreds:
        parts.extend((_DIGITS[str(hundreds)], "trăm"))
    elif full:
        parts.extend(("không", "trăm"))
    if tens >= 2:
        parts.extend((_DIGITS[str(tens)], "mươi"))
        if ones == 1:
            parts.append("mốt")
        elif ones == 5:
            parts.append("lăm")
        elif ones:
            parts.append(_DIGITS[str(ones)])
    elif tens == 1:
        parts.append("mười")
        if ones == 5:
            parts.append("lăm")
        elif ones:
            parts.append(_DIGITS[str(ones)])
    elif ones:
        if hundreds or full:
            parts.append("lẻ")
        parts.append(_DIGITS[str(ones)])
    return " ".join(parts)
