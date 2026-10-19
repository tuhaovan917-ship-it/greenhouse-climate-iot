# Database Schema v0.2.4 - Greenhouse Climate IoT

## 1. Trạng thái

Schema này đã được đồng bộ với `docs/api-contract.md` v0.2.4 và SQLModel metadata tại Backend commit `5f04d1e` trên nhánh `feat/backend`. SQLModel table models và mọi Alembic migration sinh từ schema vẫn phải được Người 2 và Người 3 cùng review.

Các nguyên tắc:

- Hỗ trợ SQLite cho demo và PostgreSQL khi nâng cấp.
- Không hard-code duy nhất một `device_id` trong schema.
- Dữ liệu cảm biến lỗi dùng `NULL`.
- Timestamp do Backend sinh và lưu UTC.
- API dùng camelCase, database dùng snake_case.

## 2. Quan hệ tổng quát

```text
device_id
  ├── telemetry_readings  (nhiều bản ghi lịch sử)
  ├── device_states       (một trạng thái mới nhất)
  ├── command_logs        (nhiều lệnh)
  ├── alerts              (nhiều cảnh báo)
  └── device_configs      (một cấu hình mong muốn mới nhất)
```

V0.1 chưa cần bảng `devices` riêng vì chỉ có `greenhouse-01`. Các bảng vẫn giữ `device_id` để không khóa thiết kế vào một thiết bị.

## 3. Bảng `telemetry_readings`

Dữ liệu cảm biến nhận từ MQTT topic `telemetry`. Đây là bảng append-only.

| Cột | Kiểu logic | Null | Mô tả |
|---|---|---:|---|
| `id` | integer/bigint | Không | Primary key tự tăng |
| `device_id` | varchar(64) | Không | Ví dụ `greenhouse-01` |
| `temperature_c` | float | Có | Nhiệt độ; `NULL` khi cảm biến lỗi |
| `humidity_pct` | float | Có | Độ ẩm 0–100; `NULL` khi lỗi |
| `light_lux` | float | Có | Ánh sáng ≥ 0; `NULL` khi lỗi |
| `water_ok` | boolean | Có | `true`: còn nước; `false`: hết nước; `NULL`: không đáng tin cậy |
| `received_at` | datetime UTC | Không | Backend sinh khi nhận MQTT |

Constraint đề xuất:

- `humidity_pct IS NULL OR humidity_pct BETWEEN 0 AND 100`.
- `light_lux IS NULL OR light_lux >= 0`.

Index:

- Composite index: `device_id, received_at`.
- REST `order` phải thêm `id` làm khóa phụ để thứ tự ổn định khi timestamp trùng nhau.

API mapping: `Telemetry`.

## 4. Bảng `device_states`

Lưu trạng thái thực tế mới nhất của từng thiết bị. Backend upsert khi nhận topic `state` hoặc `status`.

| Cột | Kiểu logic | Null | Mô tả |
|---|---|---:|---|
| `device_id` | varchar(64) | Không | Primary key |
| `mode` | varchar(16) | Không | `AUTO` hoặc `MANUAL` |
| `fan` | boolean | Không | Trạng thái quạt thực tế |
| `mist` | boolean | Không | Trạng thái bơm thực tế |
| `lamp` | boolean | Không | Trạng thái đèn thực tế |
| `failsafe_active` | boolean | Không | Failsafe đang hoạt động |
| `online` | boolean | Không | Trạng thái từ MQTT status/LWT/timeout |
| `last_seen_at` | datetime UTC | Có | Lần cuối nhận message hợp lệ từ thiết bị |
| `last_command_id` | varchar(64) | Có | Command gần nhất được ESP32 phản hồi |
| `last_command_result` | varchar(16) | Có | `APPLIED` hoặc `REJECTED` |
| `reason` | varchar(64) | Có | Ví dụ `NOT_MANUAL_MODE`, `NO_WATER` |
| `updated_at` | datetime UTC | Không | Lần cập nhật state gần nhất |

Không đặt foreign key bắt buộc từ `last_command_id` sang `command_logs`, vì state có thể đến từ phiên chạy hoặc nguồn lệnh khác mà Backend hiện tại không còn log.

API mapping: `DeviceState`, bổ sung `online` và `lastSeenAt`.

## 5. Bảng `command_logs`

Theo dõi vòng đời lệnh gửi từ Dashboard tới ESP32.

| Cột | Kiểu logic | Null | Mô tả |
|---|---|---:|---|
| `command_id` | varchar(64) | Không | Primary key do Backend sinh |
| `device_id` | varchar(64) | Không | Thiết bị nhận lệnh |
| `device` | varchar(16) | Không | `fan`, `mist` hoặc `lamp` |
| `requested_on` | boolean | Không | Trạng thái Dashboard yêu cầu |
| `status` | varchar(16) | Không | `PENDING`, `APPLIED`, `REJECTED`, `TIMEOUT` |
| `reason` | varchar(64) | Có | Lý do từ chối hoặc lỗi |
| `requested_at` | datetime UTC | Không | Lúc Backend nhận REST request |
| `completed_at` | datetime UTC | Có | Lúc nhận kết quả cuối từ ESP32 |

Index:

- Composite index: `device_id, requested_at`.
- Index `status` nếu Backend thường xuyên tìm lệnh `PENDING` quá hạn.

Quy tắc:

- Backend ghi `PENDING` trước khi publish MQTT.
- Chỉ state/command result thực tế mới chuyển sang `APPLIED` hoặc `REJECTED`.
- Nếu không có phản hồi sau 5 giây, Backend chuyển lệnh sang `TIMEOUT`; đây là trạng thái Backend-side, không thay đổi MQTT spec.
- Backend push `TIMEOUT` qua WebSocket ngay khi hết hạn. Phản hồi hợp lệ đến muộn ghi đè thành kết quả thực tế `APPLIED/REJECTED`, cập nhật `completed_at` và được Dashboard đánh dấu `wasLate=true`.

## 6. Bảng `alerts`

Lưu cảnh báo do Backend suy ra từ telemetry/state/status.

| Cột | Kiểu logic | Null | Mô tả |
|---|---|---:|---|
| `id` | integer/bigint | Không | Primary key tự tăng |
| `device_id` | varchar(64) | Không | Thiết bị phát sinh cảnh báo |
| `code` | varchar(32) | Không | V0.1: `NO_WATER`, `SENSOR_FAULT`, `OFFLINE` |
| `severity` | varchar(16) | Không | `INFO`, `WARNING` hoặc `CRITICAL` |
| `message` | text | Không | Nội dung hiển thị |
| `active` | boolean | Không | Cảnh báo còn hiệu lực |
| `started_at` | datetime UTC | Không | Lần đầu phát hiện trong một đợt |
| `last_seen_at` | datetime UTC | Không | Lần gần nhất điều kiện vẫn tồn tại |
| `resolved_at` | datetime UTC | Có | Thời điểm điều kiện hết |

Index:

- Composite index: `device_id, started_at`.
- Composite index: `device_id, active`.

Quy tắc chống trùng:

- Với cùng `device_id + code`, Backend cập nhật alert active hiện tại thay vì insert mỗi chu kỳ telemetry.
- Khi điều kiện hết, đặt `active=false` và `resolved_at`.
- Khi lỗi tái diễn sau khi đã resolved, tạo một alert mới để giữ lịch sử từng đợt.

API mapping: REST alert history và WebSocket `alert`.

## 7. Bảng `device_configs`

Lưu cấu hình mong muốn gần nhất do Dashboard gửi. Bản ghi này không tự chứng minh ESP32 đã áp dụng cấu hình.

| Cột | Kiểu logic | Null | Mô tả |
|---|---|---:|---|
| `device_id` | varchar(64) | Không | Primary key |
| `mode` | varchar(16) | Không | `AUTO` hoặc `MANUAL` mong muốn |
| `temp_on_c` | float | Không | Ngưỡng bật quạt |
| `temp_off_c` | float | Không | Ngưỡng tắt quạt |
| `humidity_on_pct` | float | Không | Ngưỡng bật bơm |
| `humidity_off_pct` | float | Không | Ngưỡng tắt bơm |
| `light_on_lux` | float | Không | Ngưỡng bật đèn |
| `light_off_lux` | float | Không | Ngưỡng tắt đèn |
| `updated_at` | datetime UTC | Không | Lần Backend nhận yêu cầu cuối |
| `published_at` | datetime UTC | Có | Lần Backend publish config cuối |

Constraint:

- `temp_on_c > temp_off_c`.
- `humidity_on_pct < humidity_off_pct`.
- `light_on_lux < light_off_lux`.

V0.1 thực thi ba ràng buộc hysteresis tại Backend trước khi ghi/publish. Metadata
commit `5f04d1e` chưa khai báo chúng thành DB `CheckConstraint`; Alembic không tự
thêm constraint ngoài single-source metadata.

Quy tắc v0.2:

- Firmware hiện chưa có `configId` hoặc payload phản hồi toàn bộ ngưỡng, nên Backend chưa thể khẳng định config đã được áp dụng.
- `POST /api/config` chỉ trả `PUBLISHED` kèm desired config. Nếu nhóm cần trạng thái `APPLIED/REJECTED`, phải bổ sung acknowledgement và `configId` vào MQTT contract trước.

## 8. Alert derivation v0.1

| Code | Severity | Điều kiện mở | Điều kiện đóng |
|---|---|---|---|
| `NO_WATER` | `CRITICAL` | Chỉ khi `water_ok=false` | `water_ok=true`; `null` chuyển sang lỗi cảm biến, không phải hết nước |
| `SENSOR_FAULT` | `WARNING` | Một trường cảm biến bắt buộc là `NULL` | Các trường hợp lệ trở lại |
| `OFFLINE` | `CRITICAL` | MQTT LWT offline hoặc 15 giây không có message hợp lệ | Nhận status online/message hợp lệ mới |

Demo đóng alert ngay khi điều kiện hết. Bản hoàn thiện yêu cầu 3 mẫu tốt liên tiếp trước khi đóng để hạn chế trạng thái chập chờn.

## 9. Query phục vụ Dashboard

### Latest telemetry

- Lọc theo `device_id`.
- Sắp xếp `received_at DESC, id DESC`.
- Lấy một bản ghi.

### History raw

- Lọc `device_id` và khoảng `from/to`.
- Sắp xếp theo `received_at` và `id`.
- Áp dụng `limit` tối đa theo API contract.

### History bucket

- Bucket đã thống nhất: `raw`, `1m`, `5m`, `1h`; mặc định `raw`.
- `temperature_c`, `humidity_pct`, `light_lux`: trung bình các giá trị khác `NULL`.
- `water_ok`: giá trị khác null cuối bucket; nếu tất cả đều null thì trả `NULL`.
- Bucket không có dữ liệu được bỏ qua; Dashboard tự thể hiện khoảng trống.
- `limit` đếm theo số bucket khi tổng hợp.
- `received_at` của dữ liệu tổng hợp là thời điểm bắt đầu bucket (`bucketStart`).
- Không tạo aggregate table trong v0.1.

### Active alerts

- Lọc `device_id`, `active=true`.
- Sắp xếp `started_at DESC, id DESC`.

## 10. Chi tiết contract đã khóa

1. Bucket tổng hợp dùng `TelemetryBucket` riêng, không có `id` và có `sampleCount`.
2. Bucket căn theo UTC epoch; khoảng lọc dùng `[from, to)`.
3. `limit` luôn lấy N dòng/bucket mới nhất trong khoảng; `order` chỉ đổi thứ tự trả về.
4. Phản hồi MQTT đến sau `TIMEOUT` ghi đè bằng `APPLIED/REJECTED` thực tế và có `wasLate=true`.
5. Backend gửi heartbeat WebSocket `{"type":"ping"}` mỗi 20 giây; Dashboard bỏ qua và không gửi ping.

## 11. Kiểm thử schema/migration

Initial Alembic revision: `20261019_01_create_initial_greenhouse_tables.py`,
autogenerate từ Backend metadata commit `5f04d1e`.

Revision này đã được kiểm tra upgrade/check/downgrade trên SQLite và PostgreSQL;
hai constraint `ck_telemetry_humidity_range` và
`ck_telemetry_light_non_negative` đều từ chối dữ liệu ngoài dải như thiết kế.

1. Chạy migration từ database SQLite rỗng.
2. Insert telemetry hợp lệ và telemetry có trường `NULL`.
3. Từ chối humidity ngoài 0–100 và light âm nếu constraint DB được bật.
4. Upsert state không tạo nhiều hàng cho cùng `device_id`.
5. Command chuyển `PENDING -> APPLIED/REJECTED/TIMEOUT` đúng thời điểm và kiểm thử phản hồi đến muộn sau timeout.
6. Alert lặp cập nhật `last_seen_at`, không tạo hàng trùng.
7. Alert resolved có thể tái mở thành một đợt mới.
8. Query history sử dụng đúng composite index.
9. Chạy thử migration tương đương trên PostgreSQL trước khi tuyên bố chỉ cần đổi `DATABASE_URL`.
