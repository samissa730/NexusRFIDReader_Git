# NexusRFIDReader - PyInstaller Packaging for Raspberry Pi

This document provides comprehensive instructions for packaging the NexusRFIDReader application using PyInstaller and creating a .deb package for easy installation on Raspberry Pi.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Instructions](#detailed-instructions)
- [Package Contents](#package-contents)
- [Installation Process](#installation-process)
- [File Locations](#file-locations)
- [Troubleshooting](#troubleshooting)
- [Uninstallation](#uninstallation)

## Overview

The NexusRFIDReader packaging system creates a standalone executable and packages it into a .deb file for easy installation on Raspberry Pi. The package includes:

- **Standalone Executable**: No Python installation required
- **Automatic Startup**: Application starts on login
- **Desktop Integration**: Available in Applications menu
- **Monitoring**: Automatic restart if application crashes
- **Data Persistence**: Local database and configuration storage

## Prerequisites

### System Requirements
- Raspberry Pi OS (Ubuntu/Debian-based)
- Internet connection for downloading dependencies
- At least 2GB free disk space
- sudo privileges

### Required Files
Ensure these files are present in your project directory:
- `main.py` - Main application entry point
- `NexusRFIDReader.spec` - PyInstaller specification file
- `requirements.txt` - Python dependencies
- `ui/img/icon.ico` - Application icon
- All project source files

## Quick Start

### One-Command Installation
```bash
# 1. Install Python and dependencies
bash scripts/install_python.sh

# 2. Create the package
bash scripts/create_pkg_rpi.sh

# 3. Install the package
sudo apt install ./NexusRFIDReader-1.0.deb

# 4. Reboot to activate
sudo reboot
```

That's it! The application will start automatically on login.

## Detailed Instructions

### Step 1: Install Python and Dependencies

Run the Python installation script to set up the build environment:

```bash
bash scripts/install_python.sh
```

This script will:
- Update package lists
- Install system dependencies
- Install Python 3.9+ (if needed)
- Install PyInstaller
- Install project dependencies
- Verify the installation

**Expected Output:**
```
==============================================================
        NexusRFIDReader Global Python Installer
              For Raspberry Pi
==============================================================

System Information:
   OS: Raspberry Pi OS
   Architecture: arm64
   Kernel: 5.15.0-rpi

Step 1: Updating package lists...
   SUCCESS Package lists updated

Step 2: Installing system dependencies...
   SUCCESS System dependencies installed

Step 3: Checking Python installation...
   Current Python version: 3.9.2
   SUCCESS Python 3.9+ is available

Step 4: Installing PyInstaller...
   SUCCESS PyInstaller installed

Step 5: Installing project dependencies...
   SUCCESS Project dependencies installed from requirements.txt

Step 6: Verifying installation...
   Python version: Python 3.9.2
   Pip version: pip 21.3.1
   PyInstaller version: 4.10
   SUCCESS PyInstaller import test passed
   SUCCESS PySide6 import test passed

==============================================================
            INSTALLATION COMPLETED SUCCESSFULLY!
==============================================================
```

### Step 2: Create the Package

Run the package creation script:

```bash
bash scripts/create_pkg_rpi.sh
```

This script will:
- Build the PyInstaller executable
- Create package directory structure
- Copy application files
- Create monitoring script
- Create desktop entries
- Create autostart configuration
- Build the .deb package
- Clean up build files

**Expected Output:**
```
==============================================================
        NexusRFIDReader Package Builder
              For Raspberry Pi
==============================================================

Package Information:
   Name: NexusRFIDReader
   Version: 1.0
   Architecture: arm64
   Description: Nexus RFID Reader - Advanced RFID scanning and GPS tracking system

Step 1: Building PyInstaller executable...
   SUCCESS PyInstaller found
   SUCCESS Executable built successfully

Step 2: Creating package directory structure...
   SUCCESS Directory structure created

Step 3: Copying application files...
   SUCCESS Application files copied

Step 4: Creating application monitoring script...
   SUCCESS Monitoring script created

Step 5: Creating desktop application entry...
   SUCCESS Desktop entry created

Step 6: Creating autostart configuration...
   SUCCESS Autostart configuration created

Step 7: Creating package control file...
   SUCCESS Control file created

Step 8: Creating post-installation script...
   SUCCESS Post-installation script created

Step 9: Creating pre-removal script...
   SUCCESS Pre-removal script created

Step 10: Building the .deb package...
   SUCCESS Package built successfully

Step 11: Cleaning up build files...
   SUCCESS Build files cleaned up

==============================================================
            PACKAGE CREATED SUCCESSFULLY!
==============================================================

Package File: NexusRFIDReader-1.0.deb
Package Size: 45.2M

Installation Instructions:
   1. Install the package:
      sudo apt install ./NexusRFIDReader-1.0.deb

   2. Reboot to activate autostart:
      sudo reboot

   3. The application will start automatically on login
   4. You can also find it in the Applications menu

Package Contents:
   - Executable: /usr/local/bin/NexusRFIDReader
   - Icon: /usr/share/icons/hicolor/512x512/apps/NexusRFIDReader.ico
   - Desktop Entry: /usr/share/applications/NexusRFIDReader.desktop
   - Data Directory: /var/lib/nexusrfid
   - Log File: /var/log/nexus-rfid-monitor.log
   - Autostart: ~/.config/autostart/monitor-nexus-rfid.desktop

Ready for deployment!
```

### Step 3: Install the Package

Install the created .deb package:

```bash
sudo apt install ./NexusRFIDReader-1.0.deb
```

**Expected Output:**
```
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
Note, selecting 'NexusRFIDReader' instead of './NexusRFIDReader-1.0.deb'
The following NEW packages will be installed:
  NexusRFIDReader
0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.
Need to get 0 B/45.2 MB of archives.
After this operation, 45.2 MB of additional disk space will be used.
Get:1 /home/pi/NexusRFIDReader-1.0.deb NexusRFIDReader 1.0 [45.2 MB]
Selecting previously unselected package NexusRFIDReader.
(Reading database ... 45,123 files and directories currently installed.)
Preparing to unpack .../NexusRFIDReader-1.0.deb ...
Unpacking NexusRFIDReader (1.0) ...
Setting up NexusRFIDReader (1.0) ...
Setting up NexusRFIDReader environment...
Created data directory at /var/lib/nexusrfid
Configured autostart for user: pi
Updated desktop database
Updated icon cache
NexusRFIDReader installation completed successfully!
The application will start automatically on next login.
You can also start it manually from the Applications menu.
```

### Step 4: Reboot to Activate

Reboot the system to activate autostart:

```bash
sudo reboot
```

After reboot, the application will start automatically.

## Package Contents

The .deb package includes the following components:

### Executable Files
- `/usr/local/bin/NexusRFIDReader` - Main application executable
- `/usr/local/bin/monitor_nexus_rfid.sh` - Monitoring script

### Desktop Integration
- `/usr/share/applications/NexusRFIDReader.desktop` - Application menu entry
- `/usr/share/icons/hicolor/512x512/apps/NexusRFIDReader.ico` - Application icon

### Autostart Configuration
- `~/.config/autostart/monitor-nexus-rfid.desktop` - Autostart entry (per user)

### Data and Log Directories
- `/var/lib/nexusrfid/` - Application data directory
- `/var/log/nexus-rfid-monitor.log` - Monitoring script log

## Installation Process

The installation process includes several automated steps:

1. **Package Installation**: Installs the .deb package
2. **Directory Creation**: Creates necessary directories with proper permissions
3. **User Configuration**: Sets up autostart for existing users
4. **Database Updates**: Updates desktop and icon databases
5. **Service Setup**: Configures monitoring and autostart

## File Locations

### Application Files
```
/usr/local/bin/NexusRFIDReader          # Main executable
/usr/local/bin/monitor_nexus_rfid.sh    # Monitoring script
/usr/share/applications/NexusRFIDReader.desktop  # Desktop entry
/usr/share/icons/hicolor/512x512/apps/NexusRFIDReader.ico  # Icon
```

### Data Files
```
/var/lib/nexusrfid/                     # Application data directory
/var/lib/nexusrfid/database.db          # SQLite database (created on first run)
/var/log/nexus-rfid-monitor.log         # Monitoring log
~/.nexusrfid/                           # User configuration directory
~/.nexusrfid/crash.dump                 # Crash dump file (if crashes occur)
```

### Configuration Files
```
~/.config/autostart/monitor-nexus-rfid.desktop  # Autostart configuration
```

## Troubleshooting

### Common Issues

#### 1. PyInstaller Build Fails
**Problem**: PyInstaller fails to build the executable
**Solution**:
```bash
# Check if all dependencies are installed
pip3 list | grep -E "(PySide6|PyInstaller)"

# Reinstall PyInstaller
pip3 uninstall pyinstaller
pip3 install pyinstaller

# Try building again
bash scripts/create_pkg_rpi.sh
```

#### 2. Package Installation Fails
**Problem**: `sudo apt install ./NexusRFIDReader-1.0.deb` fails
**Solution**:
```bash
# Check package dependencies
dpkg -I NexusRFIDReader-1.0.deb

# Install missing dependencies
sudo apt update
sudo apt install -f

# Try installation again
sudo apt install ./NexusRFIDReader-1.0.deb
```

#### 3. Application Does Not Start
**Problem**: Application does not start automatically
**Solution**:
```bash
# Check if autostart is configured
ls -la ~/.config/autostart/

# Check monitoring script log
tail -f /var/log/nexus-rfid-monitor.log

# Start manually to test
/usr/local/bin/NexusRFIDReader
```

#### 4. Permission Issues
**Problem**: Permission denied errors
**Solution**:
```bash
# Fix data directory permissions
sudo chown -R pi:pi /var/lib/nexusrfid
sudo chmod -R 755 /var/lib/nexusrfid

# Fix log file permissions
sudo chown pi:pi /var/log/nexus-rfid-monitor.log
sudo chmod 644 /var/log/nexus-rfid-monitor.log
```

### Debug Mode

To run the application in debug mode:

```bash
# Run with console output
/usr/local/bin/NexusRFIDReader --debug

# Check system logs
journalctl -u nexus-rfid -f

# Check application logs
tail -f ~/.nexusrfid/rfid.log
```

## Uninstallation

To completely remove the application:

```bash
# Run the uninstall script
sudo bash scripts/uninstall_pkg_rpi.sh
```

This will:
- Stop all running processes
- Remove the package
- Remove all application files
- Clean up autostart entries
- Remove log files (with confirmation)
- Update system databases

**Expected Output:**
```
==============================================================
            NexusRFIDReader Uninstaller
              For Raspberry Pi
==============================================================

WARNING: This will completely remove NexusRFIDReader and all its data!
This action cannot be undone.

Are you sure you want to continue? (y/N): y

Step 1: Stopping NexusRFIDReader processes...
   Stopping application processes...
   No running NexusRFIDReader processes found
   Stopping monitoring processes...
   No running monitoring processes found
   SUCCESS All processes stopped

Step 2: Removing package using dpkg...
   SUCCESS Package removed

Step 3: Purging configuration files...
   SUCCESS Configuration files purged

Step 4: Removing application files...
   SUCCESS Removed executable: /usr/local/bin/NexusRFIDReader
   SUCCESS Removed monitoring script: /usr/local/bin/monitor_nexus_rfid.sh
   SUCCESS Removed desktop entry: /usr/share/applications/NexusRFIDReader.desktop
   SUCCESS Removed icon: /usr/share/icons/hicolor/512x512/apps/NexusRFIDReader.ico

Step 5: Removing data directories...
   Found data directory: /var/lib/nexusrfid
   WARNING: This directory may contain important data!
   Remove data directory? (y/N): y
   SUCCESS Removed data directory: /var/lib/nexusrfid

Step 6: Removing autostart entries...
   SUCCESS Removed autostart for user: pi

Step 7: Cleaning up log files...
   Found log file: /var/log/nexus-rfid-monitor.log
   Remove log file? (y/N): y
   SUCCESS Removed log file: /var/log/nexus-rfid-monitor.log

Step 8: Updating system databases...
   SUCCESS Updated desktop database
   SUCCESS Updated icon cache

Step 9: Cleaning up package cache...
   SUCCESS Package cache cleaned

Step 10: Final verification...
   SUCCESS All application files removed successfully

==============================================================
            UNINSTALLATION COMPLETED!
==============================================================

Summary of removed components:
   - Application executable
   - Monitoring script
   - Desktop entry
   - Application icon
   - Autostart configurations
   - Package database entries

NexusRFIDReader has been completely removed!
```

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review the log files in `/var/log/nexus-rfid-monitor.log`
3. Check application logs in `~/.nexusrfid/rfid.log`
4. Verify system requirements and dependencies

## License

This packaging system is part of the NexusRFIDReader project. Please refer to the main project license for usage terms.
