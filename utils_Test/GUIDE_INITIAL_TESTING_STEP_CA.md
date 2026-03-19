# Step-CA Initial Testing — Single Complete Guide

This guide runs **step-ca** in Docker and tests **bootstrap trust** and **certificate issuance** on the same device (Raspberry Pi, reComputer, or Mac). It uses the **step CLI** and follows the same flow you would use in production.

---

## What You Will Do

1. **Run the CA** in a Docker container (port 9000).
2. **Bootstrap trust** on the device using the CA root fingerprint.
3. **Request a device certificate** and verify issuance.

**Result:** You get `device.crt` and `device.key` for a test device (e.g. `My-Test-Device-001`), which you can later use for Azure IoT Hub X.509 auth.

---

## Prerequisites

- **Docker** installed and running.
- **Network:** For “device” and “CA” on the same machine, no extra network setup. For a separate device, use the CA host’s IP instead of `localhost` in the steps below.

---

## Part 1: Setup the step-ca Server (Docker)

All commands in this part are run on the machine that will host the CA (same machine as the “device” for initial testing).

### 1.1 Create directory and initialize the CA

```bash
mkdir -p ~/step
cd ~/step

docker run -it --rm -v $(pwd):/home/step smallstep/step-ca step ca init \
  --name "My-IoT-CA" \
  --provisioner "admin" \
  --dns "localhost" \
  --address ":9000"
```

- When prompted, set a **password** and remember it (you will use it in the next step).
- This creates config and certs under `~/step` (e.g. `config/`, `certs/`, `secrets/`).

### 1.2 Create the CA password file

The step-ca container needs the password in a file to start non-interactively.

```bash
mkdir -p ~/step/secrets
echo "YOUR_CA_PASSWORD" > ~/step/secrets/password
chmod 600 ~/step/secrets/password
```

Replace `YOUR_CA_PASSWORD` with the password you set in step 1.1.

### 1.3 Start the step-ca container

Use the **current directory** as the mount (not a `step` subfolder):

```bash
cd ~/step
sudo docker run -d --name step-ca -p 9000:9000 -v $(pwd):/home/step smallstep/step-ca
```

Check that it is running:

```bash
sudo docker ps
sudo docker logs step-ca
```

If the container exits, check the logs for errors (e.g. wrong password or missing `secrets/password`).

### 1.4 Get the root CA fingerprint (bootstrap trust later)

```bash
sudo docker exec step-ca step certificate fingerprint /home/step/certs/root_ca.crt
```

**Save the 64-character hex string** (e.g. `a1b2c3d4e5f6...`). You will use it when bootstrapping the “device.”

---

## Part 2: Install step CLI on the “Device”

The “device” is the machine that will request a certificate (for initial testing, the same machine as the CA).

### 2.1 Raspberry Pi / reComputer (ARM64)

```bash
cd ~
wget https://github.com/smallstep/cli/releases/latest/download/step_linux_arm64.tar.gz
tar -xzf step_linux_arm64.tar.gz
sudo cp step_linux_arm64/bin/step /usr/local/bin/
```

For **32-bit ARM** (older Pi):

```bash
wget https://github.com/smallstep/cli/releases/latest/download/step_linux_arm.tar.gz
tar -xzf step_linux_arm.tar.gz
sudo cp step_linux_arm/bin/step /usr/local/bin/
```

Verify:

```bash
step version
```

### 2.2 Mac

```bash
brew install step
step version
```

---

## Part 3: Bootstrap Trust on the Device

This configures the step CLI to trust your CA using the fingerprint from Part 1.4.

**Same machine as CA (e.g. Raspberry Pi):**

```bash
step ca bootstrap --ca-url https://localhost:9000 --fingerprint YOUR_FINGERPRINT_STRING
```

Replace `YOUR_FINGERPRINT_STRING` with the 64-character hex from step 1.4.

**Different machine (CA on another host):**

Use the CA host’s IP and ensure port 9000 is reachable:

```bash
step ca bootstrap --ca-url https://CA_HOST_IP:9000 --fingerprint YOUR_FINGERPRINT_STRING
```

---

## Part 4: Test Certificate Issuance

Request a device certificate (this is the “test certificate issuance” step).

```bash
step ca certificate "My-Test-Device-001" device.crt device.key
```

- When prompted for a one-time token, run (on the CA host):

  ```bash
  docker exec step-ca step ca token "My-Test-Device-001"
  ```

- Paste the token into the prompt.

You should get:

- `device.crt` — device certificate  
- `device.key` — device private key  

Optional verification:

```bash
step certificate inspect device.crt
openssl x509 -in device.crt -noout -subject -dates
```

---

## Quick Reference: All Commands in Order

**On CA host (e.g. Raspberry Pi):**

```bash
# 1) Init CA
mkdir -p ~/step && cd ~/step
docker run -it --rm -v $(pwd):/home/step smallstep/step-ca step ca init \
  --name "My-IoT-CA" --provisioner "admin" --dns "localhost" --address ":9000"

# 2) Password file
mkdir -p ~/step/secrets
echo "YOUR_CA_PASSWORD" > ~/step/secrets/password
chmod 600 ~/step/secrets/password

# 3) Start CA
cd ~/step
sudo docker run -d --name step-ca -p 9000:9000 -v $(pwd):/home/step smallstep/step-ca

# 4) Fingerprint (save this)
sudo docker exec step-ca step certificate fingerprint /home/step/certs/root_ca.crt

# 5) Install step CLI (ARM64)
cd ~
wget https://github.com/smallstep/cli/releases/latest/download/step_linux_arm64.tar.gz
tar -xzf step_linux_arm64.tar.gz
sudo cp step_linux_arm64/bin/step /usr/local/bin/

# 6) Bootstrap
step ca bootstrap --ca-url https://localhost:9000 --fingerprint YOUR_FINGERPRINT_STRING

# 7) Get certificate
step ca certificate "My-Test-Device-001" device.crt device.key
# (Use token from: docker exec step-ca step ca token "My-Test-Device-001")
```

---

## Troubleshooting

| Issue | What to do |
|-------|------------|
| Container exits immediately | Ensure `~/step/secrets/password` exists and contains the correct CA password; check `sudo docker logs step-ca`. |
| `cannot stat 'step_linux_arm64/step'` | Binary is in `bin/`: use `sudo cp step_linux_arm64/bin/step /usr/local/bin/`. |
| `container is not running` | Fix volume: use `-v $(pwd):/home/step` when already in `~/step`, not `$(pwd)/step`. Restart container after fixing. |
| Bootstrap or certificate fails | Confirm step-ca is running (`docker ps`), use correct fingerprint and CA URL (e.g. `https://localhost:9000` or `https://CA_IP:9000`). |

---

## Next Steps

- Use `device.crt` and `device.key` for **Azure IoT Hub** X.509 authentication (DPS + device connection).
- For **EST-based** testing (Python EST client), see `README_EST_TESTING.md` and use the EST-enabled step-ca setup (e.g. port 8443) if you need EST specifically.

---

## Summary

| Step | Action |
|------|--------|
| 1 | Init CA in `~/step` with Docker, set password |
| 2 | Create `~/step/secrets/password` with that password |
| 3 | Start container: `-v $(pwd):/home/step`, port 9000 |
| 4 | Get root CA fingerprint |
| 5 | Install step CLI (`bin/step` on Linux) |
| 6 | Bootstrap: `step ca bootstrap --ca-url https://localhost:9000 --fingerprint <FP>` |
| 7 | Issue cert: `step ca certificate "My-Test-Device-001" device.crt device.key` |

This is the single, complete flow for initial testing of step-ca bootstrap and certificate issuance on your device (Raspberry Pi / reComputer / Mac).
