# SQLite Backup & Recovery — Greenhouse Climate IoT (A6.7.2)

> Phạm vi: bản demo trên Windows PowerShell 5.1, SQLite và localhost. Không dùng quy trình này như cam kết vận hành production. Mọi ví dụ chạy từ thư mục gốc repository, trừ khi được ghi khác.

Database chính: `backend/greenhouse.db`. Hai công cụ trong dự án: `ops/backup_sqlite.py` (SQLite Backup API, chỉ tạo đích mới) và `ops/check_secure_db.py` (kiểm tra integrity, migration head, đủ bảng, Admin active).

**Bảo mật:** Bản sao chứa dữ liệu telemetry, thông tin tài khoản và hash mật khẩu. Chỉ lưu ngoài repository; hạn chế quyền truy cập, không commit, gửi lên GitHub hoặc chia sẻ công khai. Không gửi cả `.db`, `-wal`, `-shm` qua chat.

## 1. Backup nhất quán khi Backend đang chạy

Mở PowerShell tại thư mục gốc repository; giữ `ops/backup_sqlite.py` và `ops/check_secure_db.py` có sẵn.

```powershell
$ErrorActionPreference = 'Stop'
$backupDir = Join-Path $env:USERPROFILE 'Desktop\Greenhouse-IoT-backup'
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$backup = Join-Path $backupDir ('greenhouse-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N') + '.db')
& '.\backend\.venv\Scripts\python.exe' '.\ops\backup_sqlite.py' --source '.\backend\greenhouse.db' --dest $backup
if ($LASTEXITCODE -ne 0) { throw 'BACKUP_FAILED' }
& '.\backend\.venv\Scripts\python.exe' '.\ops\check_secure_db.py' --db $backup
if ($LASTEXITCODE -ne 0) { throw 'BACKUP_PREFLIGHT_FAILED' }
Write-Host "VERIFIED_BACKUP: $backup"
```

SQLite Backup API tạo ảnh chụp nhất quán khi nguồn đang dùng WAL; **không dùng `Copy-Item` riêng file `.db` đang hoạt động** để thay thế backup API. Đích mới phải không tồn tại và nằm ngoài repository. Nếu preflight thất bại, không dùng bản sao đó để phục hồi.

## 2. Diễn tập phục hồi trên database tạm (an toàn)

Bài thử này **không chạm database chính**. Thay `$backup` bằng đường dẫn tới snapshot đã được xác minh nếu ở cửa sổ PowerShell mới.

```powershell
$ErrorActionPreference = 'Stop'
$backup = Read-Host 'Duong dan snapshot .db da duoc kiem tra'
$backup = (Resolve-Path -LiteralPath $backup).Path
$testDir = Join-Path $env:TEMP ('greenhouse-restore-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testDir -ErrorAction Stop | Out-Null
$testDb = Join-Path $testDir 'restored.db'
try {
    & '.\backend\.venv\Scripts\python.exe' '.\ops\backup_sqlite.py' --source $backup --dest $testDb
    if ($LASTEXITCODE -ne 0) { throw 'TEST_RESTORE_COPY_FAILED' }
    & '.\backend\.venv\Scripts\python.exe' '.\ops\check_secure_db.py' --db $testDb
    if ($LASTEXITCODE -ne 0) { throw 'TEST_RESTORE_PREFLIGHT_FAILED' }
    Write-Host 'TEST_RESTORE_PASS'
}
finally {
    if (Test-Path -LiteralPath $testDir) { Remove-Item -LiteralPath $testDir -Recurse -Force -ErrorAction Stop }
}
```

Có thể so sánh thêm số bản ghi của từng bảng giữa snapshot và bản phục hồi. Số bản ghi không thay thế kiểm tra toàn vẹn, nhưng giúp phát hiện lỗi quy trình sao chép.

## 3. Phục hồi database chính — CHỈ KHI CÓ SỰ CỐ THẬT

**Không chạy phần này trong nghiệm thu thông thường.** Đây là thao tác có khả năng mất toàn bộ dữ liệu phát sinh sau thời điểm backup. Chỉ thực hiện sau khi người vận hành quyết định thời điểm khôi phục và chấp nhận mất dữ liệu mới.

### 3.1. Điều kiện bắt buộc

1. Dừng Wokwi, Uvicorn/Backend bằng `Ctrl+C`, các công cụ SQLite Browser và *mọi* process có thể giữ connection tới DB. Nếu chưa chắc chắn mọi process đã ngắt kết nối, **không tiếp tục**. Docker/Mosquitto có thể chạy nhưng không được có Backend khác ghi database.
2. `Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue` phải không trả listener. Đây chỉ là một kiểm tra phụ, **không chứng minh** DB không còn bị truy cập từ chương trình khác.
3. Xác minh nguồn snapshot bằng `ops/check_secure_db.py`. Kiểm tra đã chọn đúng backup và đúng repository/nhánh. Không tự chạy Alembic trên DB hỏng.
4. Chuẩn bị **thư mục rollback mới, bên ngoài repository**, lưu nguyên bộ `greenhouse.db`, `greenhouse.db-wal`, `greenhouse.db-shm` hiện tại (các file nào tồn tại thì giữ file đó). Không sao chép riêng file DB đang mở.

### 3.2. Chuẩn bị bản phục hồi ngoài repository

Đây là bước an toàn có thể làm trước khi thay file chính. Chạy từ thư mục gốc khi Backend đã dừng:

```powershell
$ErrorActionPreference = 'Stop'
$backup = Read-Host 'Duong dan snapshot .db da xac minh'
$backup = (Resolve-Path -LiteralPath $backup).Path
$store = Join-Path $env:USERPROFILE 'Desktop\Greenhouse-IoT-backup'
if (-not (Test-Path -LiteralPath $store -PathType Container)) { throw 'BACKUP_STORE_MISSING' }
$id = [guid]::NewGuid().ToString('N')
$stageDir = Join-Path $store ('restore-stage-' + $id)
$rollbackDir = Join-Path $store ('restore-rollback-' + $id)
New-Item -ItemType Directory -Path $stageDir -ErrorAction Stop | Out-Null
$stageDb = Join-Path $stageDir 'restored.db'
& '.\backend\.venv\Scripts\python.exe' '.\ops\backup_sqlite.py' --source $backup --dest $stageDb
if ($LASTEXITCODE -ne 0) { throw 'RESTORE_STAGE_COPY_FAILED' }
& '.\backend\.venv\Scripts\python.exe' '.\ops\check_secure_db.py' --db $stageDb
if ($LASTEXITCODE -ne 0) { throw 'RESTORE_STAGE_PREFLIGHT_FAILED' }
Write-Host "RESTORE_STAGE_READY: $stageDb"
Write-Host "ROLLBACK_LOCATION: $rollbackDir"
```

### 3.3. Thay database có xác nhận thủ công

**Chỉ chạy sau khi đã hoàn tất 3.1–3.2 và kiểm tra `$stageDb`, `$rollbackDir` đúng.** Dòng lệnh này thay đổi database chính; không dùng để thử nghiệm. Nếu đang còn bất kỳ connection SQLite nào, dừng ngay và điều tra.

```powershell
$ErrorActionPreference = 'Stop'
$confirmation = Read-Host 'Nhap RESTORE-LOCAL-DB neu da dung het ket noi DB va chap nhan mat du lieu moi'
if ($confirmation -cne 'RESTORE-LOCAL-DB') { throw 'RESTORE_NOT_CONFIRMED' }
if (-not (Test-Path -LiteralPath $stageDb -PathType Leaf)) { throw 'RESTORE_STAGE_MISSING' }
$listener = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
if ($listener.Count -ne 0) { throw 'BACKEND_PORT_8000_STILL_LISTENING' }
$databaseDir = Join-Path (Get-Location).Path 'backend'
$liveDb = Join-Path $databaseDir 'greenhouse.db'
if (-not (Test-Path -LiteralPath $liveDb -PathType Leaf)) { throw 'LIVE_DB_MISSING_STOP_AND_INSPECT' }
if (Test-Path -LiteralPath $rollbackDir) { throw 'ROLLBACK_DIR_ALREADY_EXISTS' }
New-Item -ItemType Directory -Path $rollbackDir -ErrorAction Stop | Out-Null
# Bảo tồn nguyên cả DB và file WAL/SHM (nếu có); không xóa.
foreach ($name in @('greenhouse.db', 'greenhouse.db-wal', 'greenhouse.db-shm')) {
    $old = Join-Path $databaseDir $name
    if (Test-Path -LiteralPath $old) {
        Move-Item -LiteralPath $old -Destination (Join-Path $rollbackDir $name) -ErrorAction Stop
    }
}
# Sao chép file staged đã xác minh; không chép WAL/SHM cũ vào DB mới.
if (Test-Path -LiteralPath $liveDb) { throw 'LIVE_DB_NOT_EMPTY' }
Copy-Item -LiteralPath $stageDb -Destination $liveDb -ErrorAction Stop
& '.\backend\.venv\Scripts\python.exe' '.\ops\check_secure_db.py' --db $liveDb
if ($LASTEXITCODE -ne 0) { throw 'RESTORED_DB_PREFLIGHT_FAILED_STOP_DO_NOT_START_BACKEND' }
Write-Host "RESTORED_DB_PREFLIGHT_PASS; KEEP_ROLLBACK: $rollbackDir"
```

**Nếu lỗi sau khi bắt đầu di chuyển bộ DB cũ:** tuyệt đối không khởi động Backend. Giữ nguyên `$rollbackDir`, `$stageDir` và mọi file còn lại; kiểm tra vị trí từng file, bảo đảm tất cả connection đã đóng rồi mới phục hồi **cả bộ file gốc** từ rollback. Không xóa bộ rollback, không dùng `reset --hard`, không chạy migrate hay lệnh xóa WAL/SHM tùy tiện.

### 3.4. Hậu kiểm

Khởi động lại bằng `ops/start_backend_secure.ps1`, xác nhận `A672_SECURE_DB_PREFLIGHT_PASS`, health 200 và ẩn danh `/api/state` trả 401. Đăng nhập, kiểm tra vai trò và giao diện trước khi khởi động lại Wokwi. Luôn giữ backup nguồn và thư mục rollback cho đến khi toàn bộ hậu kiểm hoàn thành.

## 4. Giới hạn và ghi chú

- Preflight kiểm tra Alembic revision theo mã nguồn hiện tại, không tự nâng cấp DB.
- Bảng `audit_logs` có cấu trúc nhưng hệ thống A6 chưa triển khai ghi audit đầy đủ; dữ liệu audit có thể rỗng.
- Script `backup_sqlite.py` không ghi đè file đích và từ chối đích trong repository.
- Backup/test-restore đạt không bảo đảm việc cắt chuyển DB chính an toàn khi còn process mở.
- Lưu ít nhất một snapshot đáng tin cậy ngoài repository; không đưa backup vào Git hoặc hệ thống chia sẻ không được bảo vệ.
