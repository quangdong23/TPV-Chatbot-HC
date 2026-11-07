# Bộ kiểm thử Soát tài liệu HC

Bộ dữ liệu giả lập, có đáp án biết trước. Chưa nạp vào SQL Server đang vận hành.

## Có những file nào?

- `01_du_lieu_goc/du_lieu_goc.xlsx` hoặc `.csv`: nạp làm nguồn SQL, gồm 8 dòng (2 phòng × 2 hóa chất × 2 thời điểm). Chỉ chọn **một** định dạng để nạp.
- `02_bao_cao_kiem_thu/bao_cao_dung.xlsx`: báo cáo đối chứng, cả 9 dòng phải khớp. Có bản CSV và JSON tương đương.
- `02_bao_cao_kiem_thu/bao_cao_co_sai_so.xlsx`: báo cáo có lỗi cố ý, gồm 9 dòng. Có CSV, JSON, Word, PNG và PDF scan với cùng nội dung.
- `03_dap_an/ket_qua_mong_doi.xlsx`: đáp án từng dòng, có bản CSV/JSON.
- `03_dap_an/ket_qua_da_kiem_chung.json`: kết quả thực tế đã so với đáp án bằng bộ đối soát hiện tại trên CSDL cách ly.

## Cách test

1. Dùng CSDL/tenant kiểm thử riêng để không trộn dữ liệu vận hành. Nạp **du_lieu_goc.xlsx** hoặc **du_lieu_goc.csv** qua `POST /api/chemicals/imports`, trường `file`, `strict=true`, với tài khoản được cấp quyền nhập. Nạp gốc và đối soát bằng cùng tài khoản/tenant. Hiện giao diện chưa có nút nạp dữ liệu gốc.
2. Xác nhận lô nhập có **8 dòng được thêm, 0 dòng bị từ chối**. Nếu đã có dữ liệu trùng phòng/mã/thời điểm, cần kiểm tra lại nguồn trước khi dùng đáp án này. Đây không phải lệnh thay thế/xóa dữ liệu cũ.
3. Vào tab **Soát tài liệu HC**, tải **bao_cao_dung.xlsx** → **Đọc số liệu** → kiểm tra bảng → **Đối soát SQL Server**. Kỳ vọng **9 Khớp, các nhóm khác 0**.
4. Đổi sang **bao_cao_co_sai_so.xlsx**, làm tương tự. Kỳ vọng **Tổng 9; Khớp 3; Sai lệch 4; Cần xác minh 1; Thiếu dữ liệu đối chiếu 1**.
5. Test OCR bằng **bao_cao_co_sai_so.png** hoặc **bao_cao_co_sai_so_scan.pdf**. Bảng sau Đọc số liệu phải giống Excel. Để đo chất lượng OCR/trích xuất, ghi lại chỗ đọc sai trước khi sửa; sau đó có thể sửa bảng để kiểm tra riêng phần đối soát.
6. So từng dòng với đáp án phía dưới. Để ngày lập báo cáo trống cho hệ thống đọc từ file, hoặc nhập đúng **08/11/2026 09:30 (UTC+7)**. Không thay đổi thời điểm đo trong bảng khi chạy bộ chuẩn.

## Dữ liệu gốc tại 08:00 ngày 07/11/2026, UTC+7

| Phòng | Hóa chất | Lượng mL | Nhiệt độ C | Độ ẩm % | TVOC ppb |
|---|---|---:|---:|---:|---:|
| R01 | 001 | 1500 | 25 | 55 | 100 |
| R01 | 002 | 2000 | 25 | 55 | 100 |
| R02 | 003 | 750 | 24 | 60 | 90 |
| R02 | 004 | 0 | 24 | 60 | 90 |

Nguồn còn có các số đo lúc 09:00 trong Excel. Phạm vi dữ liệu nguồn chỉ từ **07/11/2026 08:00 đến 09:00 (UTC+7)**. Tất cả thời điểm trong file đều ghi offset +07:00; API lưu UTC có thể hiển thị 01:00/02:00Z, đây là cùng thời điểm.

## Đáp án báo cáo có sai số

| Dòng | Kiểm tra | Báo cáo ghi | Nguồn đúng | Kết quả |
|---|---|---|---|---|
| 1 | R01 / 001, 07/11 lúc 08:00 | 1500 mL | 1500 mL | Khớp |
| 2 | R01 / 002, 07/11 lúc 08:00 | 2 L | 2000 mL | Khớp sau quy đổi; không phải lỗi |
| 3 | R02 / 003, 07/11 lúc 08:00 | 700 mL | 750 mL | Sai lệch −50 mL |
| 4 | R02 / 004, 07/11 lúc 08:00 | 0 mL | 0 mL | Khớp; không phải thiếu dữ liệu |
| 5 | Nhiệt độ R01, 07/11 lúc 08:00 | 28 C | 25 C | Sai lệch +3 C |
| 6 | Độ ẩm R02, 07/11 lúc 08:00 | 65% | 60% | Sai lệch +5 điểm phần trăm |
| 7 | TVOC R02, 07/11 lúc 08:00 | 0 ppb | 90 ppb | Sai lệch −90 ppb; vẫn phải giữ số 0 |
| 8 | R01 / 002, ghi ngày 08/11 lúc 08:00 | 1234 mL | Không có bản ghi ngày này | Thiếu dữ liệu/ngoài phạm vi; **không được tự lấy 2000 hoặc 2100 mL để kết luận lệch số** |
| 9 | R01 / 001, ghi ngày 08/11 lúc 08:00 | 1500 mL | Số 1500 thuộc ngày 07/11 lúc 08:00 | Nghi lệch thời điểm; cần xác minh, không được coi là khớp hoàn toàn |

Chênh lệch = số báo cáo sau quy đổi − số gốc. Với dòng 9, 1500 là bản ghi ứng viên ở ngày trước, không phải chứng cứ đã có số đo ngày 08/11. Các sai lệch đã chọn đều vượt sai số mặc định của hệ thống.

## Đánh giá lỗi nằm ở đâu?

- Bảng trích xuất khác file mẫu: lỗi đọc/OCR/trích xuất. Các mã 001–004 phải giữ số 0 đầu, dòng môi trường không có mã hóa chất.
- Bảng trích xuất đúng nhưng kết quả khác đáp án: kiểm tra dữ liệu SQL đã nạp, tenant và quy tắc đối soát.
- Dòng 2 bị báo lệch, dòng 4 bị coi là thiếu dữ liệu, hoặc dòng 8 được tự gán SQL=0: không đạt.
- Báo cáo đúng phải khớp đủ 9 dòng; báo cáo sai phải giữ đủ 9 dòng và cho đúng các nhóm nêu trên.

## Kết quả đã kiểm chứng

Đã thử CSV/XLSX/JSON cho cả hai báo cáo trên CSDL SQLite cách ly dùng cùng ORM và bộ đối soát của ứng dụng; kết quả khớp đáp án. Ảnh PNG và PDF scan của báo cáo sai cũng đã được đọc bằng mô hình thật Qwen/Qwen3.6-35B-A3B-FP8 rồi đối soát trên CSDL cách ly. Chưa ghi bất kỳ dữ liệu nào vào SQL Server của bạn. Bản Word cung cấp thêm để dùng thử, không thuộc lượt kiểm chứng mô hình thật này.

Có thể chạy lại kiểm chứng cách ly từ thư mục `backend` bằng Python của dự án:

```bash
DEBUG=false .venv/bin/python ../test_data/bo_test_hc_20261107/03_dap_an/kiem_tra_cach_ly.py
```

Thêm `HC_LIVE=1` nếu muốn kiểm tra cả ảnh/PDF bằng dịch vụ OCR/LLM đang cấu hình. Script luôn tạo CSDL SQLite trong bộ nhớ và không ghi SQL Server thật.
