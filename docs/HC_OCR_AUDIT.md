# Kiểm tra OCR trong Soát tài liệu HC — 07/11/2026

## Cập nhật sau điều chỉnh

Các nhận xét phía dưới ghi trạng thái trước sửa. Đã sửa chuẩn hóa Quantity_L, chặn chỉ số chưa hỗ trợ, giữ chuỗi số thập phân gốc và phân biệt lỗi mô hình với tài liệu không có số liệu. Đã chạy trọn luồng với OCR/LLM thật và CSDL kiểm thử cách ly, không ghi SQL Server khách hàng. Xem [kết quả thử sau sửa](validation/hc-ocr-fixed-e2e.json) và [hướng dẫn hiện tại](CHEMICAL_REPORT_FORMATS.md). Ảnh nhúng trong Word và xử lý tài liệu dài vẫn nằm ngoài đợt điều chỉnh này.

## Kết luận

Luồng OCR đã hoạt động thực tế trong chức năng đọc trước đối soát. Đã kiểm tra bằng model thật `Qwen/Qwen3.6-35B-A3B-FP8`, gọi đúng router `POST /api/chemicals/document-reviews/preview` qua ASGI, dùng ảnh/PDF mẫu tự tạo. Chỉ giả lập danh tính có quyền Ai.DocumentReview; không giả lập OCR hoặc LLM trích xuất. Không kiểm tra trên trình duyệt hoặc qua reverse proxy. Không ghi vào SQL Server; session ghi được thay bằng hàm báo lỗi nếu bị gọi.

72 kiểm thử tự động liên quan đã qua. Kết quả này không chứng minh độ chính xác trên mọi báo cáo hoặc bộ dữ liệu khách hàng.

## Kết quả mô hình thật

| Trường hợp | Kết quả |
|---|---|
| Ảnh bảng hai dòng hóa chất | HTTP 200; đúng phòng, mã, chỉ số, giá trị và đơn vị |
| Ảnh đoạn văn | HTTP 200; lấy được lượng hóa chất, nhiệt độ, độ ẩm và thời điểm. Có lỗi mã chỉ số Quantity_L cho 1,25 L |
| Ảnh có bảng kèm ghi chú | HTTP 200; lấy được cả hai dòng bảng và nhiệt độ/độ ẩm trong ghi chú |
| PDF scan đoạn văn | HTTP 200; lấy được số liệu, nhưng lặp lại lỗi Quantity_L |
| PDF scan có trang trắng cuối | HTTP 200 trong mẫu thử này; vẫn lấy được nội dung trang đầu |
| Ảnh chỉ có văn bản, không chứa số liệu | HTTP 422; không tạo dòng số liệu giả |
| PDF gồm một trang chữ và một trang scan | HTTP 200; đọc được cả hai trang. Lỗi Quantity_L vẫn có ở số liệu đơn vị L |
| DOCX chỉ chứa ảnh báo cáo | HTTP 422; không OCR ảnh nhúng trong Word |

Dữ liệu chi tiết: [validation/hc-ocr-audit.json](validation/hc-ocr-audit.json). Ảnh và PDF mẫu nằm tại `/tmp/hc-ocr-audit` trong môi trường kiểm tra.

## Các điểm cần sửa hoặc làm rõ

### 1. Mã chỉ số từ AI chưa được kiểm tra/chuẩn hóa đầy đủ

Mẫu gốc ghi 1,25 L. OCR và LLM giữ đúng giá trị 1.25, đơn vị L, nhưng LLM tự sinh `metric=Quantity_L`. `extract_chemical_document_text` chuyển thẳng metric vào kết quả. `normalize_metric` chưa có alias này và `_fetch_point_measurement` chỉ xử lý lượng hóa chất khi metric là Quantity_mL. Vì vậy có thể báo không tìm được bản ghi dù SQL có dữ liệu; đây là lỗi chuẩn hóa sau OCR, không phải đọc sai chữ.

Ưu tiên ánh xạ chỉ số thể tích về Quantity_mL, giữ nguyên value/unit để bộ đối soát quy đổi L sang mL; kiểm tra chỉ số nằm trong tập backend hỗ trợ. Prompt còn nêu Quantity_g/Weight_g trong khi bộ đối soát hiện chưa có cột tương ứng; cần báo chưa hỗ trợ thay vì báo thiếu bản ghi.

### 2. DOCX có ảnh nhúng chưa đi qua OCR

`read_report_file` trả ngay `docx_blocks_markdown` cho DOCX; không duyệt ảnh nhúng. Word có bảng/văn bản vẫn đọc được, nhưng Word chỉ chứa bản scan không được xử lý như ảnh/PDF scan.

### 3. Thông báo lỗi trích xuất chưa phân biệt nguyên nhân

Lỗi gọi LLM được đổi thành items rỗng; `_prepare_report_upload` hiển thị chung thông báo không trích xuất được số liệu. Hiện chưa phân biệt được tài liệu thật sự không có số liệu với model lỗi/quá hạn. Nên tách hai trường hợp để người dùng biết có cần thử lại hay không.

### 4. Các giới hạn xử lý tài liệu

- Tab này dùng chế độ tự phân loại PDF, chưa có lựa chọn ép OCR lại khi lớp text có sẵn sai.
- Mọi trang được ghép thành một yêu cầu LLM trích xuất. Chưa chia tài liệu dài thành từng đợt để bảo đảm không vượt context hoặc thiếu số dòng.
- Preview là một phản hồi hoàn chỉnh, không có SSE tiến trình từng trang như tab OCR riêng.
- Trang scan đọc rỗng/đọc lỗi được chặn để không đối soát thiếu trang; tùy kết quả model, trang trắng có thể bị coi là lỗi. Mẫu trang trắng trong lần thử hiện tại không gây lỗi.
- Prompt trích xuất mặc định năm 2026 nếu tài liệu thiếu năm. Đây là giả định cần bỏ hoặc yêu cầu người dùng xác nhận.

## Phạm vi chưa xác minh

Chưa thử báo cáo thực tế của khách hàng, ảnh mờ/chữ viết tay, tài liệu dài gần giới hạn và toàn bộ bước ghi/đối chiếu với SQL Server thật. Không thay đổi mã ứng dụng trong đợt kiểm tra này.
