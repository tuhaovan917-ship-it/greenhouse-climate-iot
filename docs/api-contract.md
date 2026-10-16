# API Contract — Backend ↔ Dashboard (Greenhouse Climate IoT)

**Version:** 0.2 (đã chốt với tv3: bucket, alerts history, online/lastSeenAt, waterOk nullable, API key LAN, Alembic)
**Base URL (dev):** `http://localhost:8000`
**Docs tự sinh:** `http://localhost:8000/docs` (FastAPI Swagger)
**Liên quan:** `docs/mqtt-protocol.md` v0.1 trên nhánh `feat/esp32` (topics `greenhouse/01/*`, JSON telemetry/state/command/config); `database/SCHEMA.md` v0.1 trên nhánh `feat/dashboard` (5 bảng, index, dedup alert). File này KHÔNG định nghĩa lại MQTT hay schema DB, chỉ định nghĩa REST/WS cho Dashboard React+Vite+TS.

> Nguyên tắc (theo báo cáo GĐ2): Dashboard **không nối MQTT trực tiếp**. Mọi dữ liệu/lệnh đi qua Backend. ESP32 không có clock tin cậy nên mọi `receivedAt/updatedAt` đều do Backend sinh (UTC ISO8601).

---

## 1. Stack đã chốt

| Thành phần | Lựa chọn | Ghi chú |
|---|---|---|
| Backend | Python 3.11 + FastAPI + Uvicorn | `backend/` do Người 2 sở hữu |
| MQTT client | `paho-mqtt 2.x` | sub `telemetry/state/status`, pub `command/config` |
| ORM | SQLModel (SQLAlchemy 2.0) | model dùng chung cho DB + API, snake_case DB / camelCase API |
| DB mặc định | SQLite (WAL) `greenhouse.db` | đủ cho demo môn học, không cần cài server |
| DB nâng cấp | PostgreSQL qua `DATABASE_URL` | đổi env là chạy, không sửa code |
| Migration | Alembic trong `database/` do tv3 quản | Backend chạy `alembic upgrade head`; `create_all()` chỉ test/demo tạm |
| Broker dev | Eclipse Mosquitto 2.x Docker `localhost:1883` | demo lớp, không phụ thuộc Internet |
| Broker TLS | `mqtts://:8883` khi cần | đổi `MQTT_URL` trong `.env`, không đổi code |
| Frontend | React + Vite + TypeScript | `dashboard/` do Người 3 sở hữu |

---

## 2. Quy ước chung

- `deviceId` mặc định `greenhouse-01` nhưng schema/API không hard-code 1 thiết bị.
- Thời gian: string ISO8601 UTC, ví dụ `2026-10-15T10:00:00Z`. Backend sinh lúc nhận MQTT (`receivedAt`), lúc cập nhật state (`updatedAt`, `lastSeenAt`).
- Số liệu: `temperatureC` (float, °C), `humidityPct` (float 0–100), `lightLux` (float ≥ 0), `waterOk` (`boolean | null`: `true` còn nước, `false` hết nước, `null` cảm biến không đáng tin). Giá trị lỗi từ ESP32 gửi `null`, **không** gửi `NaN`. Chỉ `false` mới báo `NO_WATER`; `null` báo `SENSOR_FAULT` + khóa bơm failsafe.
- `mode`: `AUTO` | `MANUAL`. `failsafeActive`: bool, ưu tiên cao nhất, có thể ghi đè cả 2 mode.
- Thứ tự ổn định: mọi list sắp xếp `receivedAt/startedAt DESC, id DESC` (thêm `id` làm khóa phụ khi timestamp trùng).
- Lỗi REST thống nhất: `{ "detail": "..." }` kèm HTTP status chuẩn (400 validation, 404 not found). Kết quả lệnh sai mode/hết nước thể hiện ở `command_result` (`REJECTED`), không phải HTTP 500.

### TypeScript types (copy sang Dashboard)

```ts
export type ControlMode = "AUTO" | "MANUAL";
export type DeviceName = "fan" | "mist" | "lamp";
export type CommandStatus = "PENDING" | "APPLIED" | "REJECTED" | "TIMEOUT";
export type AlertCode = "NO_WATER" | "SENSOR_FAULT" | "OFFLINE";
export type AlertSeverity = "INFO" | "WARNING" | "CRITICAL";

export interface Telemetry {
  id: number;
  deviceId: string;
  temperatureC: number | null;
  humidityPct: number | null;
  lightLux: number | null;
  waterOk: boolean | null;
  receivedAt: string; // ISO8601 UTC, do Backend sinh
}

export interface DeviceState {
  deviceId: string;
  mode: ControlMode;
  fan: boolean;
  mist: boolean;
  lamp: boolean;
  failsafeActive: boolean;
  online: boolean; // từ MQTT status LWT + timeout 15s
  lastSeenAt: string | null; // lần cuối nhận message hợp lệ
  lastCommandId: string | null;
  lastCommandResult: "APPLIED" | "REJECTED" | null;
  reason?: string | null; // NOT_MANUAL_MODE | NO_WATER | ...
  updatedAt: string;
}

export interface DeviceConfig {
  mode: ControlMode;
  tempOnC: number; tempOffC: number;
  humidityOnPct: number; humidityOffPct: number;
  lightOnLux: number; lightOffLux: number;
}
// Ràng buộc: tempOnC > tempOffC, humidityOnPct < humidityOffPct, lightOnLux < lightOffLux

export interface CommandLog {
  commandId: string;
  deviceId: string;
  device: DeviceName;
  requestedOn: boolean;
  status: CommandStatus; // TIMEOUT do Backend tự đánh sau 5s không phản hồi
  reason?: string | null;
  requestedAt: string;
  completedAt: string | null;
}

export interface Alert {
  id: number;
  deviceId: string;
  code: AlertCode;
  severity: AlertSeverity; // NO_WATER CRITICAL, OFFLINE CRITICAL, SENSOR_FAULT WARNING
  message: string;
  active: boolean;
  startedAt: string;
  lastSeenAt: string;
  resolvedAt: string | null;
}

export type WsMessage =
  | { type: "telemetry"; data: Telemetry }
  | { type: "state"; data: DeviceState }
  | { type: "command_result"; data: { commandId: string; result: CommandStatus; reason?: string | null } }
  | { type: "alert"; data: Alert };
```

---

## 3. REST API

### 3.1 `GET /api/health`
Kiểm tra sống. Trả về `{ "status": "ok", "mqttConnected": true, "db": "ok" }`.

### 3.2 `GET /api/telemetry?deviceId=greenhouse-01&from=&to=&limit=100&order=desc&bucket=raw|1m|5m|1h`
Lịch sử vẽ biểu đồ. `from/to` ISO8601, `limit` mặc định 100 max 1000 (đếm theo bucket khi dùng bucket), `order` asc/desc, `bucket` mặc định `raw`.
- `raw`: trả từng bản ghi.
- `1m|5m|1h`: số lấy average bỏ NULL, `waterOk` lấy giá trị khác null cuối bucket (all-null thì null), bucket trống bỏ qua, `receivedAt` = `bucketStart`. V0.1 tổng hợp lúc query, chưa bảng aggregate.
```json
{ "data": [ { "id": 1, "deviceId": "greenhouse-01", "temperatureC": 30.5, "humidityPct": 65.2, "lightLux": 450, "waterOk": true, "receivedAt": "2026-10-15T10:00:00Z" } ] }
```

### 3.3 `GET /api/telemetry/latest?deviceId=greenhouse-01`
1 bản tin mới nhất (`receivedAt DESC, id DESC`), dùng khi WS chưa nối.

### 3.4 `GET /api/state?deviceId=greenhouse-01`
Trạng thái **thực tế** từ ESP32 (cache topic `state` + `status`), gồm `online`, `lastSeenAt`, `updatedAt`. `online=false` khi LWT offline hoặc quá 15s không có message hợp lệ. Dashboard hiển thị cái này, không tự đoán thiết bị đã bật chỉ vì vừa bấm nút. Reload trang gọi lại endpoint này + `GET /api/alerts?active=true`.

### 3.5 `POST /api/commands`
Gửi lệnh MANUAL. Body:
```json
{ "deviceId": "greenhouse-01", "device": "fan", "on": true }
```
Backend sinh `commandId` (`cmd-<uuid ngắn>`), ghi `command_logs` `PENDING` (`requestedAt` = giờ nhận REST), publish MQTT `greenhouse/01/command` `{ commandId, device, on }` (QoS 1, retain false).
Trả về `202`: `{ "commandId": "cmd-a1b2", "status": "PENDING" }`.
ESP32 chỉ thực thi khi đang `MANUAL` + qua kiểm tra an toàn, phản hồi qua topic `state`. Backend cập nhật `APPLIED/REJECTED` (`completedAt` = giờ nhận phản hồi). Nếu 5s không phản hồi Backend tự đánh `TIMEOUT` (Backend-side, không thuộc MQTT spec). Ví dụ bồn hết nước → `mist=true` bị `REJECTED` lý do `NO_WATER`, bơm vẫn tắt.

### 3.6 `GET /api/commands?deviceId=&limit=50`
Lịch sử lệnh (`PENDING/APPLIED/REJECTED/TIMEOUT`, `reason`). Dùng hiện toast/log.

### 3.7 `GET /api/config?deviceId=greenhouse-01` / `POST /api/config`
Xem/sửa cấu hình mong muốn (mode + ngưỡng hysteresis). Body giống `DeviceConfig`. Backend validate ràng buộc ngưỡng, lưu `device_configs` (`updatedAt` = giờ nhận REST, `publishedAt` = giờ publish), publish MQTT `greenhouse/01/config` (QoS 1, retain false).
Trả về `202`: `{ "status": "PUBLISHED", "config": { ...desired } }` — **chỉ xác nhận Backend đã publish, chưa khẳng định ESP32 đã áp dụng**, vì firmware hiện chưa có `configId`/payload ack toàn bộ ngưỡng (xem `SCHEMA.md` §7). Dashboard theo dõi `GET /state` đổi `mode` để suy ra, không coi `PUBLISHED` là đã áp dụng. Muốn ack đầy đủ phải sửa MQTT contract thêm `configId`.
Ngưỡng test mặc định: `tempOn 30 / tempOff 28, humOn 55 / humOff 65, lightOn 300 / lightOff 700`.

### 3.8 `GET /api/alerts?deviceId=&active=&code=&from=&to=&limit=50`
Lịch sử + hiện tại cảnh báo (`NO_WATER`, `SENSOR_FAULT`, `OFFLINE`). WS `alert` chỉ realtime, REST mới khôi phục sau reload/reconnect. Quy tắc dedup theo `SCHEMA.md` §6: cùng `device_id + code` thì update alert active (`lastSeenAt`), hết điều kiện thì `active=false + resolvedAt`, tái diễn tạo đợt mới. Demo đóng immediate, bản cuối yêu cầu 3 mẫu tốt liên tiếp (tv2/tv3 chốt sau).

---

## 4. WebSocket realtime

### `WS /ws?deviceId=greenhouse-01`
1 socket duy nhất, message theo `WsMessage` (mục 2). Ví dụ rút gọn:
```json
{ "type": "state", "data": { "deviceId": "greenhouse-01", "mode": "MANUAL", "fan": true, "online": true, "lastSeenAt": "...", "updatedAt": "..." } }
```
Quy tắc: mất WS fallback polling `GET /latest` + `GET /state` mỗi 5s; nối lại thì tải latest state + `GET /alerts?active=true` trước khi nhận realtime. Backend push `state` khi nhận MQTT `state/status`, push `telemetry` khi nhận MQTT `telemetry` (~5s).

---

## 5. Auth v0.1

- Localhost demo: để trống.
- Mở ra LAN: `POST /api/commands` và `POST /api/config` yêu cầu header `X-API-Key` (giá trị trong `.env` `API_KEY`, rỗng = tắt kiểm tra). GET/WS mở. Chưa JWT.

## 6. DB workflow (khớp `database/README.md`)

- tv3 giữ `SCHEMA.md` + Alembic trong `database/`; bạn triển khai SQLModel table models theo schema.
- Alembic metadata import models từ Backend để tạo/review migration; 2 bên review diff trước commit. Không sửa migration đã dùng chung.
- Runtime: Backend đọc `DATABASE_URL` (`sqlite:///./greenhouse.db` demo WAL, `postgresql+psycopg://...` nâng cấp), chạy `alembic upgrade head`. Không hard-code credential, chỉ commit `.env.example`. File `*.db*` runtime không commit. SQLite bật FK enforcement nếu dùng FK.

## 7. Ánh xạ REST → MQTT

| Dashboard gọi | Backend làm | MQTT |
|---|---|---|
| `POST /api/commands` | sinh `commandId`, ghi `PENDING` | pub `greenhouse/01/command` |
| `POST /api/config` | validate ngưỡng, lưu desired, ghi `publishedAt` | pub `greenhouse/01/config` |
| `GET /state`, `WS state` | cache bản tin cuối + `online/lastSeenAt` | sub `greenhouse/01/state` (QoS 1, retain true) |
| `GET /telemetry`, `WS telemetry` | insert DB + `receivedAt` | sub `greenhouse/01/telemetry` (QoS 0) |
| Online/offline, alert `OFFLINE` | LWT + timeout 15s | sub `greenhouse/01/status` (retain true, `{"online":bool}`) |

Idempotency: MQTT QoS 1 có thể trùng, ESP32 de-dupe theo `commandId`. `command` **không retain** để tránh chạy lại lệnh cũ khi reconnect.

---

## 8. Kịch bản Demo cho Backend (khớp khung giảng viên mục 6)

- **KB1 — Lệnh hợp lệ:** Dashboard `MANUAL` → `POST /commands {fan:true}` → `202 PENDING` → WS `state {fan:true, lastCommandResult:APPLIED}`.
- **KB2 — Failsafe:** mock `waterOk=false` → `POST /commands {mist:true}` → WS `command_result {REJECTED, NO_WATER}` + `alert NO_WATER`, bơm vẫn `false`. `waterOk=null` demo `SENSOR_FAULT` tương tự.
- Chạy không cần ESP32 thật: `python backend/demo_esp32_mock.py [--no-water]` publish telemetry/state giả lên Mosquitto local.

---

## 9. Thay đổi ở v0.2 (khóa với tv3)

1. Thêm `bucket` + quy tắc aggregate; 2. Giữ `GET /alerts` + filter `active/code`; 3. `online/lastSeenAt` + timeout 15s + severity; 4. `waterOk nullable`; 5. Types `CommandLog/Alert/WsMessage` + `TIMEOUT`; 6. `POST /config` trả `PUBLISHED` (chưa ack); 7. Auth API key LAN; 8. Workflow Alembic; 9. Sửa typo REST + de-dupe.
