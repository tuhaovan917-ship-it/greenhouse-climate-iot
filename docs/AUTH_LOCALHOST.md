# Greenhouse Climate IoT — Bảo mật bắt buộc trên localhost (A6.4)

> **Phạm vi:** Demo Windows / Wokwi / localhost. Không phải cấu hình công khai qua LAN hoặc Internet. Phải bổ sung HTTPS, cookie `Secure`, bảo mật MQTT, giới hạn truy cập, và xử lý rate limit khi triển khai ngoài localhost.

## Điều kiện trước khi chạy

- Nhánh `enhance/auth-rbac` đã tích hợp A3–A6, Admin được bootstrap bằng mật khẩu riêng.
- Docker Desktop hoạt động. ESP32 Wokwi kết nối broker Mosquitto `localhost:1883` qua địa chỉ giả lập `host.wokwi.internal`.
- `backend/greenhouse.db` đã được migrate bằng Alembic và có ít nhất một Admin.
- Đã lưu bản sao SQLite bằng `sqlite3.Connection.backup()` và kiểm tra `PRAGMA integrity_check=ok`.
- Hai file **cục bộ** `backend/.env`, `dashboard/.env` đã cấu hình nghiêm ngặt và được Git ignore.
- Không để Backend khác đang chạy chung `MQTT_CLIENT_ID`, và không để 8000/5173 bị chiếm cổng. Dừng cổng 8001 từ bài thử A6 nếu còn chạy.

## Khởi động chỉ với 2 cửa sổ PowerShell

**Cửa sổ 1** (Backend + Mosquitto):

```powershell
cd C:\Users\tuhaovan\Desktop\do_an\IoT\greenhouse-climate-iot-final
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ops\start_backend_secure.ps1
```

**Cửa sổ 2** (Dashboard), sau khi cửa sổ 1 báo `Application startup complete`:

```powershell
cd C:\Users\tuhaovan\Desktop\do_an\IoT\greenhouse-climate-iot-final
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ops\start_dashboard_secure.ps1
```

Sau đó mở `http://localhost:5173/`, đăng nhập tài khoản của mình và chạy Wokwi từ VS Code. Không cần tab PowerShell thứ ba cho Wokwi.

Hai script ghi đè **cờ bảo mật bắt buộc** theo từng tiến trình, không sửa `.env` hoặc database:

| Chạy Backend | Chạy Dashboard |
| --- | --- |
| `AUTH_ENFORCEMENT_ENABLED=1` | `VITE_AUTH_GATE_ENABLED=1` |
| `MQTT_ENABLED=1` | `VITE_API_BASE_URL=http://localhost:8000` |
| `DATABASE_URL=sqlite:///./greenhouse.db` | `VITE_WS_URL=ws://localhost:8000/ws` |
| `AUTH_COOKIE_SECURE=0` *(localhost HTTP)* | `VITE_API_KEY=` *(không đưa secret vào frontend)* |

> `.env.example` trong repository vẫn tương thích demo cũ và có thể ghi `0`; **chỉ sử dụng hai script ở trên để khởi chạy bản A6 bảo mật**. Đừng đánh đồng một file `.env.example` với cấu hình triển khai thực tế.

## Kiểm tra thành công

1. `http://localhost:8000/api/health` trả `status:ok`, `db:ok`, `mqttConnected:true` (trước khi Wokwi chạy vẫn có thể kết nối MQTT).
2. Trong cửa sổ ẩn danh, `http://localhost:5173/` hiện trang đăng nhập; không tải telemetry/WS trước khi có session.
3. Không có cookie, `GET /api/state` trả `401`; Admin login rồi refresh (F5) vẫn ở Dashboard.
4. Wokwi gửi telemetry/state, thiết bị chuyển `Trực tuyến`, chỉ số và thời gian nhận cập nhật.
5. ADMIN/OPERATOR chuyển AUTO→MANUAL, thử bật/tắt quạt Wokwi và đợi `command_result=APPLIED`, sau đó **trở về AUTO**.
6. Đăng xuất làm REST trả `401` và WS bị đóng; VIEWER không thể gửi lệnh (`403`).
7. Tắt Wokwi thì hiện Offline sau timeout; không thử gửi lệnh điều khiển khi Offline.

## Kiểm thử hồi quy trên máy có `.env` strict

Để tránh bài test legacy đọc cấu hình Auth=1 của file `.env`, dùng biến **riêng trong PowerShell chạy test** (không thay file `.env`):

```powershell
cd C:\Users\tuhaovan\Desktop\do_an\IoT\greenhouse-climate-iot-final
$oldAuth = $env:AUTH_ENFORCEMENT_ENABLED
$oldMqtt = $env:MQTT_ENABLED
try {
    $env:AUTH_ENFORCEMENT_ENABLED = '0'
    $env:MQTT_ENABLED = '0'
    Push-Location .\backend
    try {
        & '.\.venv\Scripts\python.exe' -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw 'BACKEND_TESTS_FAILED' }
    } finally { Pop-Location }
} finally {
    [Environment]::SetEnvironmentVariable('AUTH_ENFORCEMENT_ENABLED', $oldAuth, 'Process')
    [Environment]::SetEnvironmentVariable('MQTT_ENABLED', $oldMqtt, 'Process')
}
```

Dashboard: `npm run lint`, `npm test`, `$env:VITE_AUTH_GATE_ENABLED='1'; npm run build`. Toàn bộ `113 backend` và `61 dashboard` tests đã PASS ở A6.4.2. Đừng chạy các script integration legacy có gửi lệnh bên ngoài Auth khi đang bật strict trên Backend chính.

## Quay lui an toàn về demo legacy (chỉ trên localhost)

1. Nhấn `Ctrl+C` ở cửa sổ Vite và FastAPI đang chạy. **Không** xóa hay ghi đè SQLite; giữ Docker/Mosquitto đang chạy.
2. Trong cửa sổ **Backend riêng**, từ `backend/`:

```powershell
$env:DATABASE_URL='sqlite:///./greenhouse.db'
$env:AUTH_ENFORCEMENT_ENABLED='0'
$env:MQTT_ENABLED='1'
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

3. Trong cửa sổ **Dashboard riêng**, từ `dashboard/`:

```powershell
$env:VITE_AUTH_GATE_ENABLED='0'
$env:VITE_API_BASE_URL='http://localhost:8000'
$env:VITE_WS_URL='ws://localhost:8000/ws'
& npm.cmd run dev -- --host localhost --port 5173 --strictPort
```

4. Đây là **chế độ demo không bắt buộc đăng nhập**. Chỉ sử dụng trên máy riêng, không mở qua LAN/Internet. Muốn quay lại strict, dừng cả hai server rồi chạy lại `ops/start_*_secure.ps1`.
5. Không khôi phục bản sao SQLite cũ trừ khi có hỏng dữ liệu thực sự và đã đánh giá lượng telemetry/log phát sinh sau bản sao.

## Bảo mật và giới hạn

- Các session cookie HttpOnly/SameSite, CSRF và RBAC bảo vệ REST/WS ở chế độ strict; Viewer chỉ xem, Operator/Admin có quyền điều khiển theo chính sách Backend.
- Mosquitto demo cổng `1883` không bật TLS/auth chặt chẽ; không đưa broker ra Internet. Trong Wokwi thiết bị là mô phỏng, không phải phần cứng 12V đã nghiệm thu.
- Không commit file `.env`, `.db`, `*.db-wal`, `*.db-shm`, session token, CSRF token hay mật khẩu. `VITE_*` là biến có thể hiển thị trong bundle.
- Giai đoạn A6.4 chỉ chuẩn hóa thao tác vận hành **localhost**. Không ngầm tuyên bố đây là sản phẩm production-ready.

### A6.5.5 - MQTT localhost

- Docker Compose publish MQTT tại `127.0.0.1:1883`, thay vì `0.0.0.0:1883`.
- Wokwi sử dụng `host.wokwi.internal` để kết nối qua IoT Gateway.
- Backend kết nối MQTT qua `localhost:1883`.
- Broker vẫn cho phép kết nối ẩn danh trong môi trường demo.
- Không dùng cấu hình này để mở MQTT ra LAN hoặc Internet khi chưa có xác thực, ACL và TLS.
- Kiểm tra Docker bằng `docker port greenhouse-mosquitto 1883/tcp`.
- Kết quả mong đợi: `127.0.0.1:1883`.

## A6.7.2 - SQLite Backup & Recovery

Xem [SQLITE_RECOVERY.md](SQLITE_RECOVERY.md) de backup va phuc hoi SQLite an toan.
