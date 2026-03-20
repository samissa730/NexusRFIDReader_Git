# Azure IoT Connection Service

This repository contains the necessary files to set up an Azure IoT connection service on a Raspberry Pi device. The service automatically connects to Azure IoT Hub and maintains a persistent connection with heartbeat monitoring.

## Features

- **X.509 authentication only**: Device certificates are enrolled via EST (Enrollment over Secure Transport); no symmetric keys.
- **Automatic Device Provisioning**: Uses Azure Device Provisioning Service (DPS) with X.509 for secure device registration
   - **Persistent Connection**: Maintains connection to Azure IoT Hub with automatic reconnection
   - **Heartbeat Monitoring**: Sends regular status updates to Azure IoT Hub
   - **Direct Method Support**: Can execute remote commands sent from Azure IoT Hub
   - **Automatic Updates**: Background thread checks for new versions every 5 minutes
   - **Blob Storage Integration**: Downloads updates from Azure Blob Storage
   - **Systemd Service**: Runs as a system service with automatic startup on boot
   - **X.509 certificate renewal**: A systemd timer runs daily and renews the device cert via EST when expiry is within 24 hours; then restarts the IoT service
   - **Comprehensive Logging**: Logs all activities to both system journal and file

## Prerequisites

Before setting up the service, ensure you have:

1. **Raspberry Pi** running Raspberry Pi OS (or compatible Linux distribution)
2. **Azure IoT Hub** with Device Provisioning Service (DPS) enabled
3. **Device Registration** in Azure DPS: ID Scope and an **X.509 enrollment** (registration_id = device ID; the CA that signed the device cert must be registered in DPS).
4. **EST server** for certificate enrollment. DEV uses APIM EST endpoints at `https://apim-dev-spotlight.azure-api.net/cert/est`. Optional: **`env.json`** with `idScope`, `est_server_url`, `est_bootstrap_token`, and device-update fields:
   ```json
   {
       "idScope": "your_dps_id_scope",
       "est_server_url": "https://apim-dev-spotlight.azure-api.net/cert/est",
       "est_bootstrap_token": "your_bootstrap_token",
       "storageAccount": "your_storage_account",
       "containerName": "your_container_name",
       "sasToken": "your_sas_token"
   }
   ```

## Quick Setup

### Automated Setup (Recommended)

**Important:** You can run the scripts directly with bash without making them executable:
```bash
sudo bash set_env.sh
sudo bash test_setup.sh
sudo bash uninstall.sh
```

1. **Clone the repository**:
   ```bash
   git clone https://github.com/samissa730/Azure-IoT-Connection.git
   cd Azure-IoT-Connection
   ```

2. **Run the automated setup**:
   ```bash
   sudo bash set_env.sh
   ```

3. **Device setup uses X.509 (EST)**. When you run device setup, you will be prompted for (or they can come from `env.json`):
   - **ID Scope**: DPS ID Scope (from Azure Portal)
   - **EST Server URL**: defaults to `https://apim-dev-spotlight.azure-api.net/cert/est`
   - **EST Bootstrap Token**: token for initial certificate enrollment
   
   Optional in `env.json`: `idScope`, `est_server_url`, `est_bootstrap_token`, `storageAccount`, `containerName`, `sasToken` (for device updates).

   DEV API reference:
   ```bash
   curl -k https://apim-dev-spotlight.azure-api.net/cert/est/simpleenroll \
     -H "Authorization: Bearer <token>" \
     --data-binary @device.csr \
     -o device.crt

   curl -k https://apim-dev-spotlight.azure-api.net/cert/est/cacerts \
     -H "Authorization: Bearer <token>" \
     -o ca_chain.pem
   ```
   Defaults: Site Name "Lazer", Truck Number = Device Serial, Device ID = Device Serial.

The script will automatically:
   - Update system packages
   - Install Python and Azure IoT dependencies
   - Create all necessary directories and files
   - Copy service scripts to proper locations
   - Set up the systemd service
   - Run device setup (X.509 via EST; prompts or `env.json`)
   - Enable and start the service
   - Verify the installation

**That's it!** Your Azure IoT service will be running and connected to Azure IoT Hub.

### Manual Setup (Alternative)

If you prefer to set up the service manually or need to troubleshoot specific steps, you can follow these manual commands:

```bash
# Update system packages
sudo apt update
sudo apt install -y python3-pip
sudo pip3 install --break-system-packages azure-iot-device

# Create directories
sudo mkdir -p /opt/azure-iot
sudo mkdir -p /etc/azureiotpnp
sudo mkdir -p /var/log

# Copy service files
sudo cp iot_service.py /opt/azure-iot/
sudo cp device_setup.py /opt/azure-iot/
sudo cp download.py /opt/azure-iot/
sudo cp est_client.py /opt/azure-iot/
sudo cp azure-iot-cert-renew.py /opt/azure-iot/
sudo cp azure-iot.service /etc/systemd/system/
sudo cp azure-iot-cert-renew.service /etc/systemd/system/
sudo cp azure-iot-cert-renew.timer /etc/systemd/system/

# Set permissions
sudo chmod +x /opt/azure-iot/iot_service.py
sudo chmod +x /opt/azure-iot/device_setup.py
sudo chmod +x /opt/azure-iot/download.py
sudo chmod +x /opt/azure-iot/azure-iot-cert-renew.py

# Run device setup
sudo python3 /opt/azure-iot/device_setup.py

# Set configuration permissions
sudo chmod 600 /etc/azureiotpnp/provisioning_config.json

# Create log file
sudo touch /var/log/azure-iot-service.log
sudo chmod 644 /var/log/azure-iot-service.log

# Setup and start service
sudo systemctl daemon-reload
sudo systemctl enable azure-iot.service
sudo systemctl start azure-iot.service
sudo systemctl enable azure-iot-cert-renew.timer
sudo systemctl start azure-iot-cert-renew.timer
```

**Note:** The automated setup script (`set_env.sh`) handles all of these steps automatically. Make sure your `env.json` file is properly configured before running the script.

## Service Management

### Check Service Status
```bash
sudo systemctl status azure-iot.service
```

### View Service Logs
```bash
# View real-time logs
sudo journalctl -u azure-iot.service -f

# View log file
sudo tail -f /var/log/azure-iot-service.log
```

### Control the Service
```bash
# Restart service
sudo systemctl restart azure-iot.service

# Stop service
sudo systemctl stop azure-iot.service

# Start service
sudo systemctl start azure-iot.service

# Disable auto-start
sudo systemctl disable azure-iot.service
```

### Certificate renewal (systemd timer)

X.509 device certificates can be renewed automatically so the device does not lose connectivity when the cert expires. The setup installs a **systemd timer** that runs the renewal script once per day (at 03:00). If the cert has less than 24 hours left, the script re-enrolls via EST, writes the new cert/key to `/etc/azureiotpnp/`, and restarts `azure-iot.service`.

**Requirements:** `provisioning_config.json` must contain `estServerUrl` and `estBootstrapToken` (these are saved by `device_setup.py` when you configure the device).

**Check timer status:**
```bash
sudo systemctl status azure-iot-cert-renew.timer
sudo systemctl list-timers azure-iot-cert-renew.timer
```

**View last renewal run:**
```bash
sudo journalctl -u azure-iot-cert-renew.service -n 50
```

**Manual run (test renewal):**
```bash
sudo python3 /opt/azure-iot/azure-iot-cert-renew.py
# Optional: renew when less than 7 days left
sudo python3 /opt/azure-iot/azure-iot-cert-renew.py --threshold 604800
```

**Change schedule:** Edit `/etc/systemd/system/azure-iot-cert-renew.timer` (e.g. `OnCalendar=*-*-* 03:00:00` for daily at 3am, or `OnCalendar=hourly` for hourly), then `sudo systemctl daemon-reload && sudo systemctl restart azure-iot-cert-renew.timer`.

## Configuration

### Main Configuration File
   - **Location**: `/etc/azureiotpnp/provisioning_config.json`
   - **Permissions**: 600 (root read/write only)
   - **Contains**: Azure DPS credentials, device tags, update configuration, and (when set by device_setup) `estServerUrl` and `estBootstrapToken` for automatic certificate renewal

### Service Configuration
   - **Location**: `/etc/systemd/system/azure-iot.service`
   - **User**: root
   - **Restart Policy**: Always (with 30-second delay)
   - **Logging**: Both journal and file
   - **Update Integration**: Background updater runs every 5 minutes

### Log Files
   - **System Journal**: `journalctl -u azure-iot.service`
   - **File Log**: `/var/log/azure-iot-service.log`
   - **Update Logs**: Check background updater activity in system journal

## Troubleshooting

### Common Issues

1. **Service won't start**:
   - Check configuration file syntax: `sudo cat /etc/azureiotpnp/provisioning_config.json | python3 -m json.tool`
   - Verify file permissions: `ls -la /etc/azureiotpnp/`
   - Check service logs: `sudo journalctl -u azure-iot.service -n 50`

2. **Connection failures**:
   - Verify network connectivity: `ping global.azure-devices-provisioning.net`
   - Check Azure DPS credentials
   - Ensure device is registered in Azure DPS

3. **Permission errors**:
   - Verify script permissions: `ls -la /opt/azure-iot/iot_service.py`
   - Check configuration file permissions: `ls -la /etc/azureiotpnp/`

### Debug Mode

To run the service manually for debugging:
```bash
sudo systemctl stop azure-iot.service
cd /opt/azure-iot
sudo python3 iot_service.py
```

### Script-Specific Issues

1. **Script permission denied:**
   ```bash
   sudo bash set_env.sh
   ```

2. **Script not found:**
   ```bash
   ls -la *.sh
   sudo bash set_env.sh
   ```

3. **Script fails with syntax errors:**
   - Ensure you're using bash: `bash set_env.sh`
   - Check for Windows line endings: `dos2unix *.sh`

4. **Configuration input validation fails:**
   - Run device setup and provide ID Scope, EST Server URL, and EST Bootstrap Token (or set them in `env.json`)
   - Ensure the EST server is reachable and the bootstrap token is correct
   - Ensure the device has a valid serial number

## Security Considerations

- Configuration file has restricted permissions (600)
- Service runs as root (required for system operations)
- No new privileges allowed
- Private temporary directory
- X.509 certificate authentication (device certs enrolled via EST)

## Scripts Overview

This repository includes several shell scripts to automate the setup, testing, and management of your Azure IoT service:

### **`set_env.sh`** - Main Setup Script
The primary automation script that handles the complete environment setup.

**What it does:**
- Updates system packages
- Installs Python and Azure IoT dependencies
- Creates all necessary directories and files
- Copies service scripts to proper locations
- Sets up the systemd service
- Runs device setup automatically using `env.json` configuration
- Enables and starts the service
- Verifies the installation

**Usage:**
```bash
sudo bash set_env.sh
```

**Features:**
- Automatic configuration from `env.json` file
- Default values for site name, truck number, and device ID
- Error handling and validation
- Colored output for better readability
- Comprehensive verification steps
- Automatic service management
- Complete automation of all manual steps

### **`test_setup.sh`** - Verification Script
Tests and validates your Azure IoT service setup to ensure everything is working correctly.

**What it does:**
- Validates configuration files and permissions
- Checks service status and dependencies
- Tests network connectivity
- Reviews service logs for errors
- Provides detailed feedback and recommendations

**Usage:**
```bash
sudo bash test_setup.sh
```

**Tests performed:**
- Configuration file existence and syntax
- Service file permissions and executability
- Systemd service status
- Python dependency verification
- Log file setup and permissions
- Network connectivity to Azure DPS
- Service log analysis

### **`uninstall.sh`** - Clean Removal Script
Completely removes the Azure IoT service and cleans up all installed files.

**What it does:**
- Stops and disables the service
- Removes systemd service files
- Deletes configuration and service directories
- Cleans up log files
- Optionally removes Python dependencies

**Usage:**
```bash
sudo bash uninstall.sh
```

**Removal options:**
- Complete service removal
- Optional Python dependency cleanup
- Confirmation prompts for safety
- Comprehensive cleanup verification

## File Structure

```
Azure-IoT-Connection/
├── set_env.sh                    # Automated setup script
├── test_setup.sh                 # Setup verification script
├── uninstall.sh                  # Service removal script
├── iot_service.py                # Main IoT service script
├── device_setup.py               # Device configuration script
├── est_client.py                 # EST client for enrollment/renewal
├── azure-iot-cert-renew.py       # Certificate renewal script (run by timer)
├── azure-iot.service             # Systemd service file
├── azure-iot-cert-renew.service  # Systemd oneshot for cert renewal
├── azure-iot-cert-renew.timer    # Systemd timer (daily)
├── env.json                      # Azure IoT credentials (create this)
├── provisioning_config_template.json  # Configuration template
└── README.md                     # This file
```

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review service logs
3. Verify Azure IoT Hub and DPS configuration
4. Ensure all prerequisites are met

## License

[Add your license information here]