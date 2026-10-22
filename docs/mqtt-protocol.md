# Quy ước giao tiếp MQTT – Greenhouse Climate IoT

**Phiên bản:** 0.1 (bản đề xuất, cần cả nhóm xác nhận trước khi triển khai)

## 1. Nguyên tắc kiến trúc

- **ESP32 (người 1)** đọc cảm biến và trực tiếp quyết định bật/tắt quạt, bơm phun sương, đèn trong chế độ **AUTO**. ESP32 cũng xử lý **MANUAL** và kiểm tra an toàn **FAILSAFE**.
- **Backend (người 2)** giao tiếp với ESP32 qua MQTT, lưu/chuyển tiếp dữ liệu và lệnh, cung cấp API cho Dashboard. Backend **không quyết định bật/tắt thiết bị thay ESP32 trong AUTO**.
- **Dashboard và Database (người 3)** hiển thị dữ liệu, gửi yêu cầu đến Backend, lưu/xem lịch sử theo phân công. Dashboard **không kết nối trực tiếp đến ESP32**.
- Khi mất mạng, ESP32 tiếp tục đọc cảm biến, điều khiển cục bộ theo cấu hình đã lưu và ưu tiên quy tắc an toàn; khi kết nối lại thì công bố trạng thái thực tế.

## 2. MQTT topics

Mã nhà kính giả lập: `01`; thống nhất tiền tố `greenhouse/01/`.

| Topic | Bên gửi → bên nhận | Mục đích | QoS đề xuất | Retain |
|---|---|---|---:|---|
| `greenhouse/01/telemetry` | ESP32 → Backend | Dữ liệu đo định kỳ (ví dụ 5 giây/lần) | 0 | Không |
| `greenhouse/01/state` | ESP32 → Backend | Trạng thái **thực tế** của thiết bị và phản hồi lệnh | 1 | Có |
| `greenhouse/01/status` | ESP32/MQTT Broker → Backend | Online/offline, hỗ trợ Last Will (LWT) | 1 | Có |
| `greenhouse/01/command` | Backend → ESP32 | Yêu cầu điều khiển MANUAL | 1 | **Không** |
| `greenhouse/01/config` | Backend → ESP32 | Thay đổi AUTO/MANUAL và ngưỡng | 1 | Không |

> Lưu ý: MQTT QoS 1 có thể phát trùng bản tin. ESP32 xử lý lệnh theo `commandId` để tránh thực hiện trùng. Không dùng retained message cho `command` để tránh nhận lại lệnh cũ sau khi kết nối lại.

## 3. Định dạng JSON (bản đề xuất)

### 3.1. ESP32 gửi `telemetry`

```json
{
  "deviceId": "greenhouse-01",
  "temperatureC": 30.5,
  "humidityPct": 65.2,
  "lightLux": 450,
  "waterOk": true
}
```

- `temperatureC`: số thực, độ C; `humidityPct`: số thực, 0–100%; `lightLux`: số thực, lux, >= 0; `waterOk`: boolean (`true` nghĩa là **còn nước**).
- Dữ liệu đo không hợp lệ gửi `null` hoặc trạng thái lỗi đã thống nhất; **không** gửi `NaN` trong JSON. Backend gắn thời điểm nhận để lưu lịch sử.

### 3.2. ESP32 gửi `state`

```json
{
  "deviceId": "greenhouse-01",
  "mode": "AUTO",
  "fan": true,
  "mist": false,
  "lamp": false,
  "failsafeActive": false,
  "lastCommandId": null,
  "lastCommandResult": null
}
```

- `mode`: `AUTO` hoặc `MANUAL`; `failsafeActive` là **cơ chế an toàn ưu tiên cao nhất**, có thể ghi đè lệnh ở cả hai chế độ.
- `lastCommandResult`: `APPLIED`, `REJECTED` hoặc `null`. Nếu từ chối, nên bổ sung `reason`, ví dụ `NOT_MANUAL_MODE` hoặc `NO_WATER`.
- Publish khi khởi động/kết nối lại, sau khi thay đổi trạng thái thiết bị/chế độ hoặc xử lý lệnh. Dashboard hiển thị **trạng thái này**, không tự đoán thiết bị đã bật chỉ vì vừa gửi yêu cầu.

### 3.3. ESP32 gửi `status` (và cấu hình LWT)

Bản tin sau khi kết nối:

```json
{"online": true}
```

Last Will do MQTT Broker phát khi mất kết nối bất thường:

```json
{"online": false}
```

Cả hai bản tin dùng `retain=true`. Backend có thể bổ sung cơ chế phát hiện quá hạn dữ liệu để tránh coi thiết bị là online khi trạng thái cũ không còn đáng tin.

### 3.4. Backend gửi `command`

```json
{
  "commandId": "cmd-0001",
  "device": "fan",
  "on": true
}
```

- `device`: `fan`, `mist`, `lamp`; `on`: boolean.
- Chỉ thực thi lệnh nếu chế độ đang là `MANUAL` và không vi phạm kiểm tra an toàn. Phản hồi bằng topic `state` kèm `lastCommandId` và `lastCommandResult`.
- Ví dụ: bồn hết nước → lệnh `mist=true` phải bị từ chối, bơm vẫn tắt.

### 3.5. Backend gửi `config`

```json
{
  "mode": "AUTO",
  "tempOnC": 30,
  "tempOffC": 28,
  "humidityOnPct": 60,
  "humidityOffPct": 70,
  "lightOnLux": 300,
  "lightOffLux": 500
}
```

- Các ngưỡng ở trên **chỉ là ví dụ để kiểm thử**, không phải ngưỡng tối ưu đã được xác nhận cho cây trồng.
- Điều kiện hợp lệ: `tempOnC > tempOffC`, `humidityOnPct < humidityOffPct`, `lightOnLux < lightOffLux`.
- Dùng hai ngưỡng bật/tắt (*hysteresis*) để tránh thiết bị đóng/ngắt liên tục.
- ESP32 kiểm tra cấu hình rồi lưu vào bộ nhớ không mất điện (ví dụ Preferences/NVS), công bố trạng thái sau khi áp dụng; khi khởi động lại tiếp tục dùng cấu hình đã lưu.

## 4. Quy tắc vận hành và an toàn

1. **AUTO:** nhiệt độ cao → bật quạt; độ ẩm thấp **và còn nước** → bật phun sương; ánh sáng yếu → bật đèn. Tắt thiết bị tại ngưỡng tắt tương ứng.
2. **MANUAL:** chỉ tiếp nhận yêu cầu qua `command`; thiết bị vẫn bị giới hạn bởi quy tắc an toàn.
3. **FAILSAFE:** hết nước hoặc trạng thái cảm biến nước không đáng tin → **không cho bơm chạy**; báo trạng thái/cảnh báo khi có kết nối.
4. **Mất Wi-Fi/MQTT:** tiếp tục điều khiển cục bộ; không chờ MQTT mới điều khiển, tự động thử kết nối lại. Phương án đề xuất để cả nhóm xác nhận: tạm dùng AUTO cục bộ khi mất kết nối nếu trước đó đang MANUAL.
5. **Kết nối lại:** ESP32 publish `status=online`, `state` thực tế và `telemetry` mới; không tự thực thi lệnh MANUAL cũ.

## 5. Trách nhiệm tích hợp

- **Người 1:** triển khai publish `telemetry/state/status`, subscribe `command/config`, kiểm tra giá trị và an toàn, lưu cấu hình trên ESP32.
- **Người 2:** thiết lập Broker và xác thực, subscribe dữ liệu từ ESP32, chuyển yêu cầu API thành `command/config`, chuyển tiếp trạng thái phản hồi, phối hợp với người 3 để ghi cơ sở dữ liệu.
- **Người 3:** dùng Backend API/WebSocket thay vì kết nối trực tiếp MQTT; thiết kế dữ liệu lưu trữ, biểu đồ và giao diện trạng thái; hỗ trợ kiểm thử end-to-end.

## 6. Bảo mật và việc cần xác nhận

- Theo báo cáo giai đoạn 2, hệ thống hướng tới **MQTT over TLS** và **HTTPS/WebSocket**; cần chọn MQTT Broker/cổng và cấu hình tương ứng trước khi viết mã kết nối.
- Không commit mật khẩu Wi-Fi, MQTT, khóa truy cập; chỉ commit file cấu hình mẫu không chứa bí mật.
- **Cả nhóm cần duyệt trước khi coi đây là chuẩn cuối cùng:** (1) tên trường/topic; (2) ngưỡng minh họa; (3) hành vi khi mất kết nối đang MANUAL; (4) Broker và cơ chế TLS; (5) cách lưu/chuyển tiếp dữ liệu của Backend–Database.

**Chưa thuộc phạm vi tài liệu này:** đường dẫn và định dạng REST API/WebSocket giữa Backend và Dashboard; sẽ thống nhất trong `docs/api-contract.md` sau.
