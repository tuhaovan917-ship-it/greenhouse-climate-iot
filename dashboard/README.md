# Web Dashboard - Greenhouse Climate IoT

## 1. Trạng thái tài liệu

- Phiên bản: `0.1-draft`.
- Người phụ trách: Người 3 - Database & Dashboard.
- Frontend đã thống nhất ở mức kiến trúc: **React + Vite + TypeScript**.
- Tài liệu này dựa trên bản nháp `docs/api-contract.md` ở nhánh `feat/backend` và `docs/mqtt-protocol.md` ở nhánh `feat/esp32`.
- Những mục ghi **Cần xác nhận** chưa phải contract chính thức và cần Người 2/lead duyệt trước khi code tích hợp.

## 2. Phạm vi Dashboard v0.1

Dashboard cần cung cấp các chức năng sau:

1. Hiển thị số liệu mới nhất:
   - Nhiệt độ (`temperatureC`).
   - Độ ẩm (`humidityPct`).
   - Cường độ ánh sáng (`lightLux`).
   - Tình trạng nước (`waterOk`).
2. Hiển thị trạng thái thực tế của hệ thống:
   - Chế độ `AUTO`/`MANUAL`.
   - Quạt (`fan`), bơm phun sương (`mist`) và đèn (`lamp`).
   - Failsafe, online/offline và thời điểm nhận dữ liệu cuối.
3. Vẽ biểu đồ lịch sử theo khoảng thời gian.
4. Hiển thị cảnh báo hiện tại và lịch sử cảnh báo.
5. Gửi yêu cầu đổi chế độ/cấu hình và điều khiển thiết bị trong MANUAL.
6. Hiển thị trạng thái lệnh `PENDING`, `APPLIED` hoặc `REJECTED` cùng lý do.

Ngoài phạm vi v0.1:

- Dashboard kết nối MQTT trực tiếp.
- Quản lý nhiều người dùng hoặc phân quyền phức tạp.
- Tự đưa ra quyết định AUTO thay cho ESP32.
- Tối ưu ngưỡng theo loại cây trồng.

## 3. Nguyên tắc tích hợp

- Dashboard chỉ gọi REST API và WebSocket của Backend.
- Không tự thay đổi MQTT topic hoặc payload JSON đã được nhóm thống nhất.
- Không cập nhật trạng thái thiết bị theo kiểu optimistic. Sau khi gửi lệnh, giao diện hiển thị `PENDING` và chờ `state`/`command_result` từ Backend.
- Dữ liệu được lưu và truyền bằng UTC ISO8601; giao diện có thể đổi sang múi giờ máy người dùng khi hiển thị.
- Các giá trị cảm biến lỗi phải hiển thị là không khả dụng, không chuyển `null` thành `0`.
- Thuật ngữ API dùng `mist`; giao diện tiếng Việt có thể hiển thị là “Bơm phun sương”.

## 4. API Dashboard sử dụng

### REST

| Mục đích | Endpoint dự kiến |
|---|---|
| Kiểm tra Backend | `GET /api/health` |
| Dữ liệu mới nhất | `GET /api/telemetry/latest?deviceId=` |
| Dữ liệu lịch sử | `GET /api/telemetry?deviceId=&from=&to=&limit=&order=&bucket=` |
| Trạng thái thực tế | `GET /api/state?deviceId=` |
| Gửi lệnh MANUAL | `POST /api/commands` |
| Lịch sử lệnh | `GET /api/commands?deviceId=&limit=` |
| Đọc/cập nhật cấu hình | `GET /api/config`, `POST /api/config` |
| Cảnh báo | `GET /api/alerts?deviceId=&from=&to=&limit=&active=` |

### WebSocket

- Kết nối: `WS /ws?deviceId=greenhouse-01`.
- Các message dự kiến: `telemetry`, `state`, `command_result`, `alert`.
- Khi WebSocket mất kết nối, Dashboard polling `telemetry/latest` và `state` mỗi 5 giây.
- Khi WebSocket kết nối lại, Dashboard tải lại latest state và các cảnh báo đang active trước khi tiếp tục nhận realtime.

## 5. Điểm cần Người 2 xác nhận

1. Thêm `bucket=raw|1m|5m|1h` cho lịch sử; mặc định `raw`.
2. Khi dùng bucket, các trường số lấy trung bình và `waterOk` lấy giá trị cuối bucket.
3. Giữ `GET /api/alerts`; WebSocket không thay thế lịch sử cảnh báo.
4. Bổ sung `online` và `lastSeenAt` vào state hoặc cung cấp endpoint status tương đương.
5. Cho phép `waterOk: boolean | null` để biểu diễn trạng thái cảm biến không đáng tin cậy.
6. Bổ sung TypeScript type cho `Command`, `CommandStatus`, `Alert` và WebSocket envelope.
7. Làm rõ `POST /api/config` chỉ xác nhận Backend đã publish hay ESP32 đã áp dụng cấu hình.
8. V0.1 không dùng JWT. Nếu Backend được mở ra LAN thì bảo vệ API ghi bằng API key cấu hình qua môi trường.

## 6. Trạng thái giao diện cần xử lý

Mỗi màn hình hoặc component gọi dữ liệu phải xử lý tối thiểu:

- `loading`: đang tải dữ liệu ban đầu.
- `ready`: đã có dữ liệu hợp lệ.
- `empty`: chưa có dữ liệu lịch sử.
- `stale`: dữ liệu cuối đã quá hạn nhưng chưa có xác nhận offline.
- `offline`: thiết bị được Backend xác định mất kết nối.
- `error`: REST/WS lỗi hoặc payload không hợp lệ.

Đối với lệnh điều khiển:

```text
IDLE -> PENDING -> APPLIED
                -> REJECTED (kèm reason)
                -> TIMEOUT (Dashboard không tự coi là thành công)
```

## 7. Cấu trúc thư mục dự kiến

```text
dashboard/
├── src/
│   ├── api/          # REST client và WebSocket client
│   ├── components/   # Component dùng chung
│   ├── features/
│   │   ├── overview/
│   │   ├── history/
│   │   ├── control/
│   │   └── alerts/
│   ├── hooks/
│   ├── types/        # TypeScript types khớp API contract
│   ├── utils/
│   └── main.tsx
├── .env.example
└── README.md
```

Thư viện biểu đồ và UI chưa khóa trong tài liệu này; chỉ chọn sau khi xác nhận không làm tăng phạm vi không cần thiết.

## 8. Biến môi trường dự kiến

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

Chỉ commit `.env.example`. Không commit `.env` hoặc thông tin bí mật.

## 9. Kế hoạch kiểm thử Dashboard

- Render đúng dữ liệu hợp lệ và các trường `null`.
- Không hiển thị `null` thành `0`.
- Biểu đồ lọc đúng `from/to`, thứ tự thời gian và bucket.
- WebSocket cập nhật realtime; mất WS chuyển sang polling 5 giây.
- Gửi lệnh hiển thị `PENDING` cho đến khi nhận kết quả thực tế.
- Hiển thị đúng `REJECTED/NO_WATER` và không bật giả trạng thái bơm.
- Reload trang vẫn tải được lịch sử cảnh báo qua REST.
- Kiểm thử tích hợp bằng `demo_esp32_mock.py` khi Backend cung cấp.
