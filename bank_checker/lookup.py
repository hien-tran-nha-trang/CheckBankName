"""Gọi API tra cứu tên chủ tài khoản (VietQR - https://api.vietqr.io/v2/lookup)."""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests

LOOKUP_URL = "https://api.vietqr.io/v2/lookup"


@dataclass
class LookupResult:
    ok: bool
    account_name: str = ""
    message: str = ""


class VietQRLookup:
    def __init__(self, client_id: str, api_key: str, timeout: float = 20, retries: int = 2):
        if not client_id or not api_key:
            raise ValueError("Thiếu VIETQR_CLIENT_ID hoặc VIETQR_API_KEY")
        self.session = requests.Session()
        self.session.headers.update(
            {"x-client-id": client_id, "x-api-key": api_key, "Content-Type": "application/json"}
        )
        self.timeout = timeout
        self.retries = retries

    def lookup(self, bin_code: str, account_number: str) -> LookupResult:
        payload = {"bin": int(bin_code), "accountNumber": account_number}
        last_error = ""
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.post(LOOKUP_URL, json=payload, timeout=self.timeout)
                if resp.status_code == 429:
                    last_error = "Vượt giới hạn số lần gọi API (429)"
                    time.sleep(2 * (attempt + 1))
                    continue
                body = resp.json()
            except requests.RequestException as e:
                last_error = f"Lỗi kết nối: {e}"
                time.sleep(1 + attempt)
                continue
            except ValueError:
                return LookupResult(False, message=f"Phản hồi không hợp lệ (HTTP {resp.status_code})")
            name = (body.get("data") or {}).get("accountName") if isinstance(body.get("data"), dict) else None
            if str(body.get("code")) == "00" and name:
                return LookupResult(True, account_name=name.strip(), message=body.get("desc", ""))
            return LookupResult(False, message=f"[{body.get('code')}] {body.get('desc', 'Không tìm thấy')}")
        return LookupResult(False, message=last_error)


TRACUUBANK_URL = "https://tracuubank.com/api/lookup"


class TracuuBankLookup:
    """https://tracuubank.com – trả phí theo lượt tra cứu thành công.

    GET /api/lookup?bank_code=VCB&bank_number=... , header Authorization: Bearer <API key>
    """

    def __init__(self, api_key: str, banks, timeout: float = 20, retries: int = 2):
        if not api_key:
            raise ValueError("Thiếu TRACUUBANK_API_KEY")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
        self.code_by_bin = {b.bin: b.code for b in banks}
        self.timeout = timeout
        self.retries = retries

    def lookup(self, bin_code: str, account_number: str) -> LookupResult:
        params = {"bank_code": self.code_by_bin.get(str(bin_code), str(bin_code)), "bank_number": account_number}
        last_error = ""
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.get(TRACUUBANK_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    last_error = "Vượt giới hạn số lần gọi API (429)"
                    time.sleep(2 * (attempt + 1))
                    continue
                body = resp.json()
            except requests.RequestException as e:
                last_error = f"Lỗi kết nối: {e}"
                time.sleep(1 + attempt)
                continue
            except ValueError:
                return LookupResult(False, message=f"Phản hồi không hợp lệ (HTTP {resp.status_code})")
            data = body.get("data") if isinstance(body.get("data"), dict) else {}
            name = data.get("accountName") or data.get("account_name")
            if name and str(body.get("status", "success")).lower() in ("success", "ok", "true"):
                return LookupResult(True, account_name=str(name).strip())
            msg = body.get("message") or body.get("msg") or body.get("error") or "Không tìm thấy"
            return LookupResult(False, message=f"[HTTP {resp.status_code}] {msg}")
        return LookupResult(False, message=last_error)


def make_lookup(provider: str, banks, **keys):
    """provider: 'tracuubank' hoặc 'vietqr'."""
    if provider == "tracuubank":
        return TracuuBankLookup(keys.get("api_key", ""), banks)
    return VietQRLookup(keys.get("client_id", ""), keys.get("api_key", ""))
