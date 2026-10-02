# CheckBankName – Kiểm tra tên chủ tài khoản ngân hàng

Ứng dụng đọc file Excel (số tài khoản + tên ngân hàng), tự nhận diện ngân hàng,
tra cứu **tên chủ tài khoản** qua API VietQR (Napas 247) và xuất file kết quả.

## Nguồn dữ liệu

| Nguồn | Dùng để | Ghi chú |
|---|---|---|
| `GET https://api.vietqr.io/v2/banks` | Danh sách ~65 ngân hàng + mã BIN | Miễn phí, không cần key. Có bản lưu sẵn ở `data/banks.json` khi mất mạng |
| `GET https://tracuubank.com/api/lookup` (**mặc định**) | Tra cứu tên theo `bank_code` + `bank_number` | Header `Authorization: Bearer <key>`. Đăng ký tại [tracuubank.com/register](https://tracuubank.com/register), **100đ / lượt** tra thành công |
| `POST https://api.vietqr.io/v2/lookup` | Tra cứu tên theo `bin` + `accountNumber` | ⚠️ **Đã ngừng cho gói Free từ 20/08/2024** (lỗi `[47]`), VietQR chuyển sang [bankHub Pay Out](https://bankhub.dev/product/pay-out) cho doanh nghiệp |

## Cài đặt

```bash
pip install -r requirements.txt
cp .env.example .env   # điền TRACUUBANK_API_KEY (hoặc chọn LOOKUP_PROVIDER=vietqr + key VietQR)
```

## Cách 1 – Giao diện web

```bash
streamlit run app.py
```

1. Chọn nguồn tra cứu và nhập API Key ở thanh bên trái (hoặc để trong `.env` / `.streamlit/secrets.toml`).
2. Tải file Excel lên → chọn cột *Số tài khoản*, *Ngân hàng*, và (tuỳ chọn) cột *Họ tên* để đối chiếu.
3. Bấm **Bắt đầu kiểm tra** → tải file `*_ket_qua.xlsx`.

Tab **Tra cứu 1 tài khoản** để kiểm tra nhanh từng số.

## Cách 2 – Dòng lệnh

```bash
python cli.py data/mau_danh_sach.xlsx              # tự đoán cột
python cli.py Kiem_tra_TNKH.xlsx --report       # file gốc + cột K, kèm báo cáo chi tiết
python cli.py ds.xlsx --account-col "Số TK Ngân Hàng" --bank-col "Tên Ngân Hàng" --name-col "Tên KH"
python cli.py ds.xlsx --dry-run                    # chỉ kiểm tra dữ liệu, không gọi API
```

## File kết quả

App xuất 2 file:

### 1. `*_ket_qua.xlsx` – file gốc + 1 cột cuối "Tên TK tra cứu"

Giữ nguyên định dạng file import của bạn, chỉ thêm **1 cột ở cuối** (vd file mẫu A–J → cột **K**):

- Tra được tên → ghi tên chủ tài khoản.
  Nếu tên **không khớp** với các cột *Tên KH / Tên Đơn Vị / Tên Liên Hệ* → ô tô **vàng**, rê chuột xem chú thích.
- Không tra được → ô để trống, tô **đỏ**, lý do nằm trong chú thích (comment) của ô.

Tên ngân hàng dạng `Ngân Hàng TMCP Á Châu_CN Khánh Hòa_PGD Cam Ranh`, `... - Chi nhánh Phú Yên`
được tự cắt phần chi nhánh/PGD trước khi nhận diện. Dòng **Kho Bạc Nhà Nước** được báo
"không hỗ trợ" vì Kho bạc không thuộc hệ thống Napas 247.

### 2. `*_bao_cao.xlsx` – báo cáo chi tiết

Giữ nguyên các cột gốc và thêm:

- **NH nhận diện** – ngân hàng app hiểu được (vd `Vietcombank (VCB)`)
- **Tên tra cứu** – tên chủ tài khoản trả về từ API
- **Trạng thái** – `OK` (tô xanh) hoặc lý do lỗi (tô đỏ)
- **So khớp tên** – `Khớp` / `Gần khớp (x%)` / `KHÔNG khớp (x%)` (so sánh không dấu)

## Lưu ý

- Cột số tài khoản trong Excel nên để định dạng **Text** để không mất số 0 đầu. STK dài hơn 15 chữ số
  từng bị lưu dạng số sẽ bị Excel làm tròn (vd `37140111367700000`) – nên kiểm tra lại các dòng này.
- Tên ngân hàng có thể ghi tự do: `VCB`, `Vietcombank`, `NH TMCP Ngoại thương`, `970436`,
  `Vietinbank - CN Nha Trang`… Dòng không nhận diện được sẽ được báo trên giao diện.
- Một số ngân hàng (Timo, Citibank, KEB Hana, …) VietQR chưa hỗ trợ tra cứu.
- API có giới hạn số lượt theo gói; app có cache trùng lặp, nghỉ giữa các lượt gọi và tự thử lại khi gặp lỗi 429.
- Dữ liệu tên chủ tài khoản là thông tin cá nhân – chỉ dùng cho mục đích đối soát hợp pháp.

## Test

```bash
pip install pytest && python -m pytest -q
```
