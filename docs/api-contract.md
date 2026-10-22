# API Contract — Backend ↔ Dashboard (Greenhouse Climate IoT)

**Version:** 0.2.6 (quy tắc `reason` của một lệnh: lệnh mới xóa lý do cũ; đã sửa theo báo cáo của Người 1)
**Base URL (dev):** `http://localhost:8000`
**Docs tự sinh:** `http://localhost:8000/docs` (FastAPI Swagger)
**Liên quan:** `docs/mqtt-protocol.md` v0.1 trên nhánh `feat/esp32` (topics `greenhouse/01/*`, JSON telemetry/state/command/config); `database/SCHEMA.md` v0.2 trên nhánh `feat/dashboard` (5 bảng, index, dedup alert, severity). File này KHÔNG định nghĩa lại MQTT hay schema DB, chỉ định nghĩa REST/WS cho Dashboard React+Vite+TS.

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
- Số liệu: `temperatureC` (float, °C), `humidityPct` (float 0–100), `lightLux` (float ≥ 0), `waterOk` (`boolean | null`: `true` còn nước, `false` hết nước, `null` cảm biến không đáng tin). Giá trị lỗi từ ESP32 gửi `null`, **không** gửi `NaN`. Backend cũng tự chuẩn hoá: giá trị không phải số, là `NaN`/`Infinity` hoặc nằm ngoài dải vật lý (`temperatureC` -40..125, `humidityPct` 0..100, `lightLux` ≥ 0) đều được lưu thành `null` kèm log cảnh báo. Chỉ `false` mới báo `NO_WATER`; `null` báo `SENSOR_FAULT` + khóa bơm failsafe.
- `mode`: `AUTO` | `MANUAL`. `failsafeActive`: bool, ưu tiên cao nhất, có thể ghi đè cả 2 mode.
- **`reason` thuộc về đúng một lệnh:** khi ESP32 phản hồi lệnh mới, `reason` của lệnh cũ bị xóa (`null`) nếu lệnh mới không kèm lý do. Lệnh có `lastCommandResult: "REJECTED"` luôn đi kèm `reason` (`NO_WATER`, `NOT_MANUAL_MODE`, `INVALID_DEVICE`); lệnh `APPLIED` thì `reason` là `null`. ESP32 publish lại `state` định kỳ với **cùng** `lastCommandId` thì giữ nguyên `reason` đã biết.
- Thứ tự ổn định: mọi list sắp xếp `receivedAt/startedAt DESC, id DESC` (thêm `id` làm khóa phụ khi timestamp trùng).
- Lỗi REST thống nhất: `{ "detail": "..." }` kèm HTTP status chuẩn (400 validation, 404 not found). Kết quả lệnh sai mode/hết nước thể hiện ở `command_result` (`REJECTED`), không phải HTTP 500.
- Body `POST` không phân biệt hoa thường cho `mode` (`"manual"` được chuẩn hoá thành `MANUAL`); sai kiểu hoặc sai giá trị trả 422.

### TypeScript types (copy sang Dashboard)

```ts
export type ControlMode = "AUTO" | "MANUAL";
export type DeviceName = "fan" | "mist" | "lamp";
export type CommandStatus = "PENDING" | "APPLIED" | "REJECTED" | "TIMEOUT";
export type TerminalCommandResult = "APPLIED" | "REJECTED" | "TIMEOUT"; // WS command_result chỉ dùng 3 giá trị này, không dùng PENDING
export type Bucket = "raw" | "1m" | "5m" | "1h";
export type AlertCode = "NO_WATER" | "SENSOR_FAULT" | "OFFLINE";
export type AlertSeverity = "INFO" | "WARNING" | "CRITICAL";

export interface Telemetry {
  id: number; // chỉ có ở bucket=raw; response bucket tổng hợp dùng TelemetryBucket (không có id)
  deviceId: string;
  temperatureC: number | null;
  humidityPct: number | null;
  lightLux: number | null;
  waterOk: boolean | null;
  receivedAt: string; // ISO8601 UTC, do Backend sinh
}
// GET /api/telemetry/latest trả `null` khi chưa có bản tin nào.

export interface TelemetryBucket {
  deviceId: string;
  bucketStart: string; // ISO8601 UTC, thời điểm bắt đầu bucket (căn UTC, xem mục 3.2)
  bucket: Exclude<Bucket, "raw">;
  sampleCount: number; // số bản tin raw trong [bucketStart, bucketEnd)
  temperatureC: number | null; // average bỏ NULL, all-null thì null
  humidityPct: number | null;
  lightLux: number | null;
  waterOk: boolean | null; // giá trị khác null cuối bucket, all-null thì null
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
  updatedAt: string | null; // null khi thiết bị chưa từng gửi state
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

// REST lịch sử (mục 3.2). Backend KHÔNG push bucket qua WS; WS chỉ luồng raw telemetry.
export interface TelemetryHistoryResponse {
  bucket: Bucket;
  data: Telemetry[] | TelemetryBucket[]; // Bucket="raw" -> Telemetry[], ngược lại -> TelemetryBucket[]
}

export type WsMessage =
  | { type: "telemetry"; data: Telemetry } // luôn raw, mỗi bản tin nhận từ MQTT
  | { type: "state"; data: DeviceState }
  | { type: "ping" } // heartbeat từ server (v0.2.4), Dashboard bỏ qua
  | { type: "command_result"; data: { commandId: string; result: TerminalCommandResult; reason?: string | null; wasLate?: boolean } }
  | { type: "alert"; data: Alert };
// Quy ước: PENDING chỉ xuất hiện ở REST 202 + GET /commands, không bao giờ xuất hiện trong WS command_result hay state.lastCommandResult.
```

---

## 3. REST API

### 3.1 `GET /api/health`
Kiểm tra sống. Trả về `{ "status": "ok", "mqttConnected": true, "db": "ok" }`.

### 3.2 `GET /api/telemetry?deviceId=greenhouse-01&from=&to=&limit=100&order=desc&bucket=raw|1m|5m|1h`
Lịch sử vẽ biểu đồ. `from/to` ISO8601 theo semantics **[from, to)** (`from` inclusive, `to` exclusive, vắng `to` = now) để các lần query liên tiếp không trùng dữ liệu.
- `limit` mặc định 100, max 1000. **Luôn lấy N dòng/bucket MỚI NHẤT trong khoảng lọc**; `order` chỉ quyết định thứ tự trả về, không đổi tập dữ liệu được lấy. Nhờ vậy `order=asc&limit=N` vẫn trả N mẫu mới nhất đúng thứ tự vẽ biểu đồ, không phải N mẫu cũ nhất trong khoảng.
- Khi số dòng khớp `from/to` vượt `MAX_SCAN_ROWS` (mặc định 20000, cấu hình qua env), Backend trả **400** kèm gợi ý thu hẹp khoảng thời gian hoặc dùng bucket lớn hơn, **không** cắt bớt dữ liệu âm thầm.
- `order` áp dụng cho `receivedAt` (raw) hoặc `bucketStart` (bucket), khóa phụ `id` để thứ tự ổn định khi timestamp trùng.
- `raw`: `data` là `Telemetry[]`.
- `1m|5m|1h`: `data` là `TelemetryBucket[]`. Bucket căn theo UTC epoch (`1m` tại :00, `5m` tại :00/:05/..., `1h` tại đầu giờ); `bucketStart` là thời điểm bắt đầu bucket; số lấy average bỏ NULL; `waterOk` lấy giá trị khác null cuối bucket (all-null thì null); `sampleCount` đếm mọi bản tin raw trong bucket; bucket trống bỏ qua. V0.1 tổng hợp lúc query, chưa bảng aggregate.
Envelope luôn là `TelemetryHistoryResponse` (`{ bucket, data }`) cho cả hai trường hợp.

`bucket=raw`:
```json
{ "bucket": "raw", "data": [ { "id": 1, "deviceId": "greenhouse-01", "temperatureC": 30.5, "humidityPct": 65.2, "lightLux": 450, "waterOk": true, "receivedAt": "2026-10-15T10:00:00Z" } ] }
```

`bucket=5m`:
```json
{ "bucket": "5m", "data": [ { "deviceId": "greenhouse-01", "bucketStart": "2026-10-15T10:00:00Z", "bucket": "5m", "sampleCount": 12, "temperatureC": 30.4, "humidityPct": 65.0, "lightLux": 452.3, "waterOk": true } ] }
```

### 3.3 `GET /api/telemetry/latest?deviceId=greenhouse-01`
1 bản tin mới nhất (`receivedAt DESC, id DESC`), dùng khi WS chưa nối. **Nếu chưa có bản tin nào thì trả `200` với body `null`** (không phải lỗi) — Dashboard tải song song nhiều endpoint, một lỗi ở đây sẽ làm hỏng cả trang.

### 3.4 `GET /api/state?deviceId=greenhouse-01`
Trạng thái **thực tế** từ ESP32 (cache topic `state` + `status`), gồm `online`, `lastSeenAt`, `updatedAt`. `online=false` khi LWT offline hoặc quá 15s không có message hợp lệ. Dashboard hiển thị cái này, không tự đoán thiết bị đã bật chỉ vì vừa bấm nút. Reload trang gọi lại endpoint này + `GET /api/alerts?active=true`.
**Nếu thiết bị chưa từng gửi state thì trả `200` với trạng thái mặc định** (`mode: "AUTO"`, các thiết bị `false`, `failsafeActive: false`, `online: false`, `lastSeenAt: null`, `updatedAt: null`) thay vì lỗi 404.

### 3.5 `POST /api/commands`
Gửi lệnh MANUAL. Body:
```json
{ "deviceId": "greenhouse-01", "device": "fan", "on": true }
```
Backend sinh `commandId` (`cmd-<uuid ngắn>`), ghi `command_logs` `PENDING` (`requestedAt` = giờ nhận REST), publish MQTT `greenhouse/01/command` `{ commandId, device, on }` (QoS 1, retain false).
Trả về `202`: `{ "commandId": "cmd-a1b2", "status": "PENDING" }`.
ESP32 chỉ thực thi khi đang `MANUAL` + qua kiểm tra an toàn, phản hồi qua topic `state`. Backend cập nhật `APPLIED/REJECTED` (`completedAt` = giờ nhận phản hồi). Nếu `COMMAND_TIMEOUT_S` (mặc định 5s) không phản hồi Backend tự đánh `TIMEOUT` (`completedAt` = giờ timeout, Backend-side, không thuộc MQTT spec) và **push WebSocket `command_result` với `result: "TIMEOUT"`, `reason: "TIMEOUT"`** (Dashboard nhận được ngay, không cần polling).
**Late response (sau TIMEOUT):** phản hồi thiết bị đến muộn luôn được chấp nhận (last-write-wins theo `completedAt`): ghi đè `TIMEOUT` thành `APPLIED/REJECTED` thực tế, push thêm một WS `command_result` kèm `wasLate: true`, đồng thời cập nhật `device_state.lastCommand*` theo phản hồi mới nhất. Trùng lặp QoS 1 (cùng `commandId` + cùng kết quả) là no-op, không push WS thừa. Dashboard key theo `commandId`, hiển thị kết quả cuối, hiện ghi chú "phản hồi trễ" khi `wasLate`, không tự gửi lại lệnh chỉ vì `TIMEOUT` (gửi lại = `commandId` mới). `COMMAND_TIMEOUT_S` cấu hình được qua env.

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
1 socket duy nhất, message theo `WsMessage` (mục 2). `command_result.result` chỉ nhận `APPLIED | REJECTED | TIMEOUT` (không nhận `PENDING`). Ví dụ rút gọn:
```json
{ "type": "state", "data": { "deviceId": "greenhouse-01", "mode": "MANUAL", "fan": true, "online": true, "lastSeenAt": "...", "updatedAt": "..." } }
{ "type": "command_result", "data": { "commandId": "cmd-a1b2", "result": "APPLIED", "wasLate": false } }
```
Quy tắc: mất WS fallback polling `GET /latest` + `GET /state` mỗi 5s; nối lại thì tải latest state + `GET /alerts?active=true` trước khi nhận realtime. Backend push `state` khi nhận MQTT `state/status`, push `telemetry` khi nhận MQTT `telemetry` (~5s).

### Heartbeat (v0.2.4)

- **Server chủ động ping:** mỗi 20 giây Backend gửi `{"type": "ping"}` qua WebSocket. Dashboard có thể bỏ qua message này, chỉ cần **bỏ qua mọi `type` lạ** để không vỡ.
- **Dashboard không cần gửi gì:** socket **không** bị đóng chỉ vì Dashboard im lặng. Trình duyệt không gửi được WebSocket ping frame từ JavaScript nên contract không yêu cầu client ping.
- Dashboard gửi text bất kỳ cũng được (Backend chỉ log, không xử lý).
- Socket chết được phát hiện khi Backend gửi thất bại, khi đó Backend dọn socket và Dashboard cần tự reconnect.

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

## 9. Thay đổi ở v0.2 / v0.2.1 (khóa với tv3)

- v0.2: thêm `bucket` + quy tắc aggregate; giữ `GET /alerts` + filter `active/code`; `online/lastSeenAt` + timeout 15s + severity; `waterOk nullable`; types `CommandLog/Alert/WsMessage` + `TIMEOUT`; `POST /config` trả `PUBLISHED` (chưa ack); auth API key LAN; workflow Alembic; sửa typo REST + de-dupe.
- v0.2.1 (làm rõ sau commit `076adf3` của tv3, không đổi MQTT payload): 1. bucket trả `TelemetryBucket` riêng (có `sampleCount`, không dùng `Telemetry.id`), căn bucket UTC epoch, lọc `[from, to)`; 2. late response sau `TIMEOUT` luôn ghi đè thành `APPLIED/REJECTED` + push WS kèm `wasLate: true` (last-write-wins, trùng QoS 1 là no-op, `COMMAND_TIMEOUT_S` cấu hình được); 3. `command_result.result` thu hẹp `TerminalCommandResult` (không nhận `PENDING`).
- v0.2.2 (chỉnh theo tv3): 1. bỏ `telemetry_bucket` khỏi `WsMessage`, thêm type REST `TelemetryHistoryResponse`; 2. ví dụ JSON mục 3.2 có envelope `{bucket, data}` cho cả `raw` và bucket; 3. tham chiếu `SCHEMA.md` v0.2.
- v0.2.3 (Backend đã triển khai, không đổi tên trường/topic): 1. `limit` lấy N mới nhất, `order` chỉ đảo thứ tự trả về; 2. vượt `MAX_SCAN_ROWS` trả 400 thay vì cắt bớt; 3. giá trị cảm biến ngoài dải vật lý → `null` kèm log; 4. `mode` trong body không phân biệt hoa thường.
- v0.2.4 (sau review tv3): 1. `TIMEOUT` push WebSocket `command_result` (`result: "TIMEOUT"`, `reason: "TIMEOUT"`); 2. heartbeat: server ping mỗi 20s (`{"type":"ping"}`), socket không bị đóng vì Dashboard im lặng, Dashboard không cần gửi ping; 3. `app/models.py` có CheckConstraint cho `humidity_pct` (0–100) và `light_lux` (≥ 0) để Alembic sinh migration đúng `SCHEMA.md` §3; 4. `psycopg[binary]` có trong `requirements.txt` cho đường PostgreSQL.
- v0.2.5 (tích hợp Dashboard): 1. `GET /api/telemetry/latest` trả `200` + `null` thay vì 400 khi chưa có dữ liệu; 2. `GET /api/state` trả `200` + trạng thái mặc định (`online: false`) thay vì 404 khi thiết bị chưa gửi state; 3. type `DeviceState.updatedAt` thành `string | null`. Dashboard tải 6 endpoint song song nên không endpoint nào được trả lỗi khi hệ thống còn trống.
- v0.2.6 (sau báo cáo của Người 1 về firmware thật): 1. `reason` thuộc về đúng một lệnh — lệnh mới (`lastCommandId` khác) xóa lý do của lệnh cũ, kể cả khi lệnh mới không gửi kèm `reason`; 2. publish lại `state` với cùng `lastCommandId` vẫn giữ lý do đã biết; 3. `command_logs` cũng vậy: kết quả mới thay lý do cũ (late `APPLIED` không còn để lại `reason: "TIMEOUT"`).
