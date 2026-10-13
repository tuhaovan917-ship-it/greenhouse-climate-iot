# Quy định phát triển dự án Greenhouse Climate IoT

## 1. Phân công trách nhiệm

- Người 1: `firmware/` – ESP32, PlatformIO, Wokwi, cảm biến và điều khiển tự động.
- Người 2: `backend/` – MQTT, Backend, API và giao tiếp hệ thống.
- Người 3: `dashboard/`, `database/` – Giao diện Web, cơ sở dữ liệu và kiểm thử.
- `docs/` – Tài liệu dùng chung, cả nhóm cùng đóng góp.

## 2. Quy tắc Git và GitHub

- `main` là nhánh chính, chỉ chứa mã nguồn đã kiểm tra.
- Người 1 làm việc trên `feat/esp32`.
- Người 2 làm việc trên `feat/backend`.
- Người 3 làm việc trên `feat/dashboard`.
- Không commit trực tiếp vào `main`.
- Mọi thay đổi đưa lên `main` thông qua Pull Request.
- Ít nhất một thành viên khác kiểm tra trước khi Merge.

## 3. Quy tắc viết mã nguồn

- Đặt tên biến và hàm bằng tiếng Anh, có ý nghĩa rõ ràng.
- Sử dụng `camelCase` cho biến và hàm, `PascalCase` cho tên lớp.
- Tên file và thư mục thống nhất, dễ hiểu.
- Tách mã nguồn thành các module theo chức năng.
- Viết chú thích cho những phần logic phức tạp.
- Không tự ý thay đổi cấu trúc JSON, MQTT Topic hoặc API đã được nhóm thống nhất.

## 4. Quy tắc Commit

Thông điệp commit ngắn gọn, mô tả rõ thay đổi.

Ví dụ:

- `feat: add temperature sensor reading`
- `fix: correct automatic fan control`
- `docs: update MQTT specification`
- `test: add sensor validation tests`

## 5. Quy tắc phối hợp

- Mỗi thành viên chịu trách nhiệm chính về thư mục được giao.
- Thống nhất trước khi chỉnh sửa thành phần dùng chung.
- Thống nhất định dạng dữ liệu và giao diện kết nối trước khi tích hợp.
- Tự kiểm thử chức năng trước khi tạo Pull Request.
- Báo cho nhóm khi gặp lỗi ảnh hưởng đến tiến độ hoặc các thành viên khác.
- Không commit mật khẩu, API Key, Token, file cấu hình bí mật hoặc file build không cần thiết.

## 6. Kiểm thử và tích hợp

- Mỗi thành viên tự kiểm thử phần việc của mình.
- Người 3 phụ trách tổng hợp kịch bản và kết quả kiểm thử.
- Cả ba thành viên cùng tham gia kiểm thử tích hợp ESP32 – Backend – Dashboard.
- Chỉ Merge vào `main` khi thay đổi đã được kiểm tra và không gây lỗi chức năng hiện có.