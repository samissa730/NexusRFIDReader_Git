# NexusRFIDReader: Deployment and OTA Update Guide

This guide explains how builds are produced, where they are stored, and how devices receive over-the-air (OTA) updates. It uses **Azure IoT Hub** (where your devices are already registered) to **notify** devices, and **Azure Blob Storage** (with URL + SAS token in device config) for the actual package download. Detailed step-by-step instructions include **where to navigate**, **what to click**, and **links**.

**Three options (no Azure Device Update required):**

- **Option A: Device twin desired property (implemented)** – After uploading to blob, the **pipeline** updates each device’s twin desired property (`ota.action = "check_update"`). The device receives the twin patch and runs **`Azure-IoT-Connection/download.py`**, which uses the **app config** to pull the .deb from blob (**releases/test/latest.json**) and install it. No Azure Device Update or Azure Function required.
- **Option B: Cloud-to-device (C2D) message** – Alternative: the pipeline could send a C2D message to each device; the device would run the same “pull from blob and install” flow when it receives the message.
- **Option C: Polling (cron)** – The device runs a script on a schedule (e.g. every 6 hours) and installs if a newer version is in blob storage.

In **Option A** and **Option B**, the device runs the install **only when notified** (no cron). The device **never receives the SAS token over the wire**; it is stored in the **app config** (`/etc/nexuslocate/config/config.json`) and used only to pull from blob.

---

## 1. High-Level Overview

### Option A: Device twin desired property (implemented)

```
Pipeline → upload .deb + latest.json to blob (DeployTest)
    → NotifyDevicesTwin job queries all devices from IoT Hub and updates each device twin desired (ota.action = "check_update")
        → Device receives twin desired patch → runs download.py
            → download.py reads app config (base_url, sas_token) → fetches releases/test/latest.json
                → Downloads .deb from blob → dpkg -i → restart nexusrfid_production.service
```

The pipeline includes the **NotifyDevicesTwin** job for **TEST** only. Add **IotHubConnectionString** to the test variable group to enable it. The job **queries all devices** from IoT Hub at run time and updates each device’s twin desired property (no manual device list). You can extend the same pattern to DEV or PROD later.

### Option B: Cloud-to-device (C2D) message (alternative)

```
Pipeline → upload .deb + latest.json to blob
    → (optional) send C2D to each device
        → Device receives C2D → runs script
            → Script reads config → fetches from blob → installs
```

### Option C: Polling

Device runs **check-and-update-from-test.sh** on a schedule (cron). Each run fetches **releases/test/latest.json** from blob and installs if newer.

---

## 2. Pipeline: Build and Deploy

- **Trigger:** Push or PR merge to **`main`** when changes touch `requirements.txt`, `main.py`, `ui/`, `utils/`, `screens/`, `widgets/`, or `*.spec`.
- **Pipeline file:** [`pipelines/build-deploy.yml`](../pipelines/build-deploy.yml).

| Stage        | Purpose |
|-------------|---------|
| BuildProject | Build Linux and Raspberry Pi .deb, publish artifacts. |
| PostBuild    | Release notes. |
| DeployDev    | Upload to DEV blob. |
| DeployTest   | Upload to TEST blob and write **`releases/test/latest.json`**. Then **NotifyDevicesTwin** job queries **all devices** from IoT Hub and updates each device’s twin desired property (`ota.action = "check_update"`). Device runs **download.py** to pull and install. |
| DeployProd   | Upload to PROD blob. |

**TEST blob** (storage account **satestrfidlocate**, container **deviceupdates**):

| Blob path | Contents |
|-----------|----------|
| `builds/<BuildNumber>/Linux/*.deb` | Linux .deb. |
| `builds/<BuildNumber>/RaspberryPi/*.deb` | Raspberry Pi .deb. |
| `releases/<BuildNumber>/*.deb` | Release .deb files. |
| **`releases/test/latest.json`** | Manifest: `version`, `linux`, `rpi` blob paths. |

Example **releases/test/latest.json**:

```json
{"version": "20250204.1", "linux": "releases/20250204.1/NexusRFIDReader-20250204.1-amd64.deb", "rpi": "releases/20250204.1/NexusRFIDReader-20250204.1-amd64.deb"}
```

After **DeployTest**, the pipeline **updates each device’s twin desired property** so devices run **download.py** and pull and install. The device uses the **blob base URL and SAS token** from its config to download; the twin update only signals “check for update.”

The pipeline already includes **NotifyDevicesTwin** for TEST. Configure **IotHubConnectionString** in the test variable group (§6.2.1). The job queries **all devices** from IoT Hub and updates each device’s twin (no manual device list). The device runs **download.py** when it receives the twin patch; no Azure Function needed. Twin OTA is applied for **TEST** first; extend to DEV/PROD later if desired.

---

## 3. Prerequisites (you likely have these)

- **Azure IoT Hub** – Your devices are already registered here.
- **Devices** – Each device has a **device ID** and can connect to IoT Hub (connection string or DPS).
- **Blob** – Pipeline uploads .deb and **releases/test/latest.json** to the test storage account. Devices will pull from blob using **base_url** and **sas_token** stored in device config.

### 3.1 Get IoT Hub connection string (for pipeline automation)

To automate updating device twins from the pipeline, you need the **IoT Hub connection string** (service-side). The pipeline **queries all device IDs** from IoT Hub at run time, so you do **not** need to maintain a device list in a variable.

**Where to get the IoT Hub connection string (Azure Portal)**

1. Open **https://portal.azure.com** and sign in.
2. In the top search bar, type **IoT Hub** (or **IoT hubs**) and select it.
3. Click your IoT Hub resource (e.g. the one used for your RFID devices).
4. In the left menu under **Settings**, click **Shared access policies**.
5. Click a policy that has **Service connect** (e.g. **iothubowner** or **service**).
6. In the right panel, under **Connection string**, copy **Primary connection string**. Store it securely; you will add it as a secret variable in Azure DevOps.

**Device list:** The **NotifyDevicesTwin** job uses the connection string with `az iot hub device-identity list --login "<connection_string>"` to get all device IDs at run time. Every device in the hub receives a twin desired property update; there is no test-only or prod-only list (any device can be test today and prod tomorrow).

---

## 4. Get a read-only SAS token for the test blob container

The device script downloads the .deb from blob using a **read-only** SAS. Generate this once and put it in device config.

**Where to go**

1. Open **https://portal.azure.com** and sign in.
2. In the top search bar, type **Storage accounts** and select it.
3. Open the **test** storage account (e.g. **satestrfidlocate**).
4. Under **Data storage**, click **Containers**.
5. Click the container **deviceupdates**.

**What to do**

6. In the container toolbar, click **Shared access token** (or **…** → **Generate SAS token**).
7. **Signing method:** Account key (or User delegation if you use it).
8. **Permissions:** Check **Read** only.
9. **Start and expiry:** Set a long-lived expiry (e.g. 1–2 years).
10. Click **Generate SAS token and URL**.
11. Copy the **SAS token** (starts with `?sv=...`). You will add it to the **nexus_update** section of the config file on each device (§5).

**Links**

- [Manage blob containers (portal)](https://learn.microsoft.com/en-us/azure/storage/blobs/blob-containers-portal)  
- [Create SAS tokens](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/authentication/create-sas-tokens?view=doc-intel-4.0.0&tabs=azure-portal)

**Azure CLI alternative**

```bash
az storage container generate-sas \
  --account-name satestrfidlocate \
  --name deviceupdates \
  --permissions r \
  --expiry "2026-12-31T23:59:59Z" \
  --auth-mode login \
  -o tsv
```

Prepend `?` if the output does not include it.

---

## 5. Device config (all options)

OTA uses the **same app config** as the application. The application creates **`/etc/nexuslocate/config/config.json`** when it is first run (after the service is installed); see `settings.py` (`load_config()` and `get_default_config()`). You do **not** create a separate OTA config—only **edit** the existing app config and set the **nexus_update** section. The **SAS token stays only on the device**; the cloud never sends it.

**What to do (on the device, via SSH or console)**

1. Open the **app config** (e.g. `/etc/nexuslocate/config/config.json`):
   ```bash
   sudo nano /etc/nexuslocate/config/config.json
   ```

2. Ensure the JSON has a **nexus_update** section with your blob URL and SAS token (merge into existing config if needed):
   ```json
   "nexus_update": {
     "base_url": "https://satestrfidlocate.blob.core.windows.net/deviceupdates",
     "sas_token": "?sv=...PASTE_YOUR_SAS_TOKEN_HERE...",
     "platform": "rpi"
   }
   ```
   - **base_url:** Test blob base URL (no trailing slash).
   - **sas_token:** The SAS string from §4 (including `?`).
   - **platform:** `"rpi"` for Raspberry Pi or `"linux"` for other Linux. Omit for auto-detect.

3. Save and exit (nano: Ctrl+O, Enter, Ctrl+X).

**OTA script and app config:** The update script (`check-and-update-from-test.sh`) must read this file. Run the script with **NEXUS_UPDATE_CONFIG_PATH** set to the app config path (e.g. `NEXUS_UPDATE_CONFIG_PATH=/etc/nexuslocate/config/config.json`), or configure your OTA listener/cron to set that environment variable so the script uses the app config.

**Reference:** [`scripts/config.json.example`](../scripts/config.json.example). App defaults (including **nexus_update**) are in `settings.get_default_config()` in `settings.py`.

---

## 6. Option A: Device twin desired property (implemented)

The cloud updates each device’s **twin desired property** (e.g. `properties.desired.ota = { "action": "check_update" }`). The device has a **twin patch handler** that runs the update script when it receives this patch, which **pulls** the manifest and .deb from blob using **base_url** and **sas_token** from config.

### 6.1 Updating device twin (manual test – Azure Portal)

**Where to go**

1. In the Azure Portal, open your **IoT Hub**.
2. In the left menu under **Device management**, click **Devices** (or **IoT devices**).
3. Click the **Device ID** of the device you want to notify (e.g. `pi-test-01`).
4. Click **Device twin** (or **Twin**).

**What to do**

5. In the device twin JSON, find the **properties.desired** section (or add it). Add or update the **ota** property:
   ```json
   "desired": {
     "ota": {
       "action": "check_update"
     }
   }
   ```
6. Click **Save**. The device receives the desired property patch and runs **download.py**.

**Link**

- [Understand and use device twins in IoT Hub](https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-devguide-device-twins)

### 6.2 Automating twin update after pipeline upload

After the pipeline uploads to blob (DeployTest), the cloud must update each device’s twin desired property. The pipeline uses Azure CLI with the **azure-iot** extension to **list all devices** from IoT Hub (see §3.1) and run `az iot hub device-twin update --desired '{"ota":{"action":"check_update"}}'` for each device. You only need the **IoT Hub connection string** in a variable group; no device list variable.

#### 6.2.1 Detailed steps: Azure DevOps (update twin after upload)

**Step 1: Create or edit a variable group in Azure DevOps**

1. In your Azure DevOps project, go to **Pipelines** → **Library** (under Pipelines in the left menu).
2. Click **+ Variable group** to create a new group (e.g. **ota-iot-variables**) or click an existing group (e.g. **test-variables**) to add OTA variables.
3. Add variable:
   - **IotHubConnectionString** – Value: paste the IoT Hub **connection string** from §3.1. Click the **lock** icon to make it a **secret**.
4. Click **Save**. No device list variable is needed; the pipeline queries **all devices** from IoT Hub at run time.

**Step 2: Add the variable group to the DeployTest stage**

In [`pipelines/build-deploy.yml`](../pipelines/build-deploy.yml), the DeployTest stage already has `variables: - group: test-variables`. Add your OTA variable group there (if you created a separate one), for example:

```yaml
variables:
  - group: test-variables
  - group: test-keyvault-secrets
  - group: ota-iot-variables   # add this if you use a separate group
```

If you added **IotHubConnectionString** to **test-variables**, you do not need to add another group.

**Step 3: Twin job in the pipeline (TEST)**

The pipeline **already includes** the **NotifyDevicesTwin** job in the DeployTest stage. It runs after the blob deployment, **queries all device IDs** from IoT Hub with `az iot hub device-identity list --login "<connection_string>"`, and updates each device’s twin desired property with `az iot hub device-twin update --desired '{"ota":{"action":"check_update"}}'`. The job is skipped if **IotHubConnectionString** is not set. Devices that receive the twin patch run **download.py** to pull and install the .deb. Place this job after the `DeployToBlobStorage` job (same `jobs:` list):

```yaml
      - job: NotifyDevicesTwin
        displayName: 'Notify all devices via device twin (OTA)'
        condition: succeeded()
        variables:
          - group: test-variables
          - group: test-keyvault-secrets
          - group: ota-iot-variables   # or omit if OTA vars are in test-variables
        steps:
          - task: AzureCLI@2
            displayName: 'List devices and update twin desired property (ota.check_update) for each'
            inputs:
              azureSubscription: ${{ format(variables.workLoadServiceConnection, 'test') }}
              scriptType: bash
              scriptLocation: inlineScript
              inlineScript: |
                set -euo pipefail
                CONN="${{ variables.IotHubConnectionString }}"
                if [ -z "$CONN" ]; then
                  echo "IotHubConnectionString not set; skipping twin OTA notifications."
                  exit 0
                fi
                az extension add --name azure-iot --yes
                echo "Querying IoT Hub for all device IDs..."
                DEVICES=$(az iot hub device-identity list --login "$CONN" --query "[].deviceId" -o tsv)
                if [ -z "$DEVICES" ]; then
                  echo "No devices found in IoT Hub."
                  exit 0
                fi
                for id in $DEVICES; do
                  id=$(echo "$id" | xargs)
                  [ -z "$id" ] && continue
                  echo "Updating device twin desired (ota) for device: $id"
                  az iot hub device-twin update \
                    --login "$CONN" \
                    --device-id "$id" \
                    --desired '{"ota":{"action":"check_update"}}'
                done
                echo "Twin OTA notifications sent."
```

- Replace **ota-iot-variables** with **test-variables** if that is where you stored **IotHubConnectionString**.
- The pipeline must have access to the subscription (e.g. **workLoadServiceConnection** for test). The job lists all devices from IoT Hub and updates each device’s twin desired property.

**Links**

- [IoT Hub device twin REST API](https://learn.microsoft.com/en-us/rest/api/iothub/service/devices/update-twin)
- [Azure Functions trigger for Blob Storage](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-blob-trigger)

### 6.3 Device side: twin patch handler that runs the update script

On the device, a **twin desired-properties patch handler** must:

1. Connect to IoT Hub (using the device connection string).
2. Subscribe to **device twin desired property** patches.
3. When the patch contains **ota.action = "check_update"**, run the update script that **pulls from blob** using config.

The updater is **`Azure-IoT-Connection/download.py`**: it reads **nexus_update.base_url** and **nexus_update.sas_token** from the **app config** (`/etc/nexuslocate/config/config.json` or **NEXUS_UPDATE_CONFIG_PATH**; see §5), fetches **releases/test/latest.json** from blob, compares version, downloads the .deb and runs **dpkg -i**, then restarts **nexusrfid_production.service**. No Azure Device Update or provisioning_config deviceUpdate required.

**Implementation:** The existing **Azure IoT service** (`Azure-IoT-Connection/iot_service.py`) sets **`on_twin_desired_properties_patch_received`** and runs **download.py** when the patch has **`ota.action == "check_update"`**. No separate listener or scheduled fallback.

**Link**

- [Device twins (IoT Hub)](https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-devguide-device-twins)

---

## 7. Option B: Cloud-to-device (C2D) message (alternative)

The cloud sends a **C2D message** to each target device. The device listens for C2D messages and, when it receives an OTA trigger message, runs the same pull-from-blob update flow (`download.py` or `check-and-update-from-test.sh`).

### 7.1 Sending C2D message (manual test – Azure CLI)

Use Azure CLI with the IoT extension to send a C2D message to one device:

```bash
az extension add --name azure-iot --yes
az iot device c2d-message send \
  --login "<IotHubConnectionString>" \
  --device-id "pi-test-01" \
  --data '{"ota":{"action":"check_update","version":"20250204.1"}}'
```

If the device-side C2D handler is running, it should receive the message and execute the update script.

**Links**

- [Send cloud-to-device messages](https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-csharp-csharp-c2d)
- [IoT Hub REST API – Send C2D](https://learn.microsoft.com/en-us/rest/api/iothub/service/send-cloud-to-device-message)

### 7.2 Automating C2D after pipeline upload

After DeployTest uploads artifacts, send C2D OTA trigger messages to devices.

#### 7.2.1 Detailed steps: Azure DevOps (send C2D after upload)

Use **IotHubConnectionString** (secret) from §6.2.1 and either:

- **OtaDeviceIds** (comma-separated), or
- query all device IDs from IoT Hub at runtime.

Ensure the variable group is linked to the DeployTest stage (see Step 1-2 in §6.2.1).

**Add a new job in the DeployTest stage to send C2D messages**

This is an optional alternative to the implemented twin job (`NotifyDevicesTwin` in §6.2.1).

```yaml
      - job: NotifyDevicesC2D
        displayName: 'Notify devices via C2D (OTA)'
        condition: succeeded()
        variables:
          - group: test-variables
          - group: test-keyvault-secrets
          - group: ota-iot-variables   # or omit if OTA vars are in test-variables
        steps:
          - task: AzureCLI@2
            displayName: 'Send C2D OTA trigger to each device'
            inputs:
              azureSubscription: ${{ format(variables.workLoadServiceConnection, 'test') }}
              scriptType: bash
              scriptLocation: inlineScript
              inlineScript: |
                set -euo pipefail
                az extension add --name azure-iot --yes
                CONN="${{ variables.IotHubConnectionString }}"
                BUILD="$(Build.BuildNumber)"
                DEVICES="${{ variables.OtaDeviceIds }}"
                if [ -z "${DEVICES:-}" ]; then
                  DEVICES=$(az iot hub device-identity list --login "$CONN" --query "[].deviceId" -o tsv)
                fi
                for id in $(echo "$DEVICES" | tr ',' ' '); do
                  id=$(echo "$id" | xargs)
                  [ -z "$id" ] && continue
                  echo "Sending C2D OTA trigger to device: $id"
                  az iot device c2d-message send \
                    --login "$CONN" \
                    --device-id "$id" \
                    --data "{\"ota\":{\"action\":\"check_update\",\"version\":\"$BUILD\"}}"
                done
                echo "C2D OTA messages sent."
```

- Replace **ota-iot-variables** with **test-variables** if OTA variables are stored there.
- The message body includes **Build.BuildNumber** so device logs can show which deployment triggered the check.

**Links**

- [Receive C2D messages (device)](https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-devguide-messages-c2d#receive-cloud-to-device-messages)
- [IoT Hub service REST API – Send C2D](https://learn.microsoft.com/en-us/rest/api/iothub/service/send-cloud-to-device-message)

### 7.3 Device side: C2D message handler

On the device, a C2D handler must:

1. Connect to IoT Hub (device connection string).
2. Subscribe to **cloud-to-device messages**.
3. Parse incoming message payload (for example `ota.action == "check_update"`).
4. Run the same update script that pulls from blob using config.

Implementation note: unlike Option A, this option uses the C2D callback path instead of `on_twin_desired_properties_patch_received`.

---

## 8. Option C: Polling with cron

If you do **not** use C2D or device twin, devices can poll blob on a schedule.

- **Script:** [`scripts/check-and-update-from-test.sh`](../scripts/check-and-update-from-test.sh) – Fetches **releases/test/latest.json** from blob (using config), compares version, downloads .deb and runs **dpkg -i** if newer.
- **Config:** Same as above: ensure the **app config** (see §5) has **nexus_update.base_url** and **nexus_update.sas_token**; run the script with **NEXUS_UPDATE_CONFIG_PATH** set to that file.

**Run manually**

```bash
/path/to/scripts/check-and-update-from-test.sh
```

**Run on a schedule (e.g. every 6 hours)**

1. Open crontab: `sudo crontab -e`
2. Add a line (use the **full path** to the script):
   ```cron
   0 */6 * * * /home/pi/NexusRFIDReader_Git/scripts/check-and-update-from-test.sh >> /var/log/nexus-update.log 2>&1
   ```
3. Save and exit. Optionally: `sudo touch /var/log/nexus-update.log`

The script runs on a **schedule**, not only when a new artifact is uploaded.

---

## 9. Builds vs Releases in Blob Storage

| Path | Purpose |
|------|---------|
| **builds/** | Build output by platform: `builds/<BuildNumber>/Linux/`, `builds/<BuildNumber>/RaspberryPi/`. |
| **releases/** | Versioned packages: `releases/<BuildNumber>/*.deb`, and **releases/test/latest.json** for OTA. |

---

## 10. Summary Checklist

### Option A (device twin) or Option B (C2D)

- [ ] IoT Hub exists; devices are registered.
- [ ] Get **IoT Hub connection string** for the pipeline (§3.1); pipeline queries all devices from IoT Hub.
- [ ] Get read-only **SAS token** for container **deviceupdates** (Portal or CLI). On each device, **edit** the **app config** (**/etc/nexuslocate/config/config.json**, §5) and set **nexus_update.base_url** and **nexus_update.sas_token**; run the OTA script with **NEXUS_UPDATE_CONFIG_PATH** set to that path.
- [ ] On each device: the **twin patch handler** in `iot_service.py` (Option A) runs **download.py** when twin desired **ota.action** is **check_update**; no extra listener needed.
- [ ] In Azure DevOps: create/edit **variable group** with **IotHubConnectionString** (secret) (§6.2.1 Step 1–2). No device list needed; pipeline queries all devices from IoT Hub.
- [ ] In the pipeline: the **NotifyDevicesTwin** job (§6.2.1 Step 3) is already in the DeployTest stage and notifies all devices via device twin after each upload.

### Option C (Polling)

- [ ] On each device, **edit** the **app config** (/etc/nexuslocate/config/config.json, §5) and set **nexus_update.base_url** and **nexus_update.sas_token**; run the script with **NEXUS_UPDATE_CONFIG_PATH** set to that path.
- [ ] Schedule **check-and-update-from-test.sh** via cron (e.g. every 6 hours).

---

## 11. Alternative: Azure Device Update for IoT Hub

If you prefer a dedicated update service with built-in deployment and status, you can use **Azure Device Update for IoT Hub** instead of C2D/twin. The pipeline can be extended to import an update and create a deployment so the ADU agent on each device runs an install script. This requires:

- A **Device Update** account and instance linked to your IoT Hub.
- The **ADU agent** installed on each device.
- Pipeline variables (e.g. **aduAccountEndpoint**) and a pipeline step that calls the Device Update API.

For full ADU setup steps (create account, instance, device groups, agent install, pipeline variables), see the Microsoft docs below. The repo’s pipeline currently includes an **optional** ADU import/deploy step when **aduAccountEndpoint** is set; you can keep it disabled and use **IoT Hub device twin** (Option A) as described in this guide.

**Links**

- [Create Device Update resources](https://learn.microsoft.com/en-us/azure/iot-hub-device-update/create-device-update-account?tabs=portal)

---

## 12. References and Links

**This repo**

- Pipeline: [`pipelines/build-deploy.yml`](../pipelines/build-deploy.yml)
- Update script (pull from blob): [`scripts/check-and-update-from-test.sh`](../scripts/check-and-update-from-test.sh)
- Config example: [`scripts/config.json.example`](../scripts/config.json.example)

**Microsoft Learn – IoT Hub**

- [Create an IoT hub (portal)](https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-create-through-portal)
- [Send cloud-to-device messages](https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-csharp-csharp-c2d)
- [Receive C2D messages (device)](https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-devguide-messages-c2d#receive-cloud-to-device-messages)
- [Device twins](https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-devguide-device-twins)
- [IoT Hub REST API – Send C2D](https://learn.microsoft.com/en-us/rest/api/iothub/service/send-cloud-to-device-message)
- [IoT Hub REST API – Update twin](https://learn.microsoft.com/en-us/rest/api/iothub/service/twin/update)

**Microsoft Learn – Storage**

- [Manage blob containers (portal)](https://learn.microsoft.com/en-us/azure/storage/blobs/blob-containers-portal)

**Azure Device Update (alternative)**

- [Device Update for IoT Hub overview](https://learn.microsoft.com/en-us/azure/iot-hub-device-update/device-update-overview)
