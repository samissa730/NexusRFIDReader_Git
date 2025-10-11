# NexusRFID Reader

A comprehensive RFID and GPS data reading application built with PySide6, featuring automatic restart capabilities for production environments.

## Features

- **RFID Tag Reading**: Live RFID tag scanning and processing
- **GPS Integration**: GPS module support for location tracking
- **Cross-Platform**: Supports Windows, Linux, and Raspberry Pi
- **Auto-Restart**: Built-in autorestart mechanisms for production deployment
- **Modern UI**: Qt Designer-based user interface
- **Crash Recovery**: Automatic restart on application crashes

## Requirements

- Python 3.7+
- PySide6
- RFID Reader hardware
- GPS module (optional)

## Quick Start

### Development Environment

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   python main.py
   ```

### Production Environment

The application includes comprehensive autorestart mechanisms for different platforms:

## Autorestart Mechanisms

### Windows Production Setup

1. **Build the executable:**
   ```bash
   # Run the build script
   scripts\build_executable.bat
   ```

2. **Setup autorestart:**
   ```bash
   # Place the executable in the project root, then run:
   scripts\setup_windows_autorestart.bat
   ```

**How it works:**
- Creates a monitoring script that checks every 10 seconds if the application is running
- Uses Windows Task Scheduler to run the monitor at user logon
- Automatically restarts the application if it crashes

**Uninstall:**
```bash
scripts\uninstall_windows_autorestart.bat
```

### Linux/Ubuntu Production Setup

#### Option 1: Systemd Service (Recommended)

1. **Build the executable:**
   ```bash
   scripts/build_executable.sh
   ```

2. **Install as systemd service:**
   ```bash
   sudo scripts/install_service.sh
   ```

**How it works:**
- Creates a systemd service (`nexusrfid.service`)
- Automatically restarts every 5 seconds if the application crashes
- Starts on system boot
- Logs output to systemd journal

**Manage the service:**
```bash
# Check status
systemctl status nexusrfid.service

# View logs
journalctl -u nexusrfid.service -f

# Stop/start/restart
sudo systemctl stop nexusrfid.service
sudo systemctl start nexusrfid.service
sudo systemctl restart nexusrfid.service
```

**Uninstall:**
```bash
sudo scripts/uninstall_service.sh
```

#### Option 2: Package Installation

1. **Create package:**
   ```bash
   scripts/create_pkg_ubuntu.sh
   ```

2. **Install package:**
   ```bash
   sudo apt install ./NexusRFIDReader-1.0.deb
   ```

**Uninstall package:**
```bash
sudo scripts/uninstall_pkg_ubuntu.sh
```

### Raspberry Pi Production Setup

#### Option 1: Monitoring Script (Lightweight)

1. **Build the executable:**
   ```bash
   scripts/build_executable.sh
   ```

2. **Create package:**
   ```bash
   scripts/create_pkg_rpi.sh
   ```

3. **Install package:**
   ```bash
   sudo apt install ./NexusRFIDReader-1.0.deb
   ```

**How it works:**
- Creates a monitoring script that checks every 5 seconds
- Uses desktop autostart to run the monitor on user login
- More lightweight than systemd for Raspberry Pi

**Uninstall:**
```bash
sudo scripts/uninstall_pkg_rpi.sh
```

#### Option 2: Systemd Service

Same as Linux/Ubuntu systemd service setup above.

## Build and Packaging

### Build Executable

**Windows:**
```bash
scripts\build_executable.bat
```

**Linux/Raspberry Pi:**
```bash
scripts/build_executable.sh
```

### Package Creation

**Ubuntu (.deb package):**
```bash
scripts/create_pkg_ubuntu.sh
```

**Raspberry Pi (.deb package):**
```bash
scripts/create_pkg_rpi.sh
```

## Testing

### Run Unit Tests

Unit tests live under the `UnitTests/` directory and use Python's built-in `unittest` framework.

1. **Activate virtual environment (optional):**
   ```bash
   # Windows PowerShell
   .\venv\Scripts\Activate.ps1
   # or CMD
   .\venv\Scripts\activate.bat
   
   # Linux/Raspberry Pi
   source venv/bin/activate
   ```

2. **Run all tests:**
   ```bash
   python -m unittest discover -s UnitTests -p "test_*.py" -v
   ```

3. **Run specific tests:**
   ```bash
   python -m unittest UnitTests.test_common -v
   ```

## Autorestart Comparison

| Environment | Mechanism | Check Interval | Boot Integration | Privileges |
|-------------|-----------|----------------|------------------|------------|
| **Development** | None (manual) | N/A | No | User |
| **Windows Prod** | Task Scheduler + Monitor | 10 seconds | User logon | Highest |
| **Linux Prod** | systemd service | 5 seconds | System boot | Root |
| **Raspberry Pi** | Desktop autostart + Monitor | 5 seconds | User logon | User |

## Troubleshooting

### Windows
- Ensure you run setup scripts as Administrator
- Check Task Scheduler for the `NexusRFIDReaderMonitor` task
- Monitor script logs are in the application directory

### Linux/Raspberry Pi
- Check systemd service status: `systemctl status nexusrfid.service`
- View logs: `journalctl -u nexusrfid.service -f`
- Ensure executable has proper permissions: `chmod +x NexusRFIDReader`

### Common Issues
- **Permission denied**: Run with appropriate privileges (sudo for Linux, Administrator for Windows)
- **Service not starting**: Check logs and ensure all dependencies are installed
- **Autostart not working**: Verify autostart configuration and user permissions

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Add your license information here]