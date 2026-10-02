"""Giao diện web: streamlit run app.py"""
import io
import os

import pandas as pd
import streamlit as st

from bank_checker import BankMatcher, LookupResult, VietQRLookup, load_banks, process, read_excel, to_excel_bytes
from bank_checker.banks import unsupported_reason
from bank_checker.processor import (
    ACCOUNT_HINTS,
    BANK_HINTS,
    COL_STATUS,
    clean_account,
    guess_column,
    guess_name_columns,
    write_to_workbook,
)

st.set_page_config(page_title="Kiểm tra tên tài khoản ngân hàng", page_icon="🏦", layout="wide")
st.title("🏦 Kiểm tra tên chủ tài khoản ngân hàng")
st.caption("Tải file Excel gồm số tài khoản + tên ngân hàng → tra cứu tên chủ tài khoản qua API VietQR.")


@st.cache_data(ttl=24 * 3600)
def get_banks():
    return load_banks()


def secret(name: str) -> str:
    try:
        return st.secrets.get(name, "") or os.getenv(name, "")
    except Exception:
        return os.getenv(name, "")


banks = get_banks()
matcher = BankMatcher(banks)

with st.sidebar:
    st.header("Cấu hình API")
    client_id = st.text_input("Client ID", value=secret("VIETQR_CLIENT_ID"))
    api_key = st.text_input("API Key", value=secret("VIETQR_API_KEY"), type="password")
    st.markdown("Đăng ký lấy key tại [my.vietqr.io](https://my.vietqr.io) / [casso.vn](https://casso.vn).")
    dry_run = st.checkbox("Chỉ kiểm tra dữ liệu (không gọi API)", value=not (client_id and api_key))
    delay = st.slider("Thời gian nghỉ giữa 2 lần gọi (giây)", 0.0, 3.0, 0.5, 0.1)
    with st.expander(f"Danh sách {len(banks)} ngân hàng"):
        st.dataframe(
            pd.DataFrame([{"Mã": b.code, "BIN": b.bin, "Tên": b.short_name, "Tra cứu": b.lookup_supported} for b in banks]),
            hide_index=True,
        )

tab_file, tab_single = st.tabs(["📄 Kiểm tra theo file Excel", "🔍 Tra cứu 1 tài khoản"])

with tab_single:
    c1, c2 = st.columns(2)
    labels = [b.label for b in banks]
    bank_label = c1.selectbox("Ngân hàng", labels)
    acc = c2.text_input("Số tài khoản")
    if st.button("Tra cứu", type="primary"):
        bank = banks[labels.index(bank_label)]
        account = clean_account(acc)
        if not account.isdigit() or not 6 <= len(account) <= 19:
            st.error("Số tài khoản chỉ gồm 6-19 chữ số.")
        elif not (client_id and api_key):
            st.error("Vui lòng nhập Client ID và API Key ở thanh bên trái.")
        else:
            res = VietQRLookup(client_id, api_key).lookup(bank.bin, account)
            if res.ok:
                st.success(f"**{res.account_name}**")
            else:
                st.error(res.message)

with tab_file:
    up = st.file_uploader("Chọn file Excel (.xlsx, .xls) hoặc CSV", type=["xlsx", "xls", "csv"])
    if up:
        if up.name.lower().endswith(".csv"):
            df = pd.read_csv(up, dtype=str)
        else:
            sheets = pd.ExcelFile(up).sheet_names
            sheet = st.selectbox("Sheet", sheets) if len(sheets) > 1 else sheets[0]
            df = read_excel(up, sheet_name=sheet)
        df = df.dropna(how="all")
        st.write(f"Đọc được **{len(df)}** dòng.")
        st.dataframe(df.head(20), hide_index=True)

        cols = list(df.columns)

        def idx(col):
            return cols.index(col) if col in cols else 0

        c1, c2 = st.columns(2)
        account_col = c1.selectbox("Cột số tài khoản", cols, index=idx(guess_column(cols, ACCOUNT_HINTS)))
        bank_col = c2.selectbox("Cột tên ngân hàng", cols, index=idx(guess_column(cols, BANK_HINTS)))
        name_cols = st.multiselect(
            "Cột tên dùng để đối chiếu (tuỳ chọn – tên tra cứu khớp với cột nào cũng được)",
            [c for c in cols if c not in (account_col, bank_col)],
            default=guess_name_columns(cols, exclude=(account_col, bank_col)),
        )

        unknown = sorted({
            str(v) for v in df[bank_col].dropna()
            if matcher.match(v) is None and not unsupported_reason(v)
        })
        if unknown:
            st.warning("Không nhận diện được các ngân hàng sau, hãy sửa trong file: " + ", ".join(unknown))

        if st.button("▶️ Bắt đầu kiểm tra", type="primary"):
            if dry_run:
                def lookup_fn(bin_code, account):
                    return LookupResult(False, message="Dữ liệu hợp lệ (chưa gọi API)")
                wait = 0
            else:
                if not (client_id and api_key):
                    st.error("Vui lòng nhập Client ID và API Key.")
                    st.stop()
                lookup_fn = VietQRLookup(client_id, api_key).lookup
                wait = delay
            bar = st.progress(0.0, text="Đang xử lý...")
            result = process(
                df, account_col, bank_col, lookup_fn, matcher, name_col=name_cols, delay=wait,
                progress=lambda i, n: bar.progress(i / n, text=f"Đang xử lý {i}/{n}"),
            )
            bar.empty()
            original = None
            if not up.name.lower().endswith((".csv", ".xls")):
                original = write_to_workbook(io.BytesIO(up.getvalue()), result, sheet_name=sheet)
            # Lưu lại để bấm tải file không phải tra cứu lại
            st.session_state["result"] = (up.name, result, original)

        saved = st.session_state.get("result")
        if saved and saved[0] == up.name:
            _, result, original = saved
            ok = (result[COL_STATUS] == "OK").sum()
            st.success(f"Hoàn tất: {ok}/{len(result)} tài khoản tra cứu thành công.")
            st.dataframe(result, hide_index=True)
            base = up.name.rsplit(".", 1)[0]
            xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            d1, d2 = st.columns(2)
            if original is not None:
                d1.download_button("⬇️ File gốc + cột tên tra cứu", data=original,
                                   file_name=f"{base}_ket_qua.xlsx", mime=xlsx, type="primary")
            d2.download_button("⬇️ Báo cáo chi tiết", data=to_excel_bytes(result),
                               file_name=f"{base}_bao_cao.xlsx", mime=xlsx)
