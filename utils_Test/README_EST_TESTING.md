# Testing step-ca and EST Locally

**For a single, complete guide for initial testing (step-ca in Docker, bootstrap + certificate issuance on Raspberry Pi/reComputer/Mac), see [GUIDE_INITIAL_TESTING_STEP_CA.md](GUIDE_INITIAL_TESTING_STEP_CA.md).**

---

## Using step-ca with EST (EST Proxy)

**step-ca does not implement EST natively.** This repo provides an **EST proxy** that exposes EST endpoints and uses step-ca as the backend. You can run everything **without the `est_proxy` folder** using a single Docker Compose command:

- **step-ca** on port **8443** (CA API).
- **est-proxy** on port **9443** (EST at `https://localhost:9443/est`).

Use **EST Server URL** `https://localhost:9443/est` and bootstrap token `changeme` when running `test_est_enrollment.py` or `test_bootstrap_enrollment.py`.

- **Alternative (no EST):** Get device certs with the **step CLI** only; see [GUIDE_INITIAL_TESTING_STEP_CA.md](GUIDE_INITIAL_TESTING_STEP_CA.md).

---

This guide explains how to test EST certificate enrollment with the EST proxy + step-ca, or with another EST-capable server.

## Overview

**Testing Flow:**
1. Start step-ca EST server in Docker
2. Run EST client to enroll and get X.509 certificate
3. Verify certificate enrollment
4. Use certificate for Azure IoT Hub X.509 authentication (next step)

## Prerequisites

- Docker and Docker Compose installed
- Python 3.7+ with `cryptography` and `requests` packages
- For Raspberry Pi: Docker should be installed and running

## Quick Start

### 1. Start step-ca and EST proxy (single command, no setup script)

From `utils_Test` you only need `docker-compose.yml` and the `runner/` image. The EST proxy code is embedded in the compose file (no `est_proxy` folder or separate script file):

```bash
cd utils_Test

# Build and start: CA init runs automatically, then step-ca and EST proxy
docker compose up -d --build

# View logs
docker compose logs -f step-ca
docker compose logs -f est-proxy

# Check status
docker compose ps
```

This will:
- Run a one-off **step-ca-init** container to create the CA and enable EST in config (if not already present).
- Start **step-ca** on port 8443 and **est-proxy** on port 9443 (EST at `https://localhost:9443/est`, bootstrap token: `changeme`).
- Store CA data in the Docker named volume `step_ca_data` (no local `step-ca-data` folder unless you change the compose file).

### 2. (Optional) Legacy setup with script and `est_proxy` folder

If you prefer the previous flow with `setup_step_ca.sh` and the `est_proxy/` folder, run the setup script once, then use a compose file that builds `./est_proxy` and uses `./step-ca-data` (see git history or keep a copy of the old `docker-compose.yml`). The default compose in this repo uses the **runner** image and embeds the EST proxy code in `EST_PROXY_SCRIPT` in the compose file.

If you see **"client version 1.52 is too new. Maximum supported API version is 1.41"**, use the helper script (it forces the client to use API 1.41):

```bash
bash docker-compose-up.sh up -d --build
# or for any compose command:
bash docker-compose-up.sh up -d
bash docker-compose-up.sh down
```

Or set the variable yourself: `export DOCKER_API_VERSION=1.41` then run `docker compose up -d --build`.

- step-ca: `https://localhost:8443`
- **EST (proxy):** `https://localhost:9443/est`

### 3. Test EST Enrollment

**Basic Test (Single Device):**
```bash
# Run the basic test script
python test_est_enrollment.py
```

**Comprehensive Bootstrap Enrollment Test:**
```bash
# Run comprehensive bootstrap enrollment and certificate issuance test
python test_bootstrap_enrollment.py
```

**What the tests cover:**

**Basic Test (`test_est_enrollment.py`):**
1. Generate a CSR (Certificate Signing Request) with registration_id as CN
2. Bootstrap enrollment via EST server (using bootstrap token)
3. Verify certificate issuance (CN, issuer, validity period)
4. Save certificates to `est_test_output/` directory

**Comprehensive Test (`test_bootstrap_enrollment.py`):**
1. ✅ **Bootstrap device enrollment** - Tests initial enrollment with bootstrap token
2. ✅ **Certificate issuance verification** - Verifies certificate details:
   - Subject CN matches registration_id
   - Issuer matches CA
   - Validity period is reasonable
   - Certificate chain is valid
3. ✅ **Multiple device enrollment** - Tests bootstrap enrollment for multiple devices
4. ✅ **Certificate chain validation** - Verifies full certificate chain

### 4. Verify Certificates

After successful enrollment, check the output directory:

```bash
ls -la est_test_output/
```

You should see:
- `device_cert.pem` - Device certificate (signed by CA)
- `device_key.pem` - Device private key
- `device_chain.pem` - Certificate chain
- `ca_cert.pem` - CA certificate
- `device.csr` - Original certificate signing request

### 5. Test DPS and IoT Hub with X.509 (`test_x509_dps_iot_hub.py`)

This test uses the certificates from `est_test_output/` (from `test_est_enrollment.py`) to register with **Azure Device Provisioning Service (DPS)** using X.509, then connect to **IoT Hub** and send **scan data** every 5 seconds until you press **Ctrl+C**.

#### Prerequisites

- `est_test_output/device_cert.pem` and `device_key.pem` (run `test_est_enrollment.py` first).
- DPS **ID Scope** and **Global endpoint** (from Azure Portal).
- **Individual enrollment** created in DPS for this device (see below).

#### Configuration on Azure (DPS + IoT Hub) – Individual enrollment

1. **Create or use a Device Provisioning Service (DPS)**  
   - Azure Portal → Create resource → **Device Provisioning Service** (or use existing).  
   - Note **Global device endpoint** (e.g. `global.azure-devices-provisioning.net`) and **ID Scope** (e.g. `0ne01234AB`).

2. **Link DPS to an IoT Hub**  
   - DPS → **Linked IoT Hubs** → Add → select your IoT Hub.  
   - DPS → **Allocation policy**: e.g. "Evenly weighted distribution" so devices get assigned to the hub.

3. **Create an Individual Enrollment (X.509)**  
   - DPS → **Manage enrollments** → **Individual Enrollments** → **Add individual enrollment**.  
   - **Mechanism:** X.509.  
   - **Primary certificate:**  
     - Upload the **device certificate** (the same one the test will use).  
     - For this test, upload the contents of `est_test_output/device_cert.pem` (the full PEM, including `-----BEGIN CERTIFICATE-----` / `-----END CERTIFICATE-----`).  
   - **Registration ID:** must match the **Common Name (CN)** of the device certificate. For the default test this is `test-device-001`.  
   - **IoT Hub Device ID:** you can leave "Auto-generate" or set to e.g. `test-device-001`.  
   - **Enable entry:** Yes.  
   - Save.

4. **When you renew the device cert** (e.g. after it expires or after re-running `test_est_enrollment.py`), update the same individual enrollment: replace the **Primary certificate** with the new `device_cert.pem`. Registration ID stays the same.

#### Local config (idScope + globalEndpoint)

The test reads DPS settings from (first found):

- `utils_Test/provisioning_config_x509.json` with `idScope` and `globalEndpoint`, or  
- `utils_Test/provisioning_config.json`, or  
- `/etc/nexuslocate/config/provisioning_config.json`, or
- Environment variables: `DPS_ID_SCOPE`, `DPS_GLOBAL_ENDPOINT`.

Example `provisioning_config_x509.json`:

```json
{
  "idScope": "0ne01234AB",
  "globalEndpoint": "global.azure-devices-provisioning.net"
}
```

See `provisioning_config_x509.json.example`.

#### Run the test

```bash
cd utils_Test

# Ensure EST enrollment was run and device cert is valid (not expired)
python test_est_enrollment.py

# Run DPS + IoT Hub test (sends scan data every 5 seconds; Ctrl+C to stop)
sudo python3 test_x509_dps_iot_hub.py
```

The script will:

1. Load `device_cert.pem` and `device_key.pem` from `est_test_output/`.
2. Use the certificate **CN** as **Registration ID** (e.g. `test-device-001`).
3. Register with DPS using X.509 (individual enrollment must exist with that cert and registration ID).
4. Connect to the assigned IoT Hub with X.509.
5. Send **scan data** (mock scan_batch) every 5 seconds until you press **Ctrl+C**.

**Certificate expiry:** Device certs from EST have short validity (e.g. 24 hours). If you get "Credentials invalid" or "not authorised", check expiry with `openssl x509 -in est_test_output/device_cert.pem -noout -dates`. Re-run `test_est_enrollment.py` to get a new cert, then update the **Primary certificate** in the DPS individual enrollment with the new `device_cert.pem`, and run `test_x509_dps_iot_hub.py` again.

**Skip in CI:** Set `SKIP_X509_DPS_TEST=1` to skip this test.

## Configuration

### Update Test Parameters

Edit `test_est_enrollment.py` to change:

```python
EST_SERVER_URL = "https://localhost:8443/est"
BOOTSTRAP_TOKEN = "changeme"  # Update if you changed it in setup
REGISTRATION_ID = "test-device-001"  # Your device registration ID
```

### Change Bootstrap Token

If you want to use a different bootstrap token:

1. Edit `step-ca-config/ca.json`:
```json
{
  "est": {
    "enabled": true,
    "bootstrapToken": "your-new-token-here"
  }
}
```

2. Update `test_est_enrollment.py` with the new token
3. Restart the server: `docker-compose restart`

## Troubleshooting

### "client version 1.52 is too new. Maximum supported API version is 1.41"

Your Docker client is newer than the daemon. Force the client to use API 1.41:

```bash
export DOCKER_API_VERSION=1.41
docker compose up -d --build
```

Or use the helper script (it sets the variable for you):

```bash
bash docker-compose-up.sh up -d --build
```

Use `docker-compose-up.sh` for other compose commands too (e.g. `bash docker-compose-up.sh down`).

### 502 Bad Gateway from EST proxy (Token failed / Sign failed)

The test script now prints the proxy’s response body (e.g. `Token failed: ...` or `Sign failed: ...`). Use that to see the real error.

- **If it mentions certificate or "valid for localhost, not step-ca":** the CA was initialized with only `--dns localhost`, but the EST proxy connects to `step-ca:8443`. Re-initialize so the CA’s TLS cert includes `step-ca`:
  ```bash
  # Stop containers, remove CA data, then run setup again (script now uses --dns localhost --dns step-ca)
  docker compose down
  rm -rf step-ca-data
  ./setup_step_ca.sh
  bash docker-compose-up.sh up -d --build
  ```
- **Other errors:** run `docker compose logs est-proxy` to see the step CLI stderr.

### Read timed out when calling EST proxy

1. **Use 127.0.0.1 instead of localhost** so the client uses IPv4 (the test script default is now `https://127.0.0.1:9443/est`).
2. **Confirm the proxy is reachable:**  
   `curl -k https://127.0.0.1:9443/health`  
   You should get `{"status":"ok"}`. If this times out, the proxy isn’t receiving traffic (check `docker compose ps`, restart with `docker compose up -d --build`).
3. **If health works but enrollment times out:** the proxy may be blocking on `step ca token` or `step ca sign`. In one terminal run `docker compose logs -f est-proxy`, in another run the test; you should see either “simpleenroll request for CN=…” and then a 502 (e.g. “Token timed out”) or an error. Rebuilt proxy now uses a 20s subprocess timeout so you should get a 502 with a message instead of a client read timeout.

### EST Server Not Starting

```bash
# Check if port 8443 is already in use
netstat -an | grep 8443  # Linux/Mac
netstat -an | findstr 8443  # Windows

# Check Docker logs
docker-compose logs step-ca

# Restart server
docker-compose restart
```

### Certificate Enrollment Fails

1. **Check EST server is running:**
   ```bash
   docker-compose ps
   curl -k https://localhost:8443/health
   ```

2. **Verify bootstrap token:**
   - Check token in `step-ca-config/ca.json`
   - Ensure it matches `BOOTSTRAP_TOKEN` in test script

3. **Check SSL certificate:**
   - For local testing, SSL verification is disabled (`verify_ssl=False`)
   - In production, use proper CA certificate

### Import Errors

If you get import errors:

```bash
# Install required packages
pip install cryptography requests

# Or add to requirements.txt
echo "cryptography" >> requirements.txt
echo "requests" >> requirements.txt
pip install -r requirements.txt
```

## Test Coverage

### Bootstrap Device Enrollment ✅
- Initial enrollment using bootstrap token
- Multiple device enrollment support
- Bootstrap token authentication

### Certificate Issuance Verification ✅
- Certificate subject CN verification
- Issuer verification against CA
- Validity period checks
- Serial number extraction
- Certificate chain validation
- Signature algorithm verification

### What Gets Tested

1. **Bootstrap Enrollment Flow:**
   - Device generates CSR with registration_id as CN
   - Device authenticates with bootstrap token
   - EST server issues certificate
   - Certificate is returned to device

2. **Certificate Issuance:**
   - Certificate CN matches registration_id
   - Certificate is signed by CA
   - Certificate validity period is reasonable
   - Certificate chain is complete and valid

3. **Multiple Devices:**
   - Bootstrap token works for multiple devices
   - Each device gets unique certificate
   - Certificates are properly isolated

## Next Steps

After successful EST enrollment testing:

1. **Integrate with device_setup.py:**
   - Add EST enrollment function
   - Save certificates to `/etc/nexuslocate/pki/`

2. **Update iot_service.py:**
   - Add X.509 certificate authentication
   - Use `IoTHubDeviceClient.create_from_x509_certificate()`

3. **Configure Azure IoT Hub:**
   - Upload CA certificate to Azure DPS
   - Create X.509 enrollment group
   - Register device with certificate

## Test Files

### Core Files
- `est_client.py` - EST client library for certificate enrollment
- `test_est_enrollment.py` - Basic test script for single device bootstrap enrollment
- `test_bootstrap_enrollment.py` - **Comprehensive test for bootstrap device enrollment and certificate issuance verification**

### Infrastructure Files
- `docker-compose.yml` - Docker Compose configuration for step-ca
- `setup_step_ca.sh` - Setup script for initializing step-ca
- `quick_test_est.sh` - Quick test script that checks prerequisites and runs tests

### Output
- `est_test_output/` - Directory containing test certificates (created after test)
  - Basic test: Single set of certificates
  - Comprehensive test: Separate directory for each device (`device_1_<id>/`, `device_2_<id>/`, etc.)

## Cleanup

To stop and remove the EST server:

```bash
# Stop server
docker-compose down

# Remove volumes (CA data)
docker-compose down -v

# Remove test output
rm -rf est_test_output/
```

## Security Notes

⚠️ **For Testing Only:**
- Default bootstrap token (`changeme`) is weak - use strong token in production
- SSL verification is disabled for local testing
- Certificates are for testing only

**For Production:**
- Use strong bootstrap tokens
- Enable SSL certificate verification
- Store CA certificates securely
- Use proper key management

## References

- [step-ca Documentation](https://smallstep.com/docs/step-ca)
- [EST Protocol (RFC 7030)](https://tools.ietf.org/html/rfc7030)
- [Azure IoT Hub X.509 Authentication](https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-x509ca-overview)
