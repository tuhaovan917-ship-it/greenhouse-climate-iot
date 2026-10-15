# API Contract — Backend ↔ Dashboard (Greenhouse Climate IoT)

**Version:** 0.1 (draft, cần tv2 + tv3 xác nhận trước khi code thật)
**Base URL (dev):** `http://localhost:8000`
**Docs tự sinh:** `http://localhost:8000/docs` (FastAPI Swagger)
**Liên quan:** `docs/mqtt-protocol.md` v0.1 trên nhánh `feat/esp32` (topics `greenhouse/01/*`, JSON telemetry/state/command/config). File này KHÔNG định nghĩa lại MQTT, chỉ định nghĩa REST/WS cho Dashboard React+Vite+TS.

> Nguyên tắc (theo báo cáo GĐ2): Dashboard **không nối MQTT trực tiếp**. Mọi dữ liệu/lệnh đi qua Backend. ESP32 không có clock tin cậy nên mọi `receivedAt/updatedAt` đều do Backend sinh (UTC ISO8601).

---

## 1. Stack đã chốt

| Thành phần | Lựa chọn | Ghi chú |
|---|---|---|
| Backend | Python 3.11 + FastAPI + Uvicorn | `backend/` do Người 2 sở hữu |
| MQTT client | `paho-mqtt 2.x` | sub `telemetry/state/status`, pub `command/config` |
| ORM | SQLModel (SQLAlchemy 2.0) | 1 model dùng chung cho DB + API |
| DB mặc định | SQLite (WAL) `greenhouse.db` | đủ cho demo môn học, không cần cài server |
| DB nâng cấp | PostgreSQL qua `DATABASE_URL` | đổi env là chạy, không sửa code |
| Broker dev | Eclipse Mosquitto 2.x Docker `localhost:1883` | demo lớp, không phụ thuộc Internet |
| Broker TLS | `mqtts://:8883` khi cần | đổi `MQTT_URL` trong `.env`, không đổi code |
| Frontend | React + Vite + TypeScript | `dashboard/` do Người 3 sở hữu |

---

## 2. Quy ước chung

- `deviceId` cố định: `greenhouse-01` (mã nhà kính 01 như MQTT spec).
- Thời gian: string ISO8601 UTC, ví dụ `2026-10-15T10:00:00Z`. Backend sinh lúc nhận MQTT (`receivedAt`), lúc cập nhật state (`updatedAt`).
- Số liệu: `temperatureC` (float, °C), `humidityPct` (float 0–100), `lightLux` (float ≥ 0), `waterOk` (bool, `true` = còn nước). Giá trị lỗi từ ESP32 gửi `null`, **không** gửi `NaN`.
- `mode`: `AUTO` | `MANUAL`. `failsafeActive`: bool, ưu tiên cao nhất, có thể ghi đè cả 2 mode.
- Lỗi REST统一: `{ "detail": "..." }` kèm HTTP status chuẩn (400 validation, 404 not found, 409 conflict ví dụ gửi lệnh khi sai mode sẽ thể hiện ở `command_result`, không phải HTTP 500).

### TypeScript types (copy sang Dashboard)

```ts
export type ControlMode = "AUTO" | "MANUAL";
export type DeviceName = "fan" | "mist" | "lamp";
export type CommandResult = "APPLIED" | "REJECTED";

export interface Telemetry {
  id: number;
  deviceId: string;
  temperatureC: number | null;
  humidityPct: number | null;
  lightLux: number | null;
  waterOk: boolean;
  receivedAt: string; // ISO8601 UTC, do Backend sinh
}

export interface DeviceState {
  deviceId: string;
  mode: ControlMode;
  fan: boolean;
  mist: boolean;
  lamp: boolean;
  failsafeActive: boolean;
  lastCommandId: string | null;
  lastCommandResult: CommandResult | null;
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
```

---

## 3. REST API

### 3.1 `GET /api/health`
Kiểm tra sống. Trả về `{ "status": "ok", "mqttConnected": true, "db": "ok" }`.

### 3.2 `GET /api/telemetry?deviceId=greenhouse-01&from=&to=&limit=100&order=desc`
Lấy lịch sử để vẽ biểu đồ. `from/to` là ISO8601, `limit` mặc định 100, max 1000.
Trả về:
```json
{ "data": [ { "id": 1, "deviceId": "greenhouse-01", "temperatureC": 30.5, "humidityPct": 65.2, "lightLux": 450, "waterOk": true, "receivedAt": "2026-10-15T10:00:00Z" } ] }
```

### 3.3 `GET /api/telemetry/latest?deviceId=greenhouse-01`
1 bản tin mới nhất, dùng để hiển thị số liệu hiện tại khi WS chưa nối.

### 3.4 `GET /api/state?deviceId=greenhouse-01`
Trạng thái **thực tế** từ ESP32 (Backend cache từ topic `state`, kèm `updatedAt`). Dashboard hiển thị cái này, không tự đoán thiết bị đã bật chỉ vì vừa bấm nút.

### 3.5 `POST /api/commands`
Gửi lệnh MANUAL. Body:
```json
{ "deviceId": "greenhouse-01", "device": "fan", "on": true }
```
Backend sinh `commandId` (`cmd-<uuid ngắn>`), publish MQTT `greenhouse/01/command` `{ commandId, device, on }` (QoS 1, retain false), ghi `command_log` trạng thái `PENDING`.
Trả về `202`: `{ "commandId": "cmd-a1b2", "status": "PENDING" }`.
ESP32 chỉ thực thi khi đang `MANUAL` + qua kiểm tra an toàn, phản hồi qua topic `state` (`lastCommandId/lastCommandResult/reason`). Ví dụ bồn hết nước → `mist=true` bị `REJECTED` lý do `NO_WATER`, bơm vẫn tắt.

### 3.6 `GET /api/commands?deviceId=&limit=50`
Lịch sử lệnh + kết quả (`PENDING/APPLIED/REJECTED`, `reason`). Dùng để hiện toast/log trên Dashboard.

### 3.7 `GET /api/config?deviceId=greenhouse-01` / `POST /api/config`
Xem/sửa mode + ngưỡng hysteresis. Body giống `DeviceConfig` (mục 2). Backend validate ràng buộc ngưỡng rồi publish MQTT `greenhouse/01/config` (QoS 1, retain false). ESP32 lưu NVS + công bố lại `state`. Ngưỡng mặc định để test (không phải tối ưu cho cây):
`tempOn 30 / tempOff 28, humOn 55 / humOff 65, lightOn 300 / lightOff 700`.

### 3.8 `GET /api/alerts?deviceId=&from=&to=&limit=50` (tối thiểu)
Backend suy ra từ `state` + `telemetry`: `NO_WATER`, `SENSOR_FAULT`, `OFFLINE`. V0.1 chỉ cần 3 loại này, chưa cần rule phức tạp.

---

## 4. WebSocket realtime

### `WS /ws?deviceId=greenhouse-01`
Dashboard nối 1 socket duy nhất, nhận 4 loại message (JSON, có `type`):

```json
{ "type": "telemetry", "data": { "temperatureC": 30.5, "humidityPct": 65.2, "lightLux": 450, "waterOk": true, "receivedAt": "..." } }
{ "type": "state", "data": { "mode": "MANUAL", "fan": true, "mist": false, "lamp": false, "failsafeActive": false, "lastCommandId": "cmd-a1b2", "lastCommandResult": "APPLIED", "updatedAt": "..." } }
{ "type": "command_result", "data": { "commandId": "cmd-a1b2", "result": "REJECTED", "reason": "NO_WATER" } }
{ "type": "alert", "data": { "code": "NO_WATER", "message": "Bồn hết nước, bơm bị khóa", "at": "..." } }
```

Quy tắc: mất WS thì fallback polling `GET /latest` + `GET /state` mỗi 5s. Backend push `state` ngay khi nhận MQTT `state`, push `telemetry` ngay khi nhận MQTT `telemetry` (chu kỳ ESP32 ~5s).

---

## 5. Ánh xạ REST → MQTT (để tv2 + tv3 cùng hiểu)

| Dashboard gọi | Backend làm | MQTT |
|---|---|---|
| `POST /api/commands` | sinh `commandId`, validate MANUAL ở mức UX | pub `greenhouse/01/command` |
| `POST /api/config` | validate ngưỡng hysteresis | pub `greenhouse/01/config` |
| `GET /state`, `WS state` | cache bản tin cuối | sub `greenhouse/01/state` (QoS 1, retain true) |
| `GET /telemetry`, `WS telemetry` | insert DB + gắn `receivedAt` | sub `greenhouse/01/telemetry` (QoS 0) |
| Online/offline, alert `OFFLINE` | LWT + timeout quá hạn dữ liệu | sub `greenhouse/01/status` (retain true, `{"online":bool}`) |

Idempotency: MQTT QoS 1 có thể trùng, ESP32 де-dupe theo `commandId`. `command` **không retain** để tránh chạy lại lệnh cũ khi reconnect.

---

## 6. Kịch bản Demo cho Backend (khớp khung giảng viên mục 6)

- **KB1 — Lệnh hợp lệ:** Dashboard `MANUAL` → `POST /commands {fan:true}` → `202 PENDING` → WS `state {fan:true, lastCommandResult:APPLIED}`. Tương đương "Mở hợp lệ" trong mẫu Logistics.
- **KB2 — Failsafe:** mock `waterOk=false` → `POST /commands {mist:true}` → WS `command_result {REJECTED, NO_WATER}` + `alert NO_WATER`, bơm vẫn `false`. Tương đương "Đột nhập" trong mẫu.
- Chạy không cần ESP32 thật: `python backend/demo_esp32_mock.py` publish telemetry/state giả lên Mosquitto local, Dashboard vẫn test được full luồng.

---

## 7. Việc cần tv3 xác nhận (trả lời trước khi khóa v0.1)

1. `limit/order/from/to` ở mục 3.2 có đủ vẽ biểu đồ không, hay cần thêm `bucket=1m/5m` để downsample?
2. `GET /api/alerts` có cần hay chỉ cần WS `alert` là đủ?
3. Auth v0.1 để trống (mạng lớp) hay cần API-key/JWT ngay?
4. `DATABASE_URL` tv3 tự quản migration trong `database/` rồi Backend import, hay để Backend tự `create_all` cho nhanh demo?
