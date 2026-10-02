import pandas as pd
import pytest

from bank_checker import BankMatcher, LookupResult, load_banks, process
from bank_checker.processor import clean_account, compare_names


@pytest.fixture(scope="module")
def matcher():
    return BankMatcher(load_banks(online=False))


@pytest.mark.parametrize("text,code", [
    ("Vietcombank", "VCB"), ("VCB", "VCB"), ("NH TMCP Ngoại thương Việt Nam", "VCB"),
    ("Ngân hàng Vietcombank - CN Nha Trang", "VCB"), ("970436", "VCB"),
    ("Vietinbank", "ICB"), ("Agribank", "VBA"), ("BIDV", "BIDV"), ("MB Bank", "MB"),
    ("mbbank", "MB"), ("Techcombank", "TCB"), ("ACB", "ACB"), ("Sacombank", "STB"),
    ("TP Bank", "TPB"), ("LienVietPostBank", "LPB"), ("Quân đội", "MB"),
    ("Ngân hàng Á Châu", "ACB"), ("SCB", "SCB"), ("Shinhan", "SHBVN"), ("SHB", "SHB"),
    ("Techcombnk", "TCB"),
])
def test_match(matcher, text, code):
    assert matcher.match(text).code == code


def test_match_unknown(matcher):
    assert matcher.match("abc xyz") is None
    assert matcher.match("") is None


def test_clean_account():
    assert clean_account(" 0123 456.789 ") == "0123456789"
    assert clean_account(123456789.0) == "123456789"
    assert clean_account("123456789.0") == "123456789"
    assert clean_account(None) == ""


def test_compare_names():
    assert compare_names("Nguyễn Văn A", "NGUYEN VAN A") == "Khớp"
    assert compare_names("Nguyen Van An", "NGUYEN VAN AN.").startswith("Khớp")
    assert compare_names("Tran Thi B", "NGUYEN VAN A").startswith("KHÔNG")


def test_process(matcher):
    df = pd.DataFrame({
        "STK": ["0071000123456", "abc", "123456789", "", "0071000123456"],
        "Ngân hàng": ["VCB", "ACB", "Ngân hàng lạ", "BIDV", "Vietcombank"],
        "Họ tên": ["Nguyễn Văn A", "", "", "", "Tran Van B"],
    })
    calls = []

    def fake(bin_code, acc):
        calls.append((bin_code, acc))
        return LookupResult(True, account_name="NGUYEN VAN A")

    out = process(df, "STK", "Ngân hàng", fake, matcher, name_col="Họ tên", delay=0)
    assert calls == [("970436", "0071000123456")]  # có cache, chỉ gọi 1 lần
    assert list(out["Trạng thái"]) [0] == "OK"
    assert out["So khớp tên"][0] == "Khớp"
    assert "không hợp lệ" in out["Trạng thái"][1]
    assert "Không nhận diện" in out["Trạng thái"][2]
    assert out["Trạng thái"][3] == "Thiếu số tài khoản"
    assert out["So khớp tên"][4].startswith("KHÔNG")
