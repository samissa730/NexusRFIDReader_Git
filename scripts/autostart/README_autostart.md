## Autostart and Build for NexusRFIDReader

### Build executables (Windows/Linux/RPi)

- Windows:
  - Edit/spec review: `NexusRFIDReader.spec`
  - Build: `scripts\build\win\build.bat`
  - Output: `dist\NexusRFIDReader\NexusRFIDReader.exe`

- Linux/RPi:
  - Ensure PyInstaller installed in the environment
  - Build: `bash scripts/build/linux/build.sh`
  - Output: `dist/NexusRFIDReader/NexusRFIDReader`

### RPi autostart (Develop - from source)

Install:
```bash
sudo bash scripts/autostart/rpi/dev/install_dev_service.sh /absolute/path/to/NexusRFIDReader [user]
```

Uninstall:
```bash
sudo bash scripts/autostart/rpi/dev/uninstall_dev_service.sh [user]
```

### RPi autostart (Product - packaged executable)

Install:
```bash
sudo bash scripts/autostart/rpi/product/install_prod_service.sh /path/to/NexusRFIDReader [user]
```

Uninstall:
```bash
sudo bash scripts/autostart/rpi/product/uninstall_prod_service.sh [user]
```

### Windows autostart (Product)

Install:
```bat
scripts\autostart\windows\install_autostart.bat "C:\\path\\to\\NexusRFIDReader.exe"
```

Uninstall:
```bat
scripts\autostart\windows\uninstall_autostart.bat
```

## Autostart for NexusRFIDReader (RPi and Windows)

This folder provides two autostart setups for the NexusRFIDReader project:

- Develop environment (RPi): runs the Python app from source using your virtual environment
- Product environment (RPi/Windows): runs the built executable after reboot

### RPi - Develop environment (run from source)

Prerequisites:
- A working venv with dependencies installed
- The device auto-logs into a desktop session (needed for PySide6 GUI)

Install service:
```bash
cd scripts/autostart/rpi/dev
sudo bash install_dev_service.sh /absolute/path/to/NexusRFIDReader
```

Notes:
- The script attempts to use your venv at `<project>/venv` first, then system `python3`.
- The service starts after network is online and targets the X session via `graphical.target`.
- If you use a user other than `pi`, pass it as the second arg.

Uninstall:
```bash
cd scripts/autostart/rpi/dev
sudo bash uninstall_dev_service.sh
```

Check status/logs:
```bash
sudo -u $(logname) systemctl --user status nexusrfidreader-dev
sudo -u $(logname) journalctl --user -u nexusrfidreader-dev -f
```

### RPi - Product environment (run packaged executable)

Assumptions:
- You have built/installed the executable (e.g. to `/usr/local/bin/NexusRFIDReader`)

Install service:
```bash
cd scripts/autostart/rpi/product
sudo bash install_prod_service.sh /path/to/NexusRFIDReader [username]
```

Uninstall:
```bash
cd scripts/autostart/rpi/product
sudo bash uninstall_prod_service.sh
```

Check status/logs:
```bash
sudo -u $(logname) systemctl --user status nexusrfidreader-prod
sudo -u $(logname) journalctl --user -u nexusrfidreader-prod -f
```

### Windows - Product environment (run packaged executable)

Add autostart (current user):
```bat
scripts\autostart\windows\install_autostart.bat "C:\\path\\to\\NexusRFIDReader.exe"
```

Remove autostart:
```bat
scripts\autostart\windows\uninstall_autostart.bat
```

Notes:
- Windows setup uses the `Run` registry key under HKCU. No admin needed.
- If you prefer Startup folder shortcut, you can adapt the batch script accordingly.


