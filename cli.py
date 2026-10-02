"""Chạy bằng dòng lệnh:

    python cli.py danh_sach.xlsx
    python cli.py danh_sach.xlsx --account-col "Số TK Ngân Hàng" --bank-col "Tên Ngân Hàng"

Mặc định: ghi file gốc (giữ định dạng) + thêm 1 cột "Tên TK tra cứu" ở cuối.
Thêm --report để xuất thêm báo cáo chi tiết (trạng thái, so khớp tên).
"""
import argparse
import os
import sys

from bank_checker import BankMatcher, LookupResult, TracuuBankLookup, VietQRLookup, load_banks, process, read_excel, to_excel_bytes
from bank_checker.processor import (
    ACCOUNT_HINTS,
    BANK_HINTS,
    COL_STATUS,
    guess_column,
    guess_name_columns,
    write_to_workbook,
)


def load_dotenv(path=".env"):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description="Kiểm tra tên chủ tài khoản ngân hàng từ file Excel")
    p.add_argument("input", help="File Excel đầu vào")
    p.add_argument("-o", "--output", help="File kết quả (mặc định: <tên file>_ket_qua.xlsx)")
    p.add_argument("--sheet", default=0, help="Tên hoặc số thứ tự sheet")
    p.add_argument("--account-col")
    p.add_argument("--bank-col")
    p.add_argument("--name-col", action="append",
                   help="Cột tên cần đối chiếu, có thể lặp lại (mặc định: tự đoán các cột 'Tên ...')")
    p.add_argument("--header", default="Tên TK tra cứu", help="Tiêu đề cột kết quả thêm vào cuối")
    p.add_argument("--report", action="store_true", help="Xuất thêm file báo cáo chi tiết *_bao_cao.xlsx")
    p.add_argument("--delay", type=float, default=0.5, help="Giây nghỉ giữa 2 lần gọi API")
    p.add_argument("--provider", choices=["tracuubank", "vietqr"], default=os.getenv("LOOKUP_PROVIDER", "tracuubank"),
                   help="Nguồn tra cứu (mặc định tracuubank; API lookup của VietQR đã ngừng cho gói Free)")
    p.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra dữ liệu, không gọi API")
    a = p.parse_args()

    sheet = int(a.sheet) if str(a.sheet).isdigit() else a.sheet
    df = read_excel(a.input, sheet_name=sheet).dropna(how="all")
    cols = list(df.columns)
    account_col = a.account_col or guess_column(cols, ACCOUNT_HINTS)
    bank_col = a.bank_col or guess_column(cols, BANK_HINTS)
    name_cols = a.name_col or guess_name_columns(cols, exclude=(account_col, bank_col))
    if not account_col or not bank_col:
        sys.exit(f"Không tự nhận diện được cột. Các cột hiện có: {cols}. Dùng --account-col / --bank-col.")
    print(f"Cột STK: {account_col} | Cột ngân hàng: {bank_col} | Cột tên đối chiếu: {', '.join(name_cols) or '-'}")

    banks = load_banks()
    if a.dry_run:
        lookup_fn = lambda b, n: LookupResult(False, message="Dữ liệu hợp lệ (chưa gọi API)")  # noqa: E731
    else:
        try:
            if a.provider == "tracuubank":
                lookup_fn = TracuuBankLookup(os.getenv("TRACUUBANK_API_KEY", ""), banks).lookup
            else:
                lookup_fn = VietQRLookup(os.getenv("VIETQR_CLIENT_ID", ""), os.getenv("VIETQR_API_KEY", "")).lookup
        except ValueError as e:
            sys.exit(f"{e}. Tạo file .env theo mẫu .env.example hoặc dùng --dry-run.")

    def progress(i, n):
        print(f"\r{i}/{n}", end="", flush=True)

    result = process(df, account_col, bank_col, lookup_fn, BankMatcher(banks), name_col=name_cols,
                     delay=0 if a.dry_run else a.delay, progress=progress)
    if result.attrs.get("fatal_error"):
        print(f"\n⚠️  Đã dừng tra cứu: {result.attrs['fatal_error']}")
    base = a.input.rsplit(".", 1)[0]
    out = a.output or base + "_ket_qua.xlsx"
    with open(out, "wb") as f:
        f.write(write_to_workbook(a.input, result, header=a.header, sheet_name=sheet))
    print(f"\nThành công {(result[COL_STATUS] == 'OK').sum()}/{len(result)}. Đã lưu: {out}")
    if a.report:
        with open(base + "_bao_cao.xlsx", "wb") as f:
            f.write(to_excel_bytes(result))
        print(f"Báo cáo chi tiết: {base}_bao_cao.xlsx")
    fails = result.loc[result[COL_STATUS] != "OK", COL_STATUS].value_counts()
    if len(fails):
        print("Các dòng chưa tra được:")
        for reason, n in fails.items():
            print(f"  {n:5}  {reason}")


if __name__ == "__main__":
    main()
