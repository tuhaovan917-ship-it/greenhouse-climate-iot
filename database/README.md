# Database - Greenhouse Climate IoT

## 1. Trạng thái tài liệu

- Phiên bản: `0.2-aligned`.
- Người phụ trách thiết kế schema/migration: Người 3 - Database & Dashboard.
- Người phụ trách kết nối và truy vấn runtime: Người 2 - Backend & MQTT.
- Workflow schema/migration đã được Người 2 và Người 3 thống nhất trong API contract v0.2. Các thay đổi schema thực tế vẫn cần hai bên review qua Pull Request.

Schema chi tiết được mô tả tại [`SCHEMA.md`](./SCHEMA.md).

## 2. Công nghệ đã thống nhất

| Thành phần | Lựa chọn v0.1 |
|---|---|
| ORM | SQLModel trên SQLAlchemy 2.0 |
| Database demo | SQLite, bật WAL |
| Database nâng cấp | PostgreSQL qua `DATABASE_URL` |
| Migration | Alembic |
| Timestamp | UTC do Backend sinh |

Mục tiêu là cùng một schema logic chạy được trên SQLite và PostgreSQL. Không dùng kiểu dữ liệu, câu SQL hoặc constraint đặc thù một database nếu chưa có phương án tương đương.

## 3. Phân chia trách nhiệm

### Người 3

- Thiết kế bảng, cột, quan hệ, constraint và index.
- Quản lý tài liệu schema và Alembic migration trong `database/`.
- Chuẩn bị dữ liệu mẫu và kịch bản kiểm thử database.
- Review mọi thay đổi model có ảnh hưởng tới schema hoặc Dashboard.

### Người 2

- Triển khai SQLModel table models trong Backend theo schema đã thống nhất.
- Quản lý engine, session, transaction và `DATABASE_URL`.
- Thực hiện insert/upsert/query khi nhận MQTT hoặc REST request.
- Cung cấp API/WS đúng contract cho Dashboard.

### Quy tắc phối hợp

- Backend không import và chạy migration như mã nghiệp vụ thông thường. Migration được thực thi bằng Alembic (`upgrade head`).
- Alembic metadata có thể import SQLModel table models từ Backend để tạo/review migration; hai người cùng review diff trước khi commit.
- `create_all()` chỉ dùng cho unit test, database tạm hoặc demo reset có chủ đích; không dùng thay migration cho database chính.
- Mọi thay đổi schema phải có migration đi kèm và không chỉnh sửa migration đã được dùng chung; tạo revision mới.

## 4. Cấu hình kết nối

Backend đọc cấu hình từ biến môi trường:

```env
# SQLite demo
DATABASE_URL=sqlite:///./greenhouse.db

# PostgreSQL ví dụ, không commit credential thật
# DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/greenhouse
```

Yêu cầu:

- Không hard-code credential trong source hoặc migration.
- Chỉ commit `.env.example` với giá trị demo không bí mật.
- File SQLite runtime, `-wal` và `-shm` không được commit.
- Backend phải bật foreign key enforcement cho SQLite nếu schema sử dụng foreign key.

## 5. Quy ước dữ liệu

- Tên bảng/cột trong database dùng `snake_case`.
- API/TypeScript dùng `camelCase`; Backend chịu trách nhiệm mapping.
- `device_id` v0.1 mặc định là `greenhouse-01`, nhưng schema không hard-code chỉ một thiết bị.
- Timestamp lưu theo UTC. API trả ISO8601 có hậu tố `Z`.
- Cảm biến lỗi lưu `NULL`, không lưu `NaN` và không biến thành `0`.
- `water_ok` cho phép `NULL` để biểu diễn trạng thái cảm biến nước không đáng tin cậy; khi đó failsafe phải khóa bơm.
- Các trạng thái dạng enum được lưu bằng chuỗi có tập giá trị giới hạn để giữ tính tương thích SQLite/PostgreSQL.
- Telemetry là dữ liệu append-only; state/config là dữ liệu latest theo `device_id`; command và alert có vòng đời trạng thái.

## 6. Migration workflow đã thống nhất

```text
Thay đổi yêu cầu
  -> cập nhật SCHEMA.md
  -> Người 2 cập nhật SQLModel table model
  -> Người 3 tạo/review Alembic revision
  -> chạy migration trên SQLite sạch
  -> kiểm tra upgrade với database có dữ liệu
  -> chạy test Backend
  -> tạo Pull Request
```

Tên revision cần mô tả thay đổi, ví dụ:

```text
create_initial_greenhouse_tables
add_alert_resolution_fields
add_telemetry_device_time_index
```

## 7. WAL, transaction và tính nhất quán

- SQLite demo bật WAL để giảm xung đột giữa luồng ghi MQTT và các truy vấn đọc từ Dashboard.
- Mỗi MQTT message được xử lý trong transaction ngắn.
- Ghi telemetry không được giữ transaction trong lúc gửi WebSocket.
- Với command, tạo bản ghi `PENDING` trước khi publish MQTT; sau phản hồi ESP32 mới cập nhật `APPLIED`/`REJECTED`. Sau 5 giây chưa có phản hồi, Backend đánh `TIMEOUT`.
- State hiển thị trên Dashboard phải là state thực tế nhận từ ESP32, không suy ra từ command vừa gửi.
- Alert lặp lại mỗi chu kỳ telemetry phải cập nhật alert đang active, không tạo một hàng mới sau mỗi 5 giây.
- `NO_WATER` và `OFFLINE` có severity `CRITICAL`; `SENSOR_FAULT` có severity `WARNING`.
- Demo đóng alert ngay khi điều kiện hết; bản hoàn thiện đóng sau 3 mẫu tốt liên tiếp.

## 8. Retention và downsampling

- V0.1 chưa tự động xóa telemetry.
- REST lịch sử hỗ trợ `bucket=raw|1m|5m|1h`; mặc định `raw`, `limit` đếm theo bucket khi tổng hợp.
- Giá trị số trong bucket lấy trung bình và bỏ `NULL`; `water_ok` lấy giá trị khác null cuối cùng, all-null trả `NULL`, bucket trống bị bỏ qua.
- V0.1 không cần bảng aggregate riêng; Backend có thể tổng hợp khi query.
- Nếu dữ liệu thực tế tăng lớn, nhóm sẽ chốt retention và bảng aggregate trong phiên bản sau.

## 9. Bảo mật và backup

- Không commit database runtime hoặc bản backup có dữ liệu nhạy cảm.
- API ghi cấu hình/lệnh không được mở công khai khi chưa có auth phù hợp.
- Demo chỉ chạy localhost có thể tắt auth; nếu mở ra LAN thì dùng API key tối thiểu.
- Trước khi chạy migration phá vỡ dữ liệu, phải backup database và kiểm tra đường rollback/khôi phục.

## 10. Tiêu chí hoàn thành database v0.1

- Có migration khởi tạo toàn bộ bảng và index đã duyệt.
- Migration chạy thành công trên SQLite sạch.
- Backend insert/query được telemetry và state.
- Command chuyển đúng `PENDING -> APPLIED/REJECTED/TIMEOUT`.
- Alert không bị tạo trùng mỗi chu kỳ cảm biến.
- API lịch sử lọc đúng device/time và trả thứ tự ổn định.
- Không có `.env`, credential hoặc file database runtime trong Git.
