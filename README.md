# Greenhouse Climate IoT

Hệ thống **giám sát và điều khiển môi trường nhà kính** bằng ESP32, MQTT, FastAPI, SQLite và React Dashboard. Phiên bản hiện tại được chạy thử với **ESP32 giả lập trên Wokwi**.

## 1. Chức năng

- Cảm biến: SHT31 (nhiệt độ, độ ẩm), BH1750 (ánh sáng) và công tắc mức nước.
- Điều khiển quạt thông gió, bơm phun sương, đèn trồng cây theo chế độ **AUTO** với hysteresis.
- **MANUAL**: gửi lệnh từ Dashboard qua Backend và MQTT; Dashboard hiển thị phản hồi thực tế, không tự giả định lệnh đã thành công.
- Failsafe: chặn bơm khi thiếu nước, xử lý lỗi cảm biến, khởi tạo ngõ ra ở trạng thái OFF.
- Khi mất Wi-Fi/MQTT ở MANUAL, ESP32 chuyển về AUTO sau khoảng **30 giây kể từ khi phát hiện mất kết nối**; khi nối lại, gửi trạng thái thực tế.
- Lưu các ngưỡng AUTO bằng Preferences/NVS; lưu dữ liệu và lịch sử tại Backend/SQLite.

## 2. Kiến trúc

```text
SHT31 / BH1750 / Water Switch
             |
             v
      ESP32 (Wokwi)
   AUTO / MANUAL / Failsafe
             |
             | MQTT greenhouse/01/*
             v
      Mosquitto (Docker)
             |
             v
 FastAPI Backend ---- SQLite + SQLModel + Alembic
             |
             | REST API / WebSocket
             v
    React / Vite Dashboard
```

ESP32 tự quyết định bật/tắt trong AUTO. Dashboard chỉ giao tiếp với Backend, không nối MQTT trực tiếp.

## 3. Thành phần công nghệ

| Thành phần | Công nghệ |
|---|---|
| Firmware | ESP32 Arduino, PlatformIO, Wokwi |
| MQTT client ESP32 | `256dpi/MQTT @ 2.5.3` |
| Broker | Eclipse Mosquitto 2.x, Docker |
| Backend | Python 3.11, FastAPI, Paho MQTT, SQLModel |
| Database | SQLite, Alembic |
| Dashboard | React, TypeScript, Vite |

Cấu trúc thư mục: `firmware/` (thiết bị), `backend/` (API và MQTT), `database/` (migration), `dashboard/` (giao diện), `docs/` (hợp đồng giao tiếp).

## 4. Chạy demo trên Windows

### 4.1. Yêu cầu

- Docker Desktop.
- Python 3.11, Node.js >= 22.22.2, npm.
- Visual Studio Code với tiện ích **PlatformIO IDE** và **Wokwi Simulator**.
- Chạy các lệnh dưới đây trong **PowerShell**, bắt đầu từ thư mục gốc dự án, trừ khi có ghi chú khác.

### 4.2. Khởi động MQTT Broker

```powershell
docker compose -p backend -f .\backend\docker-compose.yml up -d
docker ps --filter "name=greenhouse-mosquitto"
```

Broker demo chạy tại `localhost:1883`. Database persistence của Mosquitto nằm ở Docker volume gắn vào `/mosquitto/data/`.

### 4.3. Thiết lập Backend (lần đầu)

```powershell
py -3.11 -m venv .\backend\.venv
& ".\backend\.venv\Scripts\python.exe" -m pip install -r .\backend\requirements.txt -r .\database\requirements.txt
if (-not (Test-Path .\backend\.env)) {
    Copy-Item .\backend\.env.example .\backend\.env
}
```

Các giá trị mặc định trong `.env.example` hỗ trợ demo localhost. Không commit `.env` thật.

### 4.4. Khởi tạo/migrate SQLite (lần đầu hoặc khi có migration mới)

Mở **PowerShell mới** tại thư mục gốc. Đường dẫn sau bảo đảm Alembic và Backend cùng dùng file `backend/greenhouse.db`:

```powershell
Push-Location .\database
$env:DATABASE_URL = "sqlite:///../backend/greenhouse.db"
& "..\backend\.venv\Scripts\python.exe" -m alembic -c alembic.ini upgrade head
Remove-Item Env:\DATABASE_URL
Pop-Location
```

Không xóa database hiện có để chạy lại migration; Alembic quản lý các revision.

### 4.5. Khởi động Backend

Mở một PowerShell riêng, từ thư mục gốc:

```powershell
cd .\backend
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
```

- API Health: <http://127.0.0.1:8000/api/health>
- API State: <http://127.0.0.1:8000/api/state>
- Swagger API: <http://127.0.0.1:8000/docs>

Khi Broker và database sẵn sàng, API health kỳ vọng `{"status":"ok","mqttConnected":true,"db":"ok"}`.

### 4.6. Khởi động Dashboard

Mở PowerShell riêng, từ thư mục gốc:

```powershell
cd .\dashboard
npm.cmd ci
npm.cmd run dev
```

Mở <http://localhost:5173>.

### 4.7. Khởi động ESP32 trên Wokwi

1. Mở thư mục `firmware/` trong VS Code.
2. Chạy **PlatformIO: Build**.
3. Chạy **Wokwi: Start Simulator**.
4. Giữ MQTT Broker và Backend đang hoạt động.
5. Kiểm tra Serial có `Connected successfully`, `Subscribed to command/config`, `State published` và `Telemetry published`.

Firmware giả lập dùng Wi-Fi `Wokwi-GUEST`, Broker `host.wokwi.internal:1883`. Các địa chỉ này dành cho **Wokwi**, không phải cấu hình sẵn cho ESP32 vật lý.

**Lưu ý:** Không chạy `backend/demo_esp32_mock.py` đồng thời với Wokwi sử dụng cùng `deviceId=greenhouse-01`, vì có thể phát hai trạng thái cho cùng một thiết bị.

## 5. MQTT và điều khiển

| Topic | Hướng chính | QoS | Retain |
|---|---|---:|---|
| `greenhouse/01/telemetry` | ESP32 → Backend | 0 | Không |
| `greenhouse/01/state` | ESP32 → Backend | 1 | Có |
| `greenhouse/01/status` | ESP32 / Last Will → Backend | 1 | Có |
| `greenhouse/01/command` | Backend → ESP32 | 1 | Không |
| `greenhouse/01/config` | Backend → ESP32 | 1 | Không |

QoS 1 là cơ chế *at least once*: có thể nhận bản tin trùng. Firmware dùng `commandId` để chống thực thi lại lệnh trùng gần nhất. `POST /api/config` trả `PUBLISHED` chỉ có nghĩa Backend đã gửi yêu cầu, không phải ACK xác nhận ESP32 đã áp dụng đầy đủ mọi ngưỡng.

Chi tiết: [MQTT Protocol](docs/mqtt-protocol.md), [API Contract](docs/api-contract.md).

## 6. Kiểm thử và kết quả nghiệm thu (22/10/2026)

| Hạng mục | Kết quả |
|---|---|
| ESP32 PlatformIO build | PASS |
| Backend pytest | **57 passed**, 15 deprecation warnings |
| Dashboard unit tests | **42 passed** |
| Dashboard ESLint và production build | PASS |
| Dashboard ↔ Backend ↔ MQTT ↔ Wokwi, AUTO/MANUAL, điều khiển quạt | PASS |
| Failsafe thiếu nước và từ chối lệnh không an toàn | PASS trong các bài thử đã ghi nhận |
| Mất MQTT ở MANUAL, quạt ON → chuyển AUTO sau 30 giây, quạt OFF | PASS |
| MQTT reconnect, đồng bộ state thực tế | PASS |
| QoS 1 cho `state/status`, QoS 0 cho `telemetry` qua subscriber | PASS |
| Mosquitto lưu database và khôi phục retained messages | PASS |

Lệnh kiểm thử lại (từ thư mục gốc, với các dependency đã cài đặt):

```powershell
Push-Location .\backend
& ".\.venv\Scripts\python.exe" -m pytest -q
Pop-Location

Push-Location .\dashboard
npm.cmd run test
npm.cmd run lint
npm.cmd run build
Pop-Location

& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -d .\firmware
```

Báo cáo chi tiết: [Firmware Test Report](firmware/TEST_REPORT.md).

## 7. Giới hạn và lưu ý bảo mật

- Phiên bản nghiệm thu dùng **Wokwi**, chưa kiểm chứng trên ESP32 và thiết bị 12V vật lý.
- Broker demo sử dụng port `1883` và `allow_anonymous true`, **chưa bật TLS**. Không mở cấu hình demo này ra Internet hoặc mạng không đáng tin cậy.
- Backend có thể dùng `X-API-Key` cho API ghi khi cấu hình `API_KEY`; localhost demo có thể để trống.
- Bằng chứng QoS 1 được kiểm tra qua subscriber; chưa có bản chụp gói `PUBACK` độc lập ở cấp packet.
- Backend có 15 cảnh báo deprecation nhưng không có bài test thất bại.
- Không commit `.env`, credential, database runtime hoặc các file sao lưu.

## 8. Tài liệu liên quan

- [Firmware README](firmware/README.md)
- [Firmware Test Report](firmware/TEST_REPORT.md)
- [Backend README](backend/README.md)
- [Dashboard README](dashboard/README.md)
- [Database README](database/README.md)
- [MQTT Protocol](docs/mqtt-protocol.md)
- [API Contract](docs/api-contract.md)
