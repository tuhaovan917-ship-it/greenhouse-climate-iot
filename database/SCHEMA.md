# Database Schema v0.1 - Greenhouse Climate IoT

## 1. Trạng thái

Đây là schema **đề xuất** của Người 3 để Người 2 và lead review. Tên API cuối cùng vẫn tuân theo `docs/api-contract.md` sau khi contract được duyệt và merge.

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
| `status` | varchar(16) | Không | `PENDING`, `APPLIED`, `REJECTED` |
| `reason` | varchar(64) | Có | Lý do từ chối hoặc lỗi |
| `requested_at` | datetime UTC | Không | Lúc Backend nhận REST request |
| `completed_at` | datetime UTC | Có | Lúc nhận kết quả cuối từ ESP32 |

Index:

- Composite index: `device_id, requested_at`.
- Index `status` nếu Backend thường xuyên tìm lệnh `PENDING` quá hạn.

Quy tắc:

- Backend ghi `PENDING` trước khi publish MQTT.
- Chỉ state/command result thực tế mới chuyển sang `APPLIED` hoặc `REJECTED`.
- Nếu không có phản hồi trong timeout đã thống nhất, API có thể trả trạng thái bổ sung `TIMEOUT`; cần chốt với Người 2 trước khi thêm vào contract.

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

Cần xác nhận:

- Firmware hiện chưa có `configId` hoặc payload phản hồi toàn bộ ngưỡng, nên Backend chưa thể khẳng định config đã được áp dụng.
- Nếu nhóm cần trạng thái `APPLIED/REJECTED`, phải bổ sung cơ chế acknowledgement vào MQTT contract trước.

## 8. Alert derivation v0.1

| Code | Điều kiện mở | Điều kiện đóng |
|---|---|---|
| `NO_WATER` | `water_ok=false` hoặc failsafe vì nước | `water_ok=true` ổn định theo quy tắc Backend |
| `SENSOR_FAULT` | Một trường cảm biến bắt buộc là `NULL` | Các trường hợp lệ trở lại |
| `OFFLINE` | MQTT status offline hoặc quá timeout | Nhận status online/message hợp lệ mới |

Khoảng timeout, số mẫu ổn định để đóng cảnh báo và severity cần được Người 2/lead xác nhận.

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

- Bucket dự kiến: `1m`, `5m`, `1h`.
- `temperature_c`, `humidity_pct`, `light_lux`: trung bình các giá trị khác `NULL`.
- `water_ok`: giá trị hợp lệ cuối bucket.
- Bucket không có dữ liệu được bỏ qua; Dashboard tự thể hiện khoảng trống.
- Không tạo aggregate table trong v0.1.

### Active alerts

- Lọc `device_id`, `active=true`.
- Sắp xếp `started_at DESC, id DESC`.

## 10. Kiểm thử schema/migration

1. Chạy migration từ database SQLite rỗng.
2. Insert telemetry hợp lệ và telemetry có trường `NULL`.
3. Từ chối humidity ngoài 0–100 và light âm nếu constraint DB được bật.
4. Upsert state không tạo nhiều hàng cho cùng `device_id`.
5. Command chuyển `PENDING -> APPLIED/REJECTED` đúng thời điểm.
6. Alert lặp cập nhật `last_seen_at`, không tạo hàng trùng.
7. Alert resolved có thể tái mở thành một đợt mới.
8. Query history sử dụng đúng composite index.
9. Chạy thử migration tương đương trên PostgreSQL trước khi tuyên bố chỉ cần đổi `DATABASE_URL`.
