"""Danh sách ngân hàng Việt Nam và nhận diện tên ngân hàng tự do -> mã BIN."""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import requests

BANKS_URL = "https://api.vietqr.io/v2/banks"
LOCAL_BANKS_FILE = Path(__file__).resolve().parent.parent / "data" / "banks.json"

# Các cách gọi phổ biến không có sẵn trong danh sách của VietQR
EXTRA_ALIASES = {
    "VCB": ["ngoai thuong", "vietcom"],
    "ICB": ["vietin", "cong thuong", "ctg"],
    "VBA": ["agri", "nong nghiep", "nong nghiep va phat trien nong thon", "nnptnt"],
    "BIDV": ["dau tu va phat trien", "dau tu"],
    "MB": ["mb", "quan doi", "mb bank"],
    "TCB": ["techcom", "ky thuong"],
    "VPB": ["vp", "viet nam thinh vuong"],
    "STB": ["sacom", "sai gon thuong tin"],
    "TPB": ["tp", "tien phong"],
    "HDB": ["hd", "phat trien nha thanh pho ho chi minh", "phat trien nha tp hcm", "phat trien nha"],
    "EIB": ["exim", "xuat nhap khau"],
    "MSB": ["maritime", "hang hai"],
    "VCCB": ["ban viet", "viet capital", "bvbank"],
    "SHB": ["sai gon ha noi"],
    "SEAB": ["sea", "dong nam a"],
    "LPB": ["lienviet", "lien viet", "lienvietpostbank", "loc phat", "lpb"],
    "ABB": ["an binh", "ab"],
    "NAB": ["nam a"],
    "BAB": ["bac a"],
    "KLB": ["kien long"],
    "OCB": ["phuong dong"],
    "VIETBANK": ["viet nam thuong tin"],
    "BVB": ["bao viet"],
    "PVCB": ["pvcom", "dai chung"],
    "SGICB": ["saigonbank", "sai gon cong thuong"],
    "SCB": ["sai gon"],
    "NCB": ["quoc dan"],
    "MBV": ["oceanbank", "ocean", "viet nam hien dai"],
    "CBB": ["xay dung"],
    "GPB": ["dau khi toan cau"],
    "Vikki": ["dongabank", "dong a"],
    "VAB": ["viet a"],
    "PGB": ["pg", "xang dau petrolimex"],
    "SHBVN": ["shinhan"],
    "WVN": ["woori"],
    "SCVN": ["standard chartered"],
    "momo": ["vi momo"],
    "VTLMONEY": ["viettel money", "viettelpay"],
}

_STOPWORDS = re.compile(
    r"\b(ngan hang|nh|tmcp|thuong mai co phan|tnhh|mtv|bank|chi nhanh|cn|jsc|pgd)\b"
)


def normalize(text: str) -> str:
    """Bỏ dấu tiếng Việt, chữ thường, bỏ ký tự đặc biệt."""
    text = str(text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _core(text: str) -> str:
    return re.sub(r"\s+", " ", _STOPWORDS.sub(" ", normalize(text))).strip()


@dataclass(frozen=True)
class Bank:
    code: str
    bin: str
    short_name: str
    name: str
    lookup_supported: bool = True

    @property
    def label(self) -> str:
        return f"{self.short_name} ({self.code})"


def load_banks(online: bool = True, timeout: float = 10) -> list[Bank]:
    """Lấy danh sách ngân hàng từ VietQR; lỗi mạng thì dùng bản lưu sẵn."""
    raw = None
    if online:
        try:
            resp = requests.get(BANKS_URL, timeout=timeout)
            resp.raise_for_status()
            raw = resp.json().get("data")
        except (requests.RequestException, ValueError):
            raw = None
    if not raw:
        raw = json.loads(LOCAL_BANKS_FILE.read_text(encoding="utf-8"))
    return [
        Bank(
            code=b["code"],
            bin=str(b["bin"]),
            short_name=b.get("shortName") or b.get("short_name") or b["code"],
            name=b["name"],
            lookup_supported=bool(b.get("lookupSupported", 1)),
        )
        for b in raw
    ]


# Phần chi nhánh/PGD phía sau tên ngân hàng: "..._CN Khánh Hòa_PGD Cam Ranh", "... - Chi nhánh Phú Yên"
_BRANCH_SPLIT = re.compile(r"\s*\b(?:cn|chi nhanh|pgd|phong giao dich)\b")

# Đơn vị không thuộc hệ thống Napas 247 -> không thể tra cứu tên
NOT_SUPPORTED = {"kho bac": "Kho bạc Nhà nước không hỗ trợ tra cứu tên qua Napas"}


def strip_branch(text: str) -> str:
    """'Ngân Hàng TMCP Á Châu_CN Sài Gòn' -> 'ngan hang tmcp a chau'."""
    first = str(text or "").split("_", 1)[0]
    head = _BRANCH_SPLIT.split(normalize(first), maxsplit=1)[0].strip()
    return head or normalize(text)


def unsupported_reason(text: str) -> str | None:
    norm = normalize(text)
    for key, reason in NOT_SUPPORTED.items():
        if norm.startswith(key) or f" {key} " in f" {norm} ":
            return reason
    return None


class BankMatcher:
    """Đoán ngân hàng từ chuỗi người dùng nhập (VCB, Vietcombank, NH Ngoại thương, 970436...)."""

    def __init__(self, banks: list[Bank]):
        self.banks = banks
        self._exact: dict[str, Bank] = {}
        for b in banks:
            keys = [b.code, b.bin, b.short_name, b.name, *EXTRA_ALIASES.get(b.code, [])]
            for k in keys:
                for variant in (normalize(k), _core(k), normalize(k).replace(" ", "")):
                    if variant:
                        self._exact.setdefault(variant, b)

    def match(self, text: str) -> Bank | None:
        if text is None or not normalize(text):
            return None
        head = strip_branch(text)
        if head != normalize(text):
            found = self._match(head)
            if found:
                return found
        return self._match(text)

    def _match(self, text: str) -> Bank | None:
        norm = normalize(text)
        for variant in (norm, _core(text), norm.replace(" ", ""), _core(text).replace(" ", "")):
            if variant and variant in self._exact:
                return self._exact[variant]
        core = _core(text)
        # Tên ngân hàng nằm trong chuỗi (vd "Vietcombank - CN Nha Trang")
        best, best_len = None, 0
        for key, bank in self._exact.items():
            if len(key) >= 4 and re.search(rf"\b{re.escape(key)}\b", core or norm):
                if len(key) > best_len:
                    best, best_len = bank, len(key)
        if best:
            return best
        close = difflib.get_close_matches(core or norm, list(self._exact), n=1, cutoff=0.8)
        return self._exact[close[0]] if close else None
