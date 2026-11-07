# Định dạng báo cáo Soát tài liệu HC

Tab hỗ trợ TXT, XLSX, CSV, JSON và bổ sung PDF, DOCX, JPG, JPEG, PNG, MD.

- XLSX/CSV: đọc bảng số liệu theo cấu trúc cũ, không qua LLM.
- JSON: đọc mảng số liệu hoặc object có `items`, dùng `report_date` nếu form không truyền ngày.
- TXT/MD: đọc UTF-8 rồi dùng LLM bóc tách số liệu; TXT trên giao diện vẫn cho xem/sửa nội dung trước khi soát.
- DOCX: đọc đoạn văn và bảng từ bộ phân tích Word, rồi bóc tách số liệu.
- PDF: phân loại từng trang, đọc trực tiếp lớp chữ và OCR trang scan. Ảnh JPG/JPEG/PNG được OCR. Dùng cùng dịch vụ mô hình OCR hiện tại; không chạy lại bước nhận diện in đậm vì đối soát chỉ cần nội dung.

Luồng: file → nội dung hoặc dòng dữ liệu → bóc tách số liệu nếu cần → đối soát SQL Server. Không nạp file vào Kho tri thức. Chỉ mở phiên ghi đối soát sau khi đọc được số liệu. Tệp gốc vẫn dùng để tính checksum của báo cáo.

Giới hạn dùng `OCR_MAX_UPLOAD_MB` (mặc định 30 MB) và `OCR_MAX_PAGES` cho PDF (mặc định 100 trang). PDF scan/ảnh yêu cầu OCR được bật. File hỏng, không có số liệu hoặc trang OCR chưa đọc được sẽ báo lỗi, tránh đối soát một báo cáo rỗng/thiếu trang.

Mã đọc file nằm tại `backend/app/services/chemical_report_files.py`; API nhận multipart vẫn là `POST /api/chemicals/document-reviews`, giữ quyền `Ai.DocumentReview` và các trường ngày/kỳ báo cáo hiện có.

Kiểm thử từ backend:

```bash
DEBUG=false QDRANT_COLLECTION=tpv_documents .venv/bin/python -m pytest tests/test_chemical_report_files.py tests/test_chemical_chatbot_and_review.py -q
```

## Luồng kiểm tra đơn giản trước khi đối soát

1. Chọn file hoặc dán văn bản/JSON rồi bấm **Đọc số liệu**.
2. Kiểm tra và sửa trực tiếp các cột Phòng, Mã hóa chất, Chỉ số, Giá trị, Đơn vị, Thời điểm đo trong bảng.
3. Bấm **Đối soát SQL Server** để gửi các dòng đã sửa. Kết quả không tự chạy ở bước đọc số liệu; đổi nguồn đầu vào sẽ xóa bản trích xuất cũ, đổi số liệu/ngày báo cáo sẽ yêu cầu đối soát lại.

`POST /api/chemicals/document-reviews/preview` nhận multipart file, dùng chung bộ đọc định dạng và trả items/report_date/file_name, không tạo phiên đối soát. Giao diện xác nhận bằng JSON tới `POST /api/chemicals/document-reviews`; không OCR/bóc tách lại sau khi sửa. Các API đối soát trực tiếp cũ vẫn được giữ tương thích. Giao diện đã sửa đường dẫn upload từ `/document-reviews/upload` sang `/document-reviews` đúng endpoint hiện có.

Kết quả gồm Tổng dòng kiểm tra, Khớp (gồm khớp bản ghi chốt gần nhất), Sai lệch, Cần xác minh và Thiếu dữ liệu đối chiếu. Bộ đếm và bộ lọc cùng tính từ từng dòng kết quả, không phụ thuộc nhãn ngày cố định hoặc tên trạng thái sai. Mỗi dòng hiển thị số báo cáo, SQL Server, thời điểm thực tế theo UTC+7, lý do và chênh lệch/sai số khi có. Các giá trị quy đổi phải mang đơn vị chuẩn tương ứng; thiếu dữ liệu giữ null, không thay bằng 0.

Kiểm thử xác minh cập nhật: 43 ca backend và 3 ca luồng JavaScript. Chạy JavaScript bằng `node frontend/tests/chemical-review.test.cjs` từ gốc dự án. Chưa kiểm tra trực quan giao diện bằng trình duyệt trong phiên chỉnh sửa.

Giao diện Soát tài liệu HC dùng bố cục `view-split`, cột nhập `panel/panel-inner`, vùng `result` và các thành phần `field`, `dropzone`, `primary-btn`, `card`, `doc-table`, `seg`, `pill` dùng chung với các tab khác. Màu sắc theo biến giao diện ở cả chế độ sáng và tối.

## Chuẩn hóa và kiểm tra dữ liệu sau OCR

- Chỉ số `Quantity_L` và `quantity_recorded_l` được chuẩn hóa thành `Quantity_mL`. Giữ nguyên lượng và đơn vị gốc; chỉ quy đổi L sang mL một lần trong bộ đối soát. Nếu mã chỉ số thể tích L bị thiếu unit, giữ ý nghĩa nguồn bằng unit L.
- Mã chỉ số ngoài tập backend hỗ trợ bị chặn trước khi mở phiên SQL. Khối lượng g/kg hiện chưa hỗ trợ: báo rõ, không diễn giải thành thiếu dữ liệu gốc.
- AI được yêu cầu chép giá trị thành chuỗi số gốc, không tự quy đổi dấu phân cách hoặc đơn vị. Giá trị trích xuất còn được kiểm tra với tập số có trong văn bản OCR (dấu phẩy là dấu thập phân theo luồng hiện tại); số không khớp bị chặn. Kiểm tra này không chứng minh số được gán đúng phòng/hóa chất, nên vẫn cần xem/sửa bảng trước khi xác nhận. Dấu phân cách hàng nghìn phức tạp cần người dùng kiểm tra.
- Lỗi đọc file, OCR không đọc đủ trang, không tìm thấy số liệu, model quá hạn, lỗi kết nối và model trả sai định dạng có thông báo riêng. OCR trong luồng này truyền lỗi thay vì bỏ qua lỗi trang; mặc định của các luồng OCR khác được giữ.
- Trích xuất gọi model với thinking=False; tài liệu thiếu năm không còn tự gán năm 2026.

Xác minh cập nhật: 122 kiểm thử backend đạt, 1 kiểm thử live được bỏ qua ở lượt chạy mặc định; đã chạy riêng kiểm thử live với mô hình thật và CSDL SQLite cách ly dùng cùng ORM/query đối soát. Thử trọn luồng ảnh → OCR → trích xuất → sửa số liệu → đối soát xác nhận 1,545 L = 1545 mL, sửa 1,795 L thành 1,8 L cho chênh 5 mL với số gốc 1795 mL; số 0 vẫn là số 0; số liệu ngoài phạm vi có db_value=null. Không ghi vào SQL Server khách hàng. Ba kiểm thử luồng giao diện vẫn đạt.

Chạy kiểm thử với model thật (yêu cầu dịch vụ OCR/LLM đang chạy):

```bash
DEBUG=false QDRANT_COLLECTION=tpv_documents RUN_HC_OCR_LIVE=1 .venv/bin/python -m pytest tests/test_chemical_chatbot_and_review.py -k test_ocr_preview_edited_rows_and_database_results -q
```

## Sửa sai múi giờ sau trích xuất

AI được yêu cầu giữ nguyên giờ và offset từ tài liệu. `chemical_report_times.py` đối chiếu thời điểm với văn bản OCR: bảng được ghép theo phòng, hóa chất, chỉ số, giá trị và đơn vị; khi khóa lặp lại thì chỉ khôi phục theo thứ tự nếu toàn bộ chuỗi dòng khớp. Không ghép nhầm chỉ dựa trên số dòng. Ngày lập báo cáo được lấy từ dòng tiêu đề khi có một giá trị rõ ràng. Code đọc ISO 8601 hoặc ngày giờ Việt Nam; phần đối soát dùng `parse_timestamp_utc` để chuyển UTC.

Văn bản không phải bảng: thời điểm do AI trả phải trùng một thời điểm có trong nội dung đo; trường hợp bị đổi sai giờ hoặc không có căn cứ bị chặn. Dòng không ghi giờ đo riêng vẫn giữ null, không tự lấy ngày báo cáo làm giờ đo. Khi các dòng trùng không thể ghép chắc chắn, báo cần kiểm tra thay vì chọn thời điểm tùy ý. Các kiểm tra không thể sửa nội dung ngày giờ nếu chính OCR đã đọc sai chữ; người dùng vẫn cần kiểm tra bảng trước khi xác nhận.

Đã tái hiện lỗi `2026-11-07T23:00:00Z` ở hai dòng của mẫu và kiểm tra khôi phục thành `2026-11-08T08:00:00+07:00` (UTC là `2026-11-08T01:00:00Z`). Đã thử lại PNG/PDF của bộ mẫu bằng mô hình thật, kết quả trên CSDL cách ly: 3 khớp, 4 sai lệch, 1 cần xác minh và 1 thiếu dữ liệu. Không cần nạp lại dữ liệu gốc; khởi động lại backend rồi bấm Đọc số liệu lại cho file ảnh/PDF để thay bản trích xuất cũ.
