# Web Dashboard - Greenhouse Climate IoT

## 1. Trạng thái tài liệu

- Phiên bản tài liệu: `0.2.5-implementation`.
- Người phụ trách: Người 3 - Database & Dashboard.
- Frontend đã thống nhất ở mức kiến trúc: **React + Vite + TypeScript**.
- Tài liệu và TypeScript types đã đồng bộ với `docs/api-contract.md` v0.2.5 trên nhánh `feat/backend` và `docs/mqtt-protocol.md` ở nhánh `feat/esp32`.
- Tám quyết định tích hợp ở mục 5 và ba chi tiết kỹ thuật ở mục 6 đã được Người 2 và Người 3 thống nhất.

### Trạng thái triển khai

Các milestone Overview, biểu đồ lịch sử và control flow đã có:

- Scaffold React + Vite + TypeScript và giao diện sáng/tối bằng Tailwind CSS.
- TypeScript types cho REST/WebSocket, bao gồm response union riêng cho telemetry raw/bucket.
- Fixture kiểm thử cho trạng thái bình thường, offline, hết nước và lỗi cảm biến; runtime chỉ dùng dữ liệu Backend thật.
- Màn Overview responsive: sensor cards, kết nối, mode, failsafe và actuator state.
- Chế độ sáng/tối có switch trên header, mặc định theo hệ điều hành và ghi nhớ lựa chọn trong trình duyệt.
- Biểu đồ lịch sử responsive bằng Recharts cho nhiệt độ, độ ẩm và ánh sáng.
- Bộ chọn khoảng `15m|1h|6h|24h` và độ phân giải `raw|1m|5m|1h`; mỗi lần đổi chỉ request bucket đang xem với `from/to` thật.
- Bucket không phù hợp với khoảng rộng bị khóa để tránh vượt giới hạn scan và response của Backend.
- Empty state cho bucket chưa có dữ liệu và fixture history theo đúng envelope `{ bucket, data }`.
- Unit test cho dữ liệu hợp lệ, trường `null`, `waterOk=false`, `waterOk=null` và offline.
- Unit test cho bucket mặc định, chuyển sang raw, ba biểu đồ và empty state.
- Khu vực điều khiển từ xa chỉ mở khi trạng thái thực tế là `MANUAL` và thiết bị online.
- Luồng lệnh theo `commandId`: `PENDING → APPLIED|REJECTED|TIMEOUT`, hiển thị lý do và phản hồi trễ.
- Không optimistic update actuator, không tự gửi lại sau timeout và chống xử lý thừa message QoS 1 trùng kết quả.
- Khóa bơm khi `waterOk=false|null`; `POST /config` chỉ hiển thị `PUBLISHED` và tiếp tục chờ mode thực tế từ ESP32.
- Form cấu hình đủ sáu ngưỡng hysteresis, validate cùng quy tắc Backend trước khi publish.
- Khu vực cảnh báo tách rõ cảnh báo đang hoạt động và lịch sử đã xử lý, hiển thị severity, code và thời gian.
- Empty state khi hệ thống an toàn; cấu trúc sẵn sàng khôi phục lịch sử từ `GET /api/alerts` sau reload/reconnect.
- REST client đã tích hợp telemetry/state/history/config/commands/alerts theo contract Backend v0.2.5.
- Dashboard chạy live-only qua REST/WebSocket; không còn chế độ dữ liệu mô phỏng trong runtime.
- Hệ thống mới chưa có telemetry vẫn vào trạng thái ready: sensor hiển thị chưa có dữ liệu, không đổi thành 0 và bơm tiếp tục bị khóa an toàn.
- Dữ liệu quá 10 giây được đánh dấu chậm cập nhật nhưng Dashboard không tự suy ra offline; `online` vẫn do Backend quyết định.
- Một WebSocket duy nhất nhận telemetry/state/command_result/alert, bỏ qua heartbeat `ping` do server gửi, tự reconnect và fallback polling 5 giây.
- Khi reconnect, Dashboard tải lại latest telemetry, state và lịch sử cảnh báo; biểu đồ được đồng bộ lại định kỳ.

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
6. Hiển thị trạng thái lệnh `PENDING`, `APPLIED`, `REJECTED` hoặc `TIMEOUT` cùng lý do.

Ngoài phạm vi v0.1:

- Dashboard kết nối MQTT trực tiếp.
- Giao diện quản trị vòng đời tài khoản và xem audit logs (RBAC Viewer/Operator/Admin cơ bản đã có ở A6).
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
| Cảnh báo | `GET /api/alerts?deviceId=&active=&code=&from=&to=&limit=` |

### WebSocket

- Kết nối: `WS /ws?deviceId=greenhouse-01`.
- Các message dự kiến: `telemetry`, `state`, `command_result`, `alert`, `ping`.
- Backend gửi `{"type":"ping"}` mỗi 20 giây; Dashboard không gửi heartbeat và bỏ qua type không nhận diện.
- Khi WebSocket mất kết nối, Dashboard polling `telemetry/latest` và `state` mỗi 5 giây.
- Khi WebSocket kết nối lại, Dashboard tải lại latest state và các cảnh báo đang active trước khi tiếp tục nhận realtime.
- `GET /api/telemetry/latest` có thể trả `200 null`; `DeviceState.updatedAt` cũng có thể là `null` trước bản tin state đầu tiên.

## 5. Quyết định đã thống nhất với Backend

1. Lịch sử hỗ trợ `bucket=raw|1m|5m|1h`, mặc định `raw`; `limit` đếm theo bucket khi tổng hợp.
2. Trong bucket, các trường số lấy trung bình và bỏ `NULL`; `waterOk` lấy giá trị khác null cuối cùng, all-null trả `null`, bucket trống bị bỏ qua.
3. Giữ REST `GET /api/alerts` với filter `active` và `code`; WebSocket chỉ phục vụ realtime.
4. `DeviceState` có `online` và `lastSeenAt`; Backend xác định offline bằng LWT hoặc 15 giây không nhận message hợp lệ.
5. `waterOk` có kiểu `boolean | null`: `false` sinh `NO_WATER`; `null` sinh `SENSOR_FAULT` và khóa bơm failsafe.
6. Contract cung cấp type cho `CommandLog`, `Alert` và WebSocket envelope. Command có thêm trạng thái Backend-side `TIMEOUT` sau 5 giây.
7. `POST /api/config` trả `202 { status: "PUBLISHED", config: desired }`; đây không phải xác nhận ESP32 đã áp dụng.
8. Mốc v0.1 dùng X-API-Key tùy chọn trong legacy mode. Bản A6 localhost strict sử dụng session cookie, CSRF và RBAC; không dùng JWT.

## 6. Chi tiết đã được Backend làm rõ ở v0.2.1

1. Dữ liệu bucket dùng `TelemetryBucket` riêng, không có `id`, có `sampleCount`; bucket căn theo UTC epoch và khoảng lọc dùng `[from, to)`.
2. Phản hồi đến sau `TIMEOUT` được phép ghi đè thành `APPLIED/REJECTED`; WebSocket gửi `wasLate=true`. Dashboard không tự gửi lại lệnh.
3. `WsMessage.command_result.result` chỉ nhận `APPLIED | REJECTED | TIMEOUT`; `PENDING` chỉ có ở REST và lịch sử lệnh.

Phía Dashboard định nghĩa `TelemetryHistoryResponse` riêng cho REST và không đưa `telemetry_bucket` vào `WsMessage`, vì Backend chỉ push raw telemetry realtime.

## 7. Trạng thái giao diện cần xử lý

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

Khi late response cập nhật lệnh đã timeout, Dashboard phải nhận và hiển thị kết quả cuối mới với ghi chú phản hồi trễ; không tự gửi lại lệnh chỉ vì `TIMEOUT`.

## 8. Cấu trúc thư mục dự kiến

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
│   ├── test/         # Fixture chỉ dùng cho unit test, không vào runtime
│   ├── types/        # TypeScript types khớp API contract
│   ├── utils/
│   └── main.tsx
├── .env.example
└── README.md
```

UI dùng Tailwind CSS; biểu đồ lịch sử dùng Recharts.

## 9. Biến môi trường dự kiến

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
VITE_DEVICE_ID=greenhouse-01
# Bật cổng xác thực của Dashboard A6
VITE_AUTH_GATE_ENABLED=1
# Legacy demo only; không dùng API key làm xác thực A6
VITE_API_KEY=
```

Chỉ commit `.env.example`. Không commit `.env` hoặc thông tin bí mật.

## 10. Kế hoạch kiểm thử Dashboard

- Render đúng dữ liệu hợp lệ và các trường `null`.
- Không hiển thị `null` thành `0`.
- Biểu đồ lọc đúng `from/to`, thứ tự thời gian và bucket.
- WebSocket cập nhật realtime; mất WS chuyển sang polling 5 giây.
- Sau 15 giây không có message hợp lệ, giao diện hiển thị offline theo state từ Backend.
- Gửi lệnh hiển thị `PENDING` cho đến khi nhận kết quả thực tế hoặc `TIMEOUT`.
- Không tự gửi lại lệnh sau `TIMEOUT`; xử lý được phản hồi đến muộn nếu Backend cho phép cập nhật kết quả cuối.
- Hiển thị đúng `REJECTED/NO_WATER` và không bật giả trạng thái bơm.
- Phân biệt `waterOk=false` (`NO_WATER`) với `waterOk=null` (`SENSOR_FAULT`).
- Reload trang vẫn tải được lịch sử cảnh báo qua REST.
- Kiểm thử tích hợp bằng hardware simulator `backend/demo_esp32_mock.py`, sau đó kiểm tra với ESP32 thật.

## 11. Chạy Dashboard local

Yêu cầu Node.js `22.22.2+` và npm. Có thể dùng phiên bản được ghi trong `.nvmrc`.
Backend phải chạy trước tại URL được cấu hình trong `.env`.

```bash
cd dashboard
cp .env.example .env
npm install
npm run dev
```

Các lệnh kiểm tra trước khi commit:

```bash
npm run lint
npm test
npm run build
```

Không commit `.env`, `node_modules/` hoặc `dist/`.


## 12. Dashboard bảo mật A6

Phần này cập nhật trạng thái triển khai sau các mốc v0.1
và v0.2.x ở phía trên.

- Chạy localhost secure bằng `ops/start_backend_secure.ps1`
  và `ops/start_dashboard_secure.ps1` từ thư mục gốc.
- Backend bật `AUTH_ENFORCEMENT_ENABLED=1`, Dashboard bật
  `VITE_AUTH_GATE_ENABLED=1`.
- Mặc định truy cập `/` phải đăng nhập; không còn dùng route
  preview legacy để bỏ qua Auth Gate khi strict được bật.
- Đăng nhập qua `POST /api/auth/login`; session được quản lý
  bằng cookie HttpOnly, không lưu token phiên vào localStorage.
- Refresh trang gọi `GET /api/auth/me` để khôi phục session;
  logout gọi `POST /api/auth/logout` với `X-CSRF-Token`.
- REST nghiệp vụ và WebSocket chỉ khởi chạy sau khi phiên
  hợp lệ; session hết hạn hoặc bị thu hồi phải quay về Login.
- Viewer có quyền xem và UI read-only. Operator và Admin
  có thể gửi yêu cầu cấu hình/điều khiển với CSRF hợp lệ.
- Backend vẫn thực thi RBAC; khóa nút trên UI không thay thế
  kiểm tra phân quyền ở server.
- Biến `VITE_*` được đưa vào frontend bundle; tuyệt đối
  không đặt mật khẩu hoặc session token trong các biến này.
- Đã xác nhận 61/61 Dashboard tests, ESLint và secure build
  trên cấu hình nghiệm thu A6.
- Quản lý tài khoản Operator/Viewer và hiển thị audit logs
  chưa có giao diện/API quản trị hoàn chỉnh ở giai đoạn A6.
- Cấu hình localhost không được xem là production-ready.

Xem `docs/AUTH_LOCALHOST.md`, `docs/api-contract.md` mục 5,
và `database/SCHEMA.md` mục 12.
