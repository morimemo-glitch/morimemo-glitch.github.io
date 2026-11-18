"""商品名から内容量を読み取る。読めないものは None を返して比較から外す。"""
import re
import unicodedata

UNIT_FACTORS = {
    # 基準単位: g / ml / L / kg / m
    "g": {"g": 1, "kg": 1000},
    "kg": {"kg": 1, "g": 0.001},
    "L": {"l": 1, "ml": 0.001},
    "ml": {"ml": 1, "l": 1000},
    "m": {"m": 1},
}

# 「×6本」「6本セット」「3袋」「2ケース」などのまとめ数
PACK_RE = re.compile(
    r"(?:[x×*]\s*(\d{1,3})\s*(?:本|袋|個|パック|セット|箱|ケース|缶)?)"
    r"|(?:(\d{1,3})\s*(?:本|袋|個|パック|箱|ケース)\s*(?:セット|入り?|組)?)"
)


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFKC", name)
    s = s.replace("リットル", "l").replace("キロ", "kg").replace("グラム", "g")
    s = s.replace("ℓ", "l")
    return s.lower()


def _amounts(s: str, unit: str):
    """名前中の量表記を基準単位に直して列挙する。"""
    factors = UNIT_FACTORS[unit]
    keys = sorted(factors, key=len, reverse=True)
    pat = re.compile(r"(\d+(?:\.\d+)?)\s*(" + "|".join(keys) + r")(?![a-z])")
    out = []
    for m in pat.finditer(s):
        val = float(m.group(1)) * factors[m.group(2)]
        if val > 0:
            out.append((val, m.end()))
    return out


def _pack_after(s: str, pos: int) -> int:
    m = PACK_RE.search(s, pos, pos + 16)
    if not m:
        return 1
    n = int(m.group(1) or m.group(2))
    return n if 1 <= n <= 100 else 1


def parse_amount(name: str, unit: str):
    s = normalize(name)
    found = _amounts(s, unit)
    if not found:
        return None
    # 最初に出てくる量 × その直後のまとめ数
    val, end = found[0]
    total = val * _pack_after(s, end)
    # 「2ケース」「定期便 6回」などの追加の倍数
    extra = re.search(r"(?<![x×*\d])(\d{1,2})\s*(?:ケース|回(?:定期|お届け)?)(?!分)", s[end:])
    if extra and ("ケース" in extra.group(0) or "定期" in s):
        total *= int(extra.group(1))
    return total


def parse_rolls_x_length(name: str, unit: str = "m"):
    s = normalize(name)
    rolls = re.search(r"(\d{1,3})\s*ロール", s)
    length = re.search(r"(\d{2,3}(?:\.\d+)?)\s*m(?![a-z])", s)
    if not rolls or not length:
        return None
    total = int(rolls.group(1)) * float(length.group(1))
    pack = re.search(r"[x×*]\s*(\d{1,2})\s*(?:パック|袋|セット|ケース)", s)
    if pack:
        total *= int(pack.group(1))
    return total


def parse_boxes_x_pairs(name: str, unit: str = "組"):
    """ボックスティッシュ：「150組 5箱」「160W×60個」などから総組数を出す"""
    s = normalize(name)
    pairs = re.search(r"(\d{2,4})\s*(?:組|w(?![a-z]))", s)
    boxes = re.search(r"(\d{1,3})\s*(?:箱|個|コ)(?!分)", s)
    if not pairs or not boxes:
        return None
    total = int(pairs.group(1)) * int(boxes.group(1))
    pack = re.search(r"[x×*]\s*(\d{1,2})\s*(?:パック|セット|ケース)", s)
    if pack:
        total *= int(pack.group(1))
    return total


PARSERS = {"amount": parse_amount, "rolls_x_length": parse_rolls_x_length,
           "boxes_x_pairs": parse_boxes_x_pairs}


def parse(name: str, kind: str, unit: str):
    return PARSERS[kind](name, unit)
