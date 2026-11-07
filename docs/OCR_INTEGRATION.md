# Tích hợp TPV-OCR vào tab OCR tài liệu

Bộ nhận dạng được đưa trực tiếp từ `TPV-OCR` vào backend Chatbot. Không chạy thêm ứng dụng OCR trên cổng 8088, không nhúng hoặc sao chép giao diện độc lập.

## Thành phần

- `backend/app/rag/ocr.py`: phân loại trang, render ảnh, gọi VLM; thêm prompt Hóa học và phóng ảnh nhỏ theo cấu hình.
- `backend/app/rag/chemistry.py`: đọc bổ sung điều kiện phản ứng, dấu trên ký hiệu và phục hồi dòng ngăn bảng; giữ bản OCR gốc nếu đối chiếu không khớp.
- `backend/app/documents/ocr_tai_lieu.py`: chọn chế độ văn bản hoặc hóa học. Giữ hàm `doc_pdf_de_soat` để workflow soát văn bản tiếp tục hoạt động.
- `backend/app/api/ocr.py`: giữ API, file ID và quyền `Ai.Ocr`; bổ sung giới hạn đầu vào và heartbeat cho stream.
- `frontend/index.html`, `frontend/js/app.js`, `frontend/styles.css`: tiếp tục dùng giao diện Chatbot, chia phần tải file, tùy chọn, thao tác và kết quả.

## Cấu hình và chạy

Trong `backend/.env`, cấu hình riêng OCR theo dịch vụ TPV-OCR:

```dotenv
OCR_ENABLED=true
OCR_BASE_URL=http://127.0.0.1:15000/v1
OCR_MODEL=Qwen/Qwen3.6-35B-A3B-FP8
OCR_MAX_CONCURRENCY=2
OCR_MAX_UPLOAD_MB=30
OCR_MAX_PAGES=100
OCR_UPSCALE_SMALL_IMAGES=false
```

Giữ `OCR_API_KEY` theo máy chủ triển khai. Nếu Chatbot chạy trong container, đổi địa chỉ loopback sang địa chỉ máy chủ mô hình mà container truy cập được. Các cấu hình LLM chat giữ nguyên.

Checkout hiện tại có `backend/data` là file chứa đường dẫn cũ, nên cấu hình cục bộ dùng `UPLOAD_DIR=./.runtime/uploads` để nhận file trong chính dự án. Thư mục `.runtime` được bỏ qua bởi Git.

Khởi động lại backend Chatbot theo cách triển khai hiện tại; tải lại giao diện và chọn tab OCR tài liệu. Không tự khởi chạy hoặc tải trọng số mô hình. Status phản ánh cấu hình, không xác nhận kết nối mô hình.

## Hợp đồng API

- `POST /api/ocr/extract`: multipart `file`, `che_do=auto|tat_ca`, `loai_tai_lieu=general|chemistry`.
- `POST /api/ocr/extract/stream`: JSON `{ "file_id": "...", "che_do": "auto", "loai_tai_lieu": "chemistry" }`, sau khi upload qua `/api/agent/upload`.
- Bỏ `loai_tai_lieu` thì mặc định `general`, tương thích client cũ.
- SSE phát `start`, `trang`, `done` hoặc `error`; comment heartbeat sau 10 giây chờ. Kết quả có `pipeline_version=chemistry-5`.

Chế độ Hóa học dùng ảnh lớn hơn và đọc bổ sung vùng phản ứng/ký hiệu nên có thể chậm hơn. Chế độ tự động vẫn dùng lớp chữ PDF có sẵn; chọn OCR tất cả khi lớp chữ đó sai. Công thức LaTeX được giữ dạng mã; chưa dựng LaTeX trực quan. TXT giữ ký hiệu Markdown, không tái tạo bố cục Word/PDF. TIFF nhiều khung vẫn chỉ đọc khung đầu như TPV-OCR.

OCR không tự động nạp vào Kho tri thức. Sau khi xử lý hoàn tất, bấm **Nạp kho tri thức** cạnh **Tải .txt** để nạp trực tiếp Markdown đã nhận dạng qua `/api/documents/ingest-text`, giữ tên file nguồn và quyền ghi kho hiện có. Nút báo tiến trình, mã tài liệu/số đoạn khi thành công; cho phép thử lại khi lỗi và khóa sau khi nạp thành công trong lượt đó. Khi dừng hoặc lỗi kết nối, giao diện giữ các trang đã nhận; yêu cầu mô hình đang chạy có thể cần hoàn tất trước khi thread nền dừng.

## Kiểm tra

Chạy từ `backend`:

```bash
DEBUG=false .venv/bin/python -m pytest tests/test_ocr_tai_lieu.py tests/test_ocr_chemistry_equations.py tests/test_soat_pdf_scan.py tests/test_converter.py -q
node --check ../frontend/js/app.js
```

Các kiểm thử thay model bằng bản giả; không chứng minh chất lượng OCR trên máy chủ thật.

## Kết quả xác minh tích hợp

- 73 kiểm thử liên quan đã qua (OCR API, công thức hóa học, soát PDF scan và converter); JavaScript qua `node --check`.
- Đã chạy bộ xử lý tích hợp với ảnh `TPV-OCR/de-hoa.png`, chế độ `chemistry`, qua model thật `Qwen/Qwen3.6-35B-A3B-FP8`: 1 trang, 2.337 ký tự, khoảng 5 giây. Đây là kiểm tra khả năng kết nối và có đầu ra, chưa phải đánh giá độ chính xác từng ký tự.
- Chưa kiểm tra trực quan giao diện bằng trình duyệt trong môi trường chỉnh sửa này.

## Giữ chữ in đậm sau OCR

Mặc định `OCR_PRESERVE_BOLD=true`. Prompt nhận dạng chữ ban đầu giữ nguyên để tránh thay đổi hành vi đọc. Sau xử lý nội dung, `app/documents/ocr_formatting.py` gọi thêm một lượt chỉ chọn các cụm in đậm nhìn thấy trên ảnh. Code chỉ chèn `**` quanh chuỗi khớp nguyên văn và xuất hiện duy nhất; bỏ cụm không khớp, trùng nhiều vị trí, chồng lấn hoặc có dấu Markdown không phù hợp. Không cho model viết lại nội dung. Lỗi/timeout/JSON sai thì giữ nguyên bản OCR. Bước này áp dụng cho trang được OCR ở cả hai chế độ Văn bản và Hóa học; trang đọc từ lớp text PDF tiếp tục dùng định dạng có sẵn của bộ trích xuất.

Văn bản có cấu trúc hiển thị in đậm, Markdown thô và các file tải về giữ dấu `**`. Nút nạp kho gửi chính nội dung đó. Định dạng được suy ra từ ảnh nên có thể bỏ sót hoặc nhận diện sai nét đậm; việc thêm định dạng không sửa chữ/số/công thức đã có. Các cụm lặp nhiều chỗ được bỏ qua để tránh tô đậm nhầm vị trí.

Thêm tối đa một lượt gọi mô hình mỗi trang OCR, giới hạn thời gian gọi 30 giây và không thử lại. Tắt bằng `OCR_PRESERVE_BOLD=false` nếu ưu tiên tốc độ. Khởi động lại backend và OCR lại tài liệu để có định dạng mới; kết quả OCR cũ không tự thay đổi.

Xác minh: 84 kiểm thử đã qua, gồm các bất biến bảo toàn ký tự và xử lý lỗi định dạng. Trên ảnh mẫu `TPV-OCR/de-hoa.png`, mô hình thật thêm 10 cụm đậm vào 2.337 ký tự; kiểm tra tự động xác nhận nội dung sau khi bỏ dấu `**` trùng bản trước bước định dạng. Tổng thời gian lượt thử khoảng 5,9 giây; không phải cam kết tốc độ hoặc độ chính xác trên mọi tài liệu.
