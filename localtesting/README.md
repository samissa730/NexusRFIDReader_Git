# Localtesting: 5-Min Short-Lived Cert and Renew Workflow

This folder runs **step-ca** and an **EST proxy** in Docker so you can test:

- **5-minute short-lived device certificates** (renew workflow)
- **Re-enrollment / renewal** (same device, new cert after expiry)
- **Azure IoT** using a **permanent CA** (group enrollment) so you never update the portal when the device renews

---

## 1. Start the local CA and EST

From this directory:

```bash
docker compose up -d --build
```

- **step-ca** listens on `8443` (CA API).
- **EST** is at `https://localhost:9443/est` (bootstrap token: `changeme`).
- Device certs issued via EST have a **5-minute** lifetime (`defaultTLSCertDuration: 5m`).

If you already had a volume from before the 5m change, remove it so the init runs again with the new config:

```bash
docker compose down -v
docker compose up -d --build
```

---

## 2. Run the renew workflow test

**Quick test (enroll once, then re-enroll immediately):**

```bash
cd localtesting
python test_renew_workflow.py
```

This checks that the EST server issues 5-min certs and allows re-enrollment (renewal) for the same CN.

**Full test (wait for expiry, then renew):**

```bash
python test_renew_workflow.py --wait-renew
```

This enrolls once, waits 5 minutes 10 seconds, then renews and verifies the new cert is valid. Output certs are saved under `localtesting/renew_workflow_output/`.

---

## 3. Automatic renewal (cron job)

**auto_renew_cert.py** runs once per cron invocation: it reads the current device cert, checks how much time is left until expiry, and if time left is below a threshold (default 60 seconds) it re-enrolls via EST and overwrites the cert/key in `est_test_output/` (same directory as **test_est_enrollment.py**; **test_x509_dps_iot_hub.py** uses these certs). The threshold is kept below the typical cron interval (e.g. 2 minutes) so renewal runs before expiry.

**One-time setup**

1. **Create an initial cert** (so the script has something to check):
   ```bash
   cd localtesting
   python test_est_enrollment.py
   ```
   This writes `est_test_output/device_cert.pem` and `device_key.pem`. The same certs are used by **test_x509_dps_iot_hub.py**.

2. **Install the cron job** (run every 2 minutes):
   ```bash
   crontab -e
   ```
   Add one line (replace the path with your actual repo path):
   ```cron
   */2 * * * * /usr/bin/python3 /home/recomputer/Documents/NexusRFIDReader_Git/localtesting/auto_renew_cert.py >> /home/recomputer/Documents/NexusRFIDReader_Git/localtesting/auto_renew.log 2>&1
   ```
   Save and exit. Cron will run the script every 2 minutes.

   **Important:** Use **your user crontab** (`crontab -e` when logged in as recomputer), not root’s. The script must run as the same user that owns `est_test_output/` so it can overwrite the cert files.    If you use `sudo crontab -e`, the job runs as root and will get "Permission denied" when writing.

   **If you see "Permission denied" even with user crontab:** The directory may have been created when cron ran as root. Fix ownership once (run in a shell as your user):
   ```bash
   sudo chown -R $(whoami) /home/recomputer/Documents/NexusRFIDReader_Git/localtesting/est_test_output
   ```
   Use your actual path to `est_test_output`. Then the next cron run can write the renewed certs.

3. **Optional:** Use a different threshold (renew when less than 90 seconds left):
   ```cron
   */2 * * * * /usr/bin/python3 /home/recomputer/Documents/NexusRFIDReader_Git/localtesting/auto_renew_cert.py --threshold 90 >> /home/recomputer/Documents/NexusRFIDReader_Git/localtesting/auto_renew.log 2>&1
   ```

**What you need**

- Docker step-ca + EST running (`docker compose up -d` in localtesting).
- Initial cert from step 1. If the script runs and finds no cert, it exits with an error and logs: run `test_est_enrollment.py` or `test_renew_workflow.py` first.

**Manual run (no cron)**

```bash
cd localtesting
python auto_renew_cert.py
# Or with custom threshold / cert dir:
python auto_renew_cert.py --threshold 90 --cert-dir ./est_test_output
```

**Logs**

- If you use the crontab line above, output goes to `localtesting/auto_renew.log`. Check it with `tail -f localtesting/auto_renew.log`.
- Messages: "OK: Cert valid for Ns, no renewal" when no action; "Renewing: ..." and "OK: Renewed cert ..." when a renewal runs.

---

## 4. Where to get the permanent root / CA for Azure

The **long-lived CA** that signs your device certs lives inside the step-ca container. You need it for **Azure group enrollment** (so Azure trusts any device cert signed by this CA).

**Export the intermediate CA (use this for Azure):**

Device certs are signed by the **intermediate** CA. Export it from the running step-ca container:

```bash
docker cp step-ca-est-test:/home/step/certs/intermediate_ca.crt ./intermediate_ca.crt
```

Optional — export the root as well (e.g. for documentation or chaining):

```bash
docker cp step-ca-est-test:/home/step/certs/root_ca.crt ./root_ca.crt
```

- **For Azure DPS group enrollment:** upload **`intermediate_ca.crt`** (the CA that directly signs device certs). step-ca’s root and intermediate are long-lived by default (e.g. 10 years); for a true 20–30 year CA you would re-init step-ca with custom validity or use your own root.
- Keep `intermediate_ca.crt` (and optionally `root_ca.crt`) safe; you’ll register the intermediate in Azure once and leave it there.

---

## 5. Azure side: group enrollment (one-time)

To use **short-lived device certs** and **renew** without changing Azure each time:

1. **Use group enrollment**, not individual enrollment.
2. **Register the CA** that signs device certs (the intermediate from step 3).

**Steps:**

1. In **Azure Portal** → your **Device Provisioning Service (DPS)** → **Manage enrollments** → **Enrollment groups**.
2. **Add enrollment group**.
3. **Attestation:** X.509, **Certificate type:** CA Certificate. Upload **`intermediate_ca.crt`** (primary). Optionally add a secondary CA for rollover.
4. **Initial device twin / IoT Hub:** set as needed.
5. **Allocation:** e.g. **“Use custom allocation”** or **“Static configuration”** so the device gets a specific hub; or use **symmetric key** and set **Device ID** from the cert (e.g. **Common Name (CN)** = registration ID). If you use **“Allow reprovisioning”**, the same device can reprovision after renewal.
6. Save.

Result: any device whose certificate chains to `intermediate_ca.crt` can provision. When the device renews and gets a new short-lived cert (same CN), it’s still signed by the same CA, so **no change in Azure** is required.

---

## 6. How to test the whole workflow

1. **Start local CA + EST** (section 1).
2. **Run renew test** and get device certs (section 2):
   - `python test_est_enrollment.py` → certs in `est_test_output/` (used by **test_x509_dps_iot_hub.py**). **auto_renew_cert.py** (cron) also writes here by default.
3. **Export intermediate CA** and **create group enrollment** in Azure (sections 3 and 4).
4. **Configure your device app** to use:
   - Cert: `localtesting/est_test_output/device_cert.pem`
   - Key: `localtesting/est_test_output/device_key.pem`
   - DPS scope + (optional) registration ID = cert CN, e.g. `test-device-001`.
5. **Connect and send data** to IoT Hub (your existing `iot_service.py` or test script).
6. **After 5 minutes:** run renewal again (e.g. `python test_renew_workflow.py` and use the new `device_cert.pem` / `device_key.pem`, or have your app call EST renew and reload certs). **Reconnect to Azure and send data** — no change in the Azure portal.

To test “renew then connect” explicitly:

- Run `test_renew_workflow.py --wait-renew` (or your app’s renew logic).
- Point the device at the new cert/key.
- Connect to DPS → IoT Hub and send a message.

---

## 7. Sending data to Azure (test_x509_dps_iot_hub.py)

To run **test_x509_dps_iot_hub.py** (DPS registration + IoT Hub connection + send mock scan data), the script needs your DPS **idScope** and **globalEndpoint**.

**Option A — config file (recommended):**

1. Copy the example and edit with your DPS values:
   ```bash
   cp provisioning_config_x509.json.example provisioning_config_x509.json
   ```
2. Edit `provisioning_config_x509.json`: set **idScope** to your DPS ID Scope (Azure Portal → DPS → Overview) and **globalEndpoint** (usually `global.azure-devices-provisioning.net`).

**Option B — environment variables:**

```bash
export DPS_ID_SCOPE="your-dps-id-scope"
export DPS_GLOBAL_ENDPOINT="global.azure-devices-provisioning.net"
```

Then run (after running `test_est_enrollment.py` so `est_test_output/device_cert.pem` and `device_key.pem` exist):

```bash
python test_x509_dps_iot_hub.py
```

To skip this test (e.g. in CI): `SKIP_X509_DPS_TEST=1`.

---

## Summary

| Item | What to do |
|------|------------|
| **5-min cert** | Already set in `docker-compose.yml` (provisioner claims). |
| **Renew test** | `python test_renew_workflow.py` or `--wait-renew`. |
| **Permanent CA** | Export `intermediate_ca.crt` from container; use for Azure. |
| **Azure** | Group enrollment, upload intermediate CA, allocate by CN or custom. |
| **E2E test** | Enroll → connect & send data → (wait 5m) → renew → reconnect & send data. |
| **Auto-renew** | Cron: run `auto_renew_cert.py` every 2 min; see section 3. |
