# Backend & MQTT - Greenhouse Climate IoT

Trung tâm xu ly gia tiep giua **ESP32** va **Web Dashboard**: subscribe du lieu cam bien
tu MQTT Broker, luu vao database, cung cap REST API + WebSocket cho Dashboard, va gui
lenh/cai dat xuong ESP32.

| Thanh phan | Chon | Ghi chu |
|---|---|---|
| Framework | Python 3.11 + FastAPI + Uvicorn | Swagger tai `/docs` |
| MQTT client | `paho-mqtt 2.x` | sub `telemetry/state/status`, pub `command/config` |
| ORM | `SQLModel` (SQLAlchemy 2.0) | snake_case trong DB, camelCase ra API |
| Database | SQLite (WAL) mac dinh | doi `DATABASE_URL` sang PostgreSQL khi can |
| Broker | Eclipse Mosquitto 2.x (Docker) | `mqtt://:1883`, ho tro `mqtts://:8883` |

Hop dong API: [`docs/api-contract.md`](../docs/api-contract.md) **v0.2.2**.
MQTT payload: [`docs/mqtt-protocol.md`](../docs/mqtt-protocol.md) (nhanh `feat/esp32`).
Schema DB do **Nguyen 3** so huu trong `database/` (`SCHEMA.md` v0.2 + Alembic).

---

## 1. Chay nhanh

```bash
cd backend

# 1) Tao moi truong
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 2) Cai dependency
pip install -r requirements.txt

# 3) Cau hinh
copy .env.example .env          # Windows
# cp .env.example .env          # Linux/macOS

# 4) Bat MQTT Broker
docker compose up -d

# 5) Chay Backend
python -m uvicorn app.main:app --reload --port 8000
```

Mo `http://localhost:8000/docs` de xem Swagger.

### Voi PostgreSQL thay SQLite

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/greenhouse
```
Khong doi code. Chi can them `psycopg[binary]` vao `requirements.txt`.

### Voi TLS

```env
MQTT_URL=mqtts://<broker-host>:8883
MQTT_CA_FILE=./certs/ca.crt
MQTT_USERNAME=<user>
MQTT_PASSWORD=<pass>
```
Broker: bat listener `8883` trong `mosquitto/mosquitto.conf` (phan comment san).

---

## 2. Bat MQTT Broker

```bash
docker compose up -d          # Eclipse Mosquitto 2.x, 1883
docker compose logs -f
docker compose down
```

Anh/chay khong co Docker? Cai Mosquitto truc tiep va doi `MQTT_URL`.
Backend van chay duoc khi broker chua san: `/api/health` tra `mqttConnected: false`
va moi thiet bi se bao `offline`.

---

## 3. Demo khong can ESP32 that

`demo_esp32_mock.py` dong vai ESP32 day du: publish telemetry/state/status (co Last Will),
subscribe `command` va `config`, tra `APPLIED` / `REJECTED` theo dung quy tac failsafe.

```bash
# Terminal 1 - Broker
docker compose up -d

# Terminal 2 - Backend
python -m uvicorn app.main:app --port 8000

# Terminal 3 - Thiet bi ao
python demo_esp32_mock.py
```

Cac bien theo kich ban demo:

| Lenh | Dung de demo |
|---|---|
| `python demo_esp32_mock.py` | Luong binh thuong, AUTO tu dong |
| `python demo_esp32_mock.py --no-water` | **KB2**: bom het nuoc, lenh `mist` bi `REJECTED/NO_WATER` |
| `python demo_esp32_mock.py --sensor-fault` | Cam bien loi, telemetry `null`, canh bao `SENSOR_FAULT` |
| `python demo_esp32_mock.py --offline-after 30` | Mat ket noi, LWT bat `offline`, canh bao `OFFLINE` |
| `python demo_esp32_mock.py --period 2` | Telemetry nhanh hon de test bieu do |

**KB1** (lenh hop le): Dashboard chuyen `MANUAL` -> POST `/api/commands {device:"fan", on:true}`
-> ESP32 tra `APPLIED`, quat bat, WebSocket day `state` moi.

**KB2** (dung failsafe): `--no-water` -> lenh `mist` bi `REJECTED` voi `reason: NO_WATER`,
bom van tat, Dashboard hien canh bao do.

---

## 4. Endpoint tong quan

| Method | Duong dan | Y nghia |
|---|---|---|
| GET | `/api/health` | Backend + MQTT + DB con song khong |
| GET | `/api/telemetry?bucket=raw\|1m\|5m\|1h` | Lich su, envelope `{bucket, data}` |
| GET | `/api/telemetry/latest` | Ban tin moi nhat |
| GET | `/api/state` | Trang thai thuc te + `online` + `lastSeenAt` |
| POST | `/api/commands` | Gui lenh MANUAL, tra `202 {commandId}` |
| GET | `/api/commands` | Lich su lenh `PENDING/APPLIED/REJECTED/TIMEOUT` |
| GET | `/api/config` | Cau hinh mong muon hien tai |
| POST | `/api/config` | Cap nhat cau hinh, tra `202 PUBLISHED` |
| GET | `/api/alerts?active=&code=` | Lich su + canh bao dang active |
| WS | `/ws?deviceId=greenhouse-01` | Push `telemetry`, `state`, `command_result`, `alert` |

Chi tiet request/response va TypeScript types: `docs/api-contract.md` muc 2-4.

---

## 5. Cau truc thu muc

```text
backend/
├── app/
│   ├── main.py            # FastAPI app, lifespan, router, CORS
│   ├── config.py          # Doc bien moi truong (.env)
│   ├── database.py        # Engine, session, WAL + foreign_keys cho SQLite
│   ├── models.py          # SQLModel table models (theo database/SCHEMA.md)
│   ├── schemas.py         # Pydantic API schemas (camelCase) + ISO8601 Z
│   ├── mqtt_client.py     # paho-mqtt: subscribe/publish, TLS, reconnect
│   ├── ws_manager.py      # Quan ly ket noi WebSocket theo thiet bi
│   ├── routers/           # health, telemetry, state, commands, config, alerts, ws
│   └── services/          # ingest, telemetry (bucket), commands, alerts, state
├── docker-compose.yml     # Mosquitto cho demo
├── mosquitto/mosquitto.conf
├── demo_esp32_mock.py     # Thiet bi ao cho demo
├── requirements.txt
├── .env.example
└── .env                   # KHONG commit
```

---

## 6. Tu kiem tra truoc khi demo

Khong can them thu vien gi - dung Swagger + thiet bi ao:

| Buoc | Cach | Mong doi |
|---|---|---|
| 1 | `GET /api/health` | `mqttConnected: true`, `db: "ok"` |
| 2 | `python demo_esp32_mock.py` | Terminal in `telemetry` moi 5s |
| 3 | `GET /api/telemetry/latest` | Gia tri cam bien, `receivedAt` ket thuc bang `Z` |
| 4 | `GET /api/telemetry?bucket=1m` | Envelope `{bucket, data}`, co `sampleCount` |
| 5 | `GET /api/state` | `online: true`, `lastSeenAt` duoc dien |
| 6 | `POST /api/config` -> `MANUAL` | `202 {"status":"PUBLISHED", ...}` |
| 7 | `POST /api/commands {"device":"fan","on":true}` | `202 {"status":"PENDING"}` roi `APPLIED` |
| 8 | Bat lai mock voi `--no-water` | Canh bao `NO_WATER` `CRITICAL`, lenh `mist` bi `REJECTED`, bom van `false` |
| 9 | `GET /api/commands` | `reason: "NO_WATER"` duoc giu nguyen |

Mo `http://localhost:8000/docs` de xem va go truc tiep cac request tren.

## 7. Vai tro va phan cong

Theo `docs/CONTRIBUTING.md` va `database/README.md`:

- **Backend (`app/models.py`)**: SQLModel table models, engine, session, `DATABASE_URL`,
  insert/upsert/query, xuat REST/WS dung hop dong.
- **Nguyen 3 (`database/`)**: thiet ke schema, Alembic migration, `alembic upgrade head`.

`app/models.py` la **single source** cho Alembic metadata, nen doi bang/cot o day
thi phai bao cao de Nguyen 3 sinh migration tuong ung. Khong sua migration da dung chung.

Luu y: `create_all` chi dung cho test/demo (`AUTO_CREATE_TABLES=1`); database chinh
luon chay `alembic upgrade head`.

---

## 8. Bien moi truong

| Bien | Mac dinh | Y nghia |
|---|---|---|
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Dia chi server |
| `DEVICE_ID` | `greenhouse-01` | Thiet bi mac dinh |
| `API_KEY` | rong | Rong = khong kiem tra; dat gia tri = yeu cau `X-API-Key` khi mo LAN |
| `MQTT_URL` | `mqtt://localhost:1883` | Broker; `mqtts://` cho TLS |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | rong | Xac thuc broker |
| `MQTT_CA_FILE` | rong | CA cho TLS |
| `MQTT_ENABLED` | `1` | `0` = chi chay REST/WS, khong ket noi broker |
| `COMMAND_TIMEOUT_S` | `5` | Khong phan hoi -> `TIMEOUT` |
| `DEVICE_TIMEOUT_S` | `15` | Khong co tin nhan -> `online=false` |
| `DATABASE_URL` | `sqlite:///./greenhouse.db` | SQLite hoac PostgreSQL |
| `MAX_SCAN_ROWS` | `20000` | Vuot qua -> `GET /api/telemetry` tra 400 thay vi cat bom |
| `AUTO_CREATE_TABLES` | `0` | Chi dev/demo, thay cho Alembic |
| `LOG_LEVEL` | `INFO` | `DEBUG` de in tung tin nhan MQTT nhan duoc |

Khong commit `.env`, database runtime (`*.db`, `*.db-wal`, `*.db-shm`) hay `certs/`.

---

## 9. Ghi chu ky thuat

- **Khong giu transaction khi gui WebSocket**: ghi DB, commit, roi moi broadcast.
- **Race `device_states`**: `status` va `state` co the den cung luc, nen dung
  `INSERT ... ON CONFLICT DO UPDATE` (`upsertDeviceState`) thay vi "doc roi insert".
- **Alert dedup**: khoa thread trong `AlertService`, cung `device_id + code` thi cap nhat
  `lastSeenAt` thay vi them dong moi; het dieu kien thi dong alert.
- **Luong MQTT**: callback paho chay tren network thread nen lenh duoc `run_coroutine_threadsafe`
  len loop, khong duoc goi coroutine truc tiep.
- **Bucket**: tong hop bang Python de chay giong nhau tren SQLite va PostgreSQL
  (`strftime` vs `date_trunc` la khac nhau); can bucket theo UTC epoch.
- **`limit` luon lay phan moi nhat**: `order` chi quyet dinh thu tu tra ve, nen `order=asc`
  van ve duoc N mau moi nhat dung thu tu khong phai N mau cuoi cung trong khoang.
- **PENDING chi la REST**: WebSocket `command_result` chi nhan `APPLIED|REJECTED|TIMEOUT`.
- **`reason` khong bi xoa**: ESP32 publish lai `state` dinh ky va thuong khong kem
  `reason`, nen Backend chi ghi de khi tin moi co `reason` - ly do tu choi duoc giu lai.

---

## 10. Han ch muc v0.2

- Chua co xac thuc nguoi dung (JWT); khi mo LAN dung `API_KEY` cho API ghi.
- `POST /api/config` chi xac nhan `PUBLISHED`, chua co `configId` de ESP32 ack.
- Chua co bang aggregate; bucket duoc tinh luc query.
- Chua co retention policy cho telemetry.

## Du an

Greenhouse Climate IoT - Backend & MQTT, Module 2.
