# Sending Scan Data to Azure IoT Hub Using MQTT

This document is the **single source of truth** for how RFID scan data is sent from the Nexus RFID Reader application to **Azure IoT Hub** over **MQTT**, and how it is **stored in PostgreSQL** by an **Azure Function** written in **C#**. It covers the full path, why each step exists, and the exact steps and configuration required.

---

## 1. High-Level Architecture

```
┌──────────────────┐     ┌─────────────────────┐     ┌──────────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  RFID Reader     │     │  Nexus App          │     │  Azure IoT Service       │     │  Azure IoT Hub       │     │  Azure Function      │     │  PostgreSQL          │
│  (hardware)      │────▶│  (overview screen)  │────▶│  (separate process)      │────▶│  (cloud)            │────▶│  (C#)                │────▶│  (persistent store)  │
│                  │     │  IoTClient          │     │  IoTHubDeviceClient      │     │  Device-to-cloud    │     │  Event-driven       │     │  Scans table(s)      │
└──────────────────┘     │  Unix socket        │     │  send_message() → MQTT   │     │  → routes / events  │     │  → parse & insert    │     └─────────────────────┘
                         └─────────────────────┘     └──────────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

**Flow in one sentence:** The RFID hardware produces tag reads; the main app builds scan records and sends them over a **Unix socket** to a **separate Azure IoT service process**, which batches them and publishes to **Azure IoT Hub** over **MQTT**; an **Azure Function (C#)** consumes those messages and **persists the scan data to PostgreSQL**.

---

## 2. Why This Design?

| Decision | Reason |
|----------|--------|
| **Separate IoT service process** | The main app (GUI, RFID, GPS) can run without root; the IoT service runs as a systemd service, survives app restarts, and owns the single MQTT connection and credentials. |
| **Unix socket** (`/var/run/nexus-iot.sock`) | Local, low-latency IPC; no network port; the app does not need Azure credentials—only the service does. |
| **Batching scans** | Fewer MQTT publishes reduce connection load and cost; configurable `batchSize` and `batchIntervalSeconds` balance latency vs. efficiency. |
| **DPS (Device Provisioning Service)** | Devices get a **derived symmetric key** from a group key; no per-device key distribution. One enrollment group in DPS, many devices. |
| **MQTT** | Azure IoT Hub’s recommended protocol for devices: efficient, bidirectional; the Python SDK uses MQTT under the hood when you call `send_message()`. |

---

## 3. End-to-End Data Path (Step by Step)

### 3.1 RFID scan to scan record (application)

1. **Where:** `screens/overview.py` — RFID tag events are received and, after filters (speed, RSSI, etc.), `_send_scan_to_iot()` is called.
2. **What:** A **scan record** (dict) is built with:
   - `siteId`, `tagName` (EPC), `latitude`, `longitude`, `speed`, `deviceId`, `antenna`, `barrier` (bearing), `rssi`.
3. **Why:** This shape matches the backend/C# Azure Function expectations and includes everything needed for location and analytics.

### 3.2 Application → IoT service (Unix socket)

1. **Where:** `utils/iot_client.py` — `IoTClient.send_scan(scan_record)`.
2. **What:** The client connects to `SOCKET_PATH = '/var/run/nexus-iot.sock'` and sends one **JSON line per message**:  
   `{"type": "scan", "data": <scan_record>}\n`
3. **Why:** Newline-delimited JSON allows the service to read line-by-line and parse one message at a time. The `type` field lets the service distinguish scans from other message types in the future.

### 3.3 IoT service receives and batches

1. **Where:** `Azure-IoT-Connection/iot_service.py` — `_handle_client()` → `_process_message()`.
2. **What:** For each `type == "scan"` message, the service appends `data` to an in-memory **scan buffer**. When either:
   - the buffer length ≥ `batchSize`, or  
   - `batchIntervalSeconds` has elapsed since the first item in the buffer,  
   the service calls `_flush_scan_batch()`.
3. **Why:** Sending one MQTT message per scan would be expensive and noisy; batching reduces message count and keeps throughput high.

### 3.4 IoT service → Azure IoT Hub (MQTT)

1. **Where:** `Azure-IoT-Connection/iot_service.py` — `_flush_scan_batch()` builds a payload and calls `_send_message_safe()` → `self.client.send_message(message_json)`.
2. **What:** The payload is a single JSON string, e.g.:
   ```json
   {"type": "scan_batch", "scans": [<scan1>, <scan2>, ...]}
   ```
   The **Azure IoT Device SDK** (`azure.iot.device.IoTHubDeviceClient`) sends this as a **device-to-cloud (D2C) message** over **MQTT** to the IoT Hub.
3. **Why:** IoT Hub exposes MQTT (and AMQP/HTTPS); the SDK handles MQTT connection, TLS, and reconnection. Your code only calls `send_message()`; the transport is MQTT by default.

### 3.5 Azure IoT Hub

- The hub receives the MQTT publish on the device’s D2C topic.
- Messages can be consumed by **IoT Hub routes** (e.g. to Event Hubs, Service Bus, Blob), **Stream Analytics**, or **Azure Functions**. In this project, an **Azure Function** is the consumer that stores scan data (see 3.6).

### 3.6 Azure Function (C#) → PostgreSQL

1. **What:** An **Azure Function** (developed in **C#**) is triggered by device-to-cloud messages from IoT Hub (e.g. via an **IoT Hub route** to an Event Hub–compatible endpoint or a built-in Event Hub endpoint, or via an IoT Hub–triggered function). The function parses the incoming JSON (`type: "scan_batch"`, `scans` array) and **writes each scan (or the batch) into a PostgreSQL database**.
2. **Why C#:** The backend and API layer for Nexus Locate are C#-based; using C# for the function keeps tooling, types, and team expertise consistent and allows sharing DTOs/validation with the rest of the backend.
3. **Why Azure Function:** Serverless, event-driven processing: each message (or batch) triggers one execution; no always-on VM; scaling and billing are handled by Azure.
4. **Why PostgreSQL:** Relational store for scans (and related entities) with strong consistency, queryability, and integration with existing C# backends (e.g. Entity Framework, Npgsql). Scan records map to table rows (e.g. site, tag, lat/lon, speed, device, antenna, barrier, rssi, timestamp).

**End-to-end:** Device → MQTT → IoT Hub → (route) → Azure Function (C#) → PostgreSQL. The scan record shape produced by the app (see 3.1) is designed to match what the C# function expects and writes to PostgreSQL.

---

## 4. Required Detailed Steps (Setup)

### 4.1 Azure cloud prerequisites

| Step | What to do | Why |
|------|------------|-----|
| 1 | Create an **Azure IoT Hub** (any tier; Basic supports D2C). | Hub is the MQTT endpoint and identity store for devices. |
| 2 | Create a **Device Provisioning Service (DPS)** and link it to the IoT Hub. | DPS assigns devices to the hub and issues credentials without pre-registering each device in the hub. |
| 3 | In DPS, create an **Enrollment Group** (e.g. symmetric key). Note: **ID Scope** and **Primary Key** (group key). | Group enrollment lets you derive per-device keys from one key; no need to paste keys on each device. |
| 4 | (Optional) Register the device in the hub or use DPS to auto-create. | DPS can create the device in the hub on first provisioning. |

**Why DPS:** One group key + device ID (e.g. serial) gives a derived symmetric key per device. No manual key per device in the portal.

### 4.1.1 How to get Azure IoT Hub and DPS credentials (Azure Portal)

Follow these steps in the **Azure Portal** ([https://portal.azure.com](https://portal.azure.com)) to obtain the values you need for device setup: **ID Scope** and **Group key (Primary Key)**. You need an Azure subscription and rights to create or use IoT Hub and DPS resources.

---

#### A. Create or use an IoT Hub

1. In the Azure Portal search bar (top), type **IoT Hub** and select **IoT Hub** under *Services*.
2. Click **+ Create** (or open an existing hub).
3. **Subscription** and **Resource group**: Choose or create one (e.g. create a resource group `rg-nexus-iot`).
4. **Region**: Choose a region (e.g. East US).
5. **IoT Hub name**: Enter a globally unique name (e.g. `hub-nexus-locate`). Click **Next: Networking** then **Next: Management**, then **Review + create** → **Create**.
6. Wait for deployment to finish. You do **not** need to copy the IoT Hub connection string for the device; the device will get the hub via DPS. The hub is only needed so DPS can link to it.

---

#### B. Create Device Provisioning Service (DPS) and link it to the hub

1. In the portal search bar, type **Device Provisioning Service** and select **Device Provisioning Services** under *Services*.
2. Click **+ Create**.
3. **Subscription** and **Resource group**: Use the same as the IoT Hub (e.g. `rg-nexus-iot`).
4. **Name**: Enter a name (e.g. `dps-nexus-locate`).
5. **Region**: Same region as the hub is recommended. Click **Review + create** → **Create**.
6. After deployment, open the new DPS resource (click **Go to resource** or find it in the resource group).
7. In the left menu under *Settings*, click **Linked IoT hubs**.
8. Click **+ Add**.
9. **Subscription**: Select your subscription. **IoT Hub**: Select the IoT Hub you created (e.g. `hub-nexus-locate`). **Access policy**: Choose **iothubowner** (or a policy that has *Registry write* so DPS can create devices). Click **Save**.

---

#### C. Copy the ID Scope (required for device config)

1. Stay in your **Device Provisioning Service** resource.
2. In the left menu, click **Overview**.
3. On the Overview page, find **ID Scope**. It looks like `0neXXXXXXXX` (alphanumeric).
4. Click the **Copy** icon next to **ID Scope** and save it somewhere safe (e.g. in `env.json` as `idScope`).  
   **You will use this value as `idScope` in device setup.**

---

#### D. Create an Enrollment Group and get the Primary Key (group key)

1. In the same DPS resource, in the left menu under *Settings*, click **Manage enrollments**.
2. Click **+ Add enrollment group** at the top.
3. **Group name**: Enter a name (e.g. `nexus-devices`).
4. **Attestation type**: Select **Symmetric Key**.
5. **Auto-generate keys**: Leave **checked** (both Primary and Secondary key will be generated).
6. **IoT Hub device options** (optional): You can set **IoT Hub** to your hub and enable **Enable entry** so that new devices are created in the hub when they first provision.
7. Click **Save**.
8. The new enrollment group appears in the list. Click the **group name** (e.g. `nexus-devices`) to open it.
9. On the enrollment group page you will see:
   - **Primary Key** (long Base64 string)
   - **Secondary Key** (optional, for key rotation)
10. Click **Copy** next to **Primary Key** and store it securely.  
    **You will use this value as `group_key` in `env.json`; the device setup script derives a per-device key from it.**

**Important:** Treat the Primary Key as a secret. Do not commit it to source control; use `env.json` (or similar) and restrict file permissions.

---

#### E. Summary: values to use on the device

| Value | Where you got it | Used as |
|-------|------------------|--------|
| **ID Scope** | DPS → Overview → ID Scope | `idScope` in `env.json` / device config |
| **Primary Key** (enrollment group) | DPS → Manage enrollments → [your group] → Primary Key | `group_key` in `env.json`; device setup derives the per-device symmetric key from this |

Optional (for OTA/updates): **Storage account**, **container name**, and **SAS token** for the blob container where updates are stored—configured separately and added to `env.json` if you use the Azure IoT service’s update feature.

---

### 4.2 Device credentials (derived key)

- **Group key (primary key):** From the DPS enrollment group (Base64).
- **Registration ID:** Usually the device serial (e.g. from `/proc/cpuinfo` on Linux).
- **Derived key:** `HMAC-SHA256(group_key_bytes, registration_id)` then Base64.  
  Implemented in `Azure-IoT-Connection/device_setup.py` via `compute_derived_key()`.

**Why symmetric key:** Simple and supported everywhere. For higher security, use X.509 (DPS and SDK support it).

### 4.3 Device configuration file

- **Path:** `/etc/azureiotpnp/provisioning_config.json`
- **Permissions:** `600` (root only).
- **Contents (minimal; secrets encrypted at rest):**
  - `globalEndpoint`: `"global.azure-devices-provisioning.net"`
  - `idScopeEnc` / `symmetricKeyEnc`: encrypted values (key derived from `/etc/machine-id`); or legacy plain `idScope` / `symmetricKey` for backward compatibility
  - `registrationId`: device ID (e.g. serial)
  - `tags.nexusLocate`: e.g. `siteName`, `truckNumber`, `deviceSerial` (optional)
  - `batchSize` / `batchIntervalSeconds`: optional; service defaults are 10 and 5
  - `deviceUpdate`: optional; only present if OTA via `download.py` is configured  
  The **cryptography** package is required for encryption/decryption; `device_setup.py` writes encrypted credentials and `iot_service.py` decrypts on load.

**Why file-based:** The IoT service runs as a system service and must read credentials and batching settings from a fixed path without user interaction.

### 4.4 Provisioning (one-time per device)

1. Run **device setup** so that `provisioning_config.json` is created and the derived key is computed:
   - `env.json` (or prompts) supplies: `group_key`, `idScope`, and optionally storage/site/truck. The group key is used only to derive the device key and is never written to the device config.
   - `device_setup.py` writes `provisioning_config.json` with only the minimal runtime credentials (no group key; optional `deviceUpdate` only if OTA is configured).
2. **Why:** Provisioning uses DPS to get `assigned_hub` and `device_id`; the service then connects to that hub with the same symmetric key.

### 4.5 IoT service process

1. **Install:** Copy `iot_service.py`, `device_setup.py`, `download.py` to `/opt/azure-iot/`, install `azure-iot-device` (e.g. `pip3 install azure-iot-device`).
2. **Systemd:** Install `azure-iot.service` so the service starts on boot and restarts on failure.
3. **Start:** `sudo systemctl start azure-iot.service`.

**Why systemd:** Persistent connection to IoT Hub, restart on failure, and the Unix socket is created when the service starts so the app can send scans even after reboot.

### 4.6 Main application

- The app only needs to know the **socket path** (`/var/run/nexus-iot.sock`). No Azure credentials in the app.
- On each relevant RFID read (after filters), call `iot_client.send_scan(scan_record)`.
- If the IoT service is not running, `send_scan` returns `False`; the app can log and continue.

**Why no Azure in app:** Security and simplicity: credentials live in one place (IoT service + config file), and the app stays agnostic of MQTT and Azure.

---

## 5. Message Formats (Reference)

### 5.1 App → IoT service (Unix socket)

- One message per line (newline-delimited JSON).
- Single scan:
  ```json
  {"type": "scan", "data": {"siteId": "...", "tagName": "EPC...", "latitude": 0.0, "longitude": 0.0, "speed": 0.0, "deviceId": "...", "antenna": "1", "barrier": 0.0, "rssi": "0"}}
  ```

### 5.2 IoT service → Azure IoT Hub (MQTT body)

- One JSON object per MQTT publish (batch):
  ```json
  {"type": "scan_batch", "scans": [{ ...scan1... }, { ...scan2... }]}
  ```
- Other event types (same transport): e.g. `{"event": "device_connected", "deviceId": "...", ...}`, `{"event": "heartbeat", ...}`.

### 5.3 MQTT details (SDK)

- The **Azure IoT Device SDK for Python** uses **MQTT** (or MQTT over WebSocket) by default.
- `client.send_message(message_json)` publishes to the standard **device-to-cloud** topic; the hub receives it and can route it.
- **TLS:** The SDK uses TLS to the hub; no extra MQTT configuration is required in your code.

---

## 6. Reliability and Behavior

| Mechanism | Where | Why |
|-----------|--------|-----|
| **Reconnect** | `_ensure_connected()`, `_check_connection_health()` | Network or hub restarts; the service reconnects and continues. |
| **Retries** | `_send_message_safe()` (e.g. 3 attempts) | Transient failures; after failure the service may reconnect and retry. |
| **Batch re-queue** | `_flush_scan_batch()` on send failure | Failed batch is put back at the front of the buffer so scans are not dropped. |
| **Heartbeat** | Periodic `event: heartbeat` message | Backend can detect alive devices even when no scans are sent. |
| **Connection check** | Periodic twin or health check | Detects stale or dropped MQTT connection so the service can reconnect. |

---

## 7. Security Summary

- **Credentials:** Stored only in `/etc/azureiotpnp/provisioning_config.json` with mode `600`.
- **Transport:** TLS to Azure (handled by the SDK over MQTT).
- **App:** No Azure secrets; only talks to the local Unix socket.
- **Symmetric key:** Derived per device from the DPS group key; compromise of one device does not expose the group key if the derivation is correct.

---

## 8. Troubleshooting

| Symptom | Check | Reason |
|---------|--------|--------|
| Scans not reaching the hub | IoT service status: `systemctl status azure-iot.service` | Service must be running to create the socket and hold the MQTT connection. |
| Socket missing | `ls -la /var/run/nexus-iot.sock` | Created by the IoT service on start; if missing, the service failed or is stopped. |
| Provisioning fails | DPS ID Scope, group key, registration ID | Wrong scope/key or ID format prevents DPS from assigning the hub. |
| Connection drops | Logs: `journalctl -u azure-iot.service -f` | Network, firewall, or throttling; service should reconnect automatically. |
| No batches sent | `batchSize` and `batchIntervalSeconds` in config | Buffer flushes only when size or interval is reached; ensure config is loaded. |

---

## 9. File and Code Reference

| Purpose | Path |
|---------|------|
| App-side client (socket) | `utils/iot_client.py` |
| Scan construction and send trigger | `screens/overview.py` (`_send_scan_to_iot`, `IoTClient.send_scan`) |
| IoT service (MQTT, batching, socket server) | `Azure-IoT-Connection/iot_service.py` |
| Device config generation | `Azure-IoT-Connection/device_setup.py` |
| Provisioning config template | `Azure-IoT-Connection/provisioning_config_template.json` |
| Service setup and usage | `Azure-IoT-Connection/README.md` |
| **Backend: scan persistence** | **Azure Function (C#)** – separate project/service; consumes IoT Hub messages and writes scan data to **PostgreSQL**. |

---

## 10. Summary Checklist

- [ ] Azure: IoT Hub + DPS created; DPS linked to hub; enrollment group (symmetric key) created; ID Scope and group key noted.
- [ ] Device: `provisioning_config.json` present at `/etc/azureiotpnp/` with correct `idScope`, `registrationId`, derived `symmetricKey`, and optional `batchSize` / `batchIntervalSeconds`.
- [ ] IoT service: Installed under `/opt/azure-iot/`, systemd unit enabled and started; socket `/var/run/nexus-iot.sock` exists when service is running.
- [ ] App: Uses `IoTClient` and `send_scan(scan_record)` for each scan to send; no Azure credentials in the app.
- [ ] Backend: **Azure Function (C#)** triggered by IoT Hub messages; parses `scan_batch` payloads and **stores scan data in PostgreSQL**. IoT Hub route (or equivalent) must point device-to-cloud messages to the function.

This document describes the **full path and reasons** for sending scan data to Azure IoT Hub using MQTT and for storing it in PostgreSQL via the C# Azure Function in this project.
