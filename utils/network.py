"""
Network utilities for detecting active tunnels and managing interface priorities.
Priority order: Ethernet > WiFi > Cellular
"""

import subprocess
import socket
import psutil
import platform
import re
from utils.logger import logger


# Map interface prefixes to tunnel types
INTERFACE_MAP = {
    "eth": "Ethernet",
    "en": "Ethernet",
    "wlan": "Wifi",
    "wl": "Wifi",
    "wwan": "Cellular",
    "usb": "Cellular",
    "cdc": "Cellular",
}


def get_tunnel_type(interface):
    """Determine tunnel/connection type based on interface name."""
    for prefix, tunnel in INTERFACE_MAP.items():
        if interface.lower().startswith(prefix):
            return tunnel
    # Windows-specific: check interface name directly
    iface_lower = interface.lower()
    if "ethernet" in iface_lower:
        return "Ethernet"
    elif "wi-fi" in iface_lower or "wireless" in iface_lower or "wlan" in iface_lower:
        return "Wifi"
    elif "mobile" in iface_lower or "cellular" in iface_lower or "wwan" in iface_lower:
        return "Cellular"
    return None


def has_internet(interface):
    """Check if interface has internet connectivity by pinging 8.8.8.8 through the specific interface"""
    try:
        # Get interface IP first
        interfaces = psutil.net_if_addrs()
        if interface not in interfaces:
            return False
        
        # Find IPv4 address for this interface
        ipv4_addr = None
        for addr in interfaces[interface]:
            if addr.family == socket.AF_INET:
                ipv4_addr = addr.address
                break
        
        if not ipv4_addr:
            return False
        
        if platform.system() == "Windows":
            # Windows: Use ping with -S flag to specify source IP
            result = subprocess.run(
                ["ping", "-n", "2", "-w", "2000", "-S", ipv4_addr, "8.8.8.8"],
                capture_output=True,
                timeout=5,
                text=True
            )
            return result.returncode == 0
        else:
            # Linux: Use ping with -I flag to bind to specific interface
            result = subprocess.run(
                ["ping", "-I", interface, "-c", "2", "-W", "2", "8.8.8.8"],
                capture_output=True,
                timeout=5,
                text=True
            )
            return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def detect_active_tunnels():
    """Detect active network tunnels/interfaces with internet connectivity."""
    active_tunnels = set()

    interfaces = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for iface, addrs in interfaces.items():
        # Skip loopback interface
        if iface == 'lo':
            continue
            
        if iface not in stats or not stats[iface].isup:
            continue

        # Check if interface has an IPv4 address
        if not any(addr.family == socket.AF_INET for addr in addrs):
            continue

        if has_internet(iface):
            tunnel = get_tunnel_type(iface)
            if tunnel:
                active_tunnels.add(tunnel)

    return active_tunnels


def get_active_interfaces():
    """Get all active network interfaces with IPv4 addresses."""
    interfaces = []
    net_if_addrs = psutil.net_if_addrs()
    net_if_stats = psutil.net_if_stats()
    
    for iface, addrs in net_if_addrs.items():
        # Skip loopback interface
        if iface == 'lo':
            continue
            
        # Check if interface is up
        if iface not in net_if_stats or not net_if_stats[iface].isup:
            continue
        
        # Check if interface has IPv4 address
        ipv4_addr = None
        for addr in addrs:
            if addr.family == socket.AF_INET:
                ipv4_addr = addr.address
                break
        
        if ipv4_addr:
            interfaces.append({
                'name': iface,
                'ip': ipv4_addr,
                'status': 'UP' if net_if_stats[iface].isup else 'DOWN'
            })
    
    return interfaces


def test_interface_ping(interface_name, interface_ip):
    """
    Test internet connectivity through a specific interface by pinging 8.8.8.8.
    Returns True if ping succeeds, False otherwise.
    """
    try:
        if platform.system() == "Linux":
            # Linux: Use ping with -I flag to bind to specific interface
            result = subprocess.run(
                ['ping', '-I', interface_name, '-c', '2', '-W', '2', '8.8.8.8'],
                capture_output=True,
                timeout=5,
                text=True
            )
            return result.returncode == 0
        elif platform.system() == "Windows":
            # Windows: Use ping with -S flag to specify source IP
            result = subprocess.run(
                ['ping', '-n', '2', '-w', '2000', '-S', interface_ip, '8.8.8.8'],
                capture_output=True,
                timeout=5,
                text=True
            )
            return result.returncode == 0
        else:
            # For other systems, try generic ping
            result = subprocess.run(
                ['ping', '-c', '2', '8.8.8.8'],
                capture_output=True,
                timeout=5,
                text=True
            )
            return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception as e:
        logger.debug(f"Error testing {interface_name}: {e}")
        return False


def get_interface_priority_type(interface_name):
    """Get priority type for interface ordering (1=Ethernet, 2=WiFi, 3=Cellular)."""
    iface_lower = interface_name.lower()
    
    if iface_lower.startswith('eth') or iface_lower.startswith('en'):
        return 1  # Ethernet - highest priority
    elif iface_lower.startswith('wlan') or iface_lower.startswith('wl'):
        return 2  # WiFi - medium priority
    elif iface_lower.startswith('usb') or iface_lower.startswith('wwan') or iface_lower.startswith('cdc'):
        return 3  # Cellular - lowest priority
    else:
        return 99  # Unknown - lowest priority


def get_current_default_interface():
    """Get the current default network interface."""
    try:
        if platform.system() == "Linux":
            # Get default route interface
            result = subprocess.run(
                ['ip', 'route', 'show', 'default'],
                capture_output=True,
                timeout=5,
                text=True
            )
            if result.returncode == 0 and result.stdout:
                # Parse output: default via 192.168.1.1 dev eth0 proto dhcp metric 100
                match = re.search(r'dev\s+(\w+)', result.stdout)
                if match:
                    return match.group(1)
        elif platform.system() == "Windows":
            # Use PowerShell to get default interface
            ps_cmd = 'Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Select-Object -First 1 | Get-NetAdapter | Select-Object -ExpandProperty Name'
            result = subprocess.run(
                ['powershell', '-Command', ps_cmd],
                capture_output=True,
                timeout=5,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    except Exception as e:
        logger.debug(f"Warning: Could not determine current default interface: {e}")
    return None


def check_priorities_need_update():
    """
    Check if interface priorities need to be updated.
    Returns True if priorities need updating, False otherwise.
    """
    try:
        # Get all active interfaces with internet
        interfaces = get_active_interfaces()
        working_interfaces = []
        
        for iface in interfaces:
            if test_interface_ping(iface['name'], iface['ip']):
                tunnel_type = get_tunnel_type(iface['name'])
                if tunnel_type:
                    working_interfaces.append({
                        'name': iface['name'],
                        'ip': iface['ip'],
                        'type': tunnel_type
                    })
        
        if len(working_interfaces) <= 1:
            # Only one or no working interfaces, no need to reorder
            return False
        
        # Get current default interface
        current_default = get_current_default_interface()
        if not current_default:
            # Can't determine default, assume update needed
            return True
        
        # Check if current default is the highest priority interface
        sorted_interfaces = sorted(working_interfaces, key=lambda x: get_interface_priority_type(x['name']))
        highest_priority_interface = sorted_interfaces[0]
        
        # If current default is not the highest priority, update needed
        if current_default != highest_priority_interface['name']:
            return True
        
        return False
    except Exception as e:
        logger.debug(f"Error checking priorities: {e}")
        return False


def configure_network_priorities():
    """
    Check and update network interface priorities if needed.
    Priority order: Ethernet > WiFi > Cellular
    Returns dict with success status and information about configured interfaces.
    """
    try:
        # Get all active interfaces
        interfaces = get_active_interfaces()
        
        if not interfaces:
            logger.debug("No active network interfaces found")
            return {'success': False, 'working': [], 'configured': []}
        
        # Test each interface for internet connectivity
        working_interfaces = []
        for iface in interfaces:
            if test_interface_ping(iface['name'], iface['ip']):
                tunnel_type = get_tunnel_type(iface['name'])
                if tunnel_type:
                    working_interfaces.append({
                        'name': iface['name'],
                        'ip': iface['ip'],
                        'type': tunnel_type
                    })
        
        if not working_interfaces:
            logger.debug("No working interfaces with internet connectivity found")
            return {'success': False, 'working': [], 'configured': []}
        
        # Check if priorities need updating
        if not check_priorities_need_update():
            logger.debug("Interface priorities are already optimal")
            return {
                'success': True,
                'working': [iface['name'] for iface in working_interfaces],
                'configured': []
            }
        
        # Reorder interface priorities
        if reorder_interface_priorities(working_interfaces):
            configured_names = [iface['name'] for iface in working_interfaces]
            logger.info(f"Network priorities configured successfully. Working interfaces: {', '.join(configured_names)}")
            return {
                'success': True,
                'working': [iface['name'] for iface in working_interfaces],
                'configured': configured_names
            }
        else:
            logger.warning("Failed to update interface priorities")
            return {
                'success': False,
                'working': [iface['name'] for iface in working_interfaces],
                'configured': []
            }
    except Exception as e:
        logger.error(f"Error configuring network priorities: {e}")
        return {'success': False, 'working': [], 'configured': []}


def reorder_interface_priorities(working_interfaces):
    """
    Reorder network interface priorities without reboot.
    Priority: Ethernet (1) > WiFi (2) > Cellular (3)
    Returns True if successful, False otherwise.
    """
    if not working_interfaces:
        return False
    
    # Sort interfaces by priority type
    sorted_interfaces = sorted(working_interfaces, key=lambda x: get_interface_priority_type(x['name']))
    
    try:
        if platform.system() == "Linux":
            return reorder_linux_priorities(sorted_interfaces)
        elif platform.system() == "Windows":
            return reorder_windows_priorities(sorted_interfaces)
        else:
            logger.debug("Interface priority reordering not supported on this platform")
            return False
    except Exception as e:
        logger.error(f"Error reordering interface priorities: {e}")
        return False


def reorder_linux_priorities(sorted_interfaces):
    """Reorder interface priorities on Linux using ip route metrics."""
    try:
        # Assign metrics: lower metric = higher priority
        # Ethernet: 100, WiFi: 200, Cellular: 300
        metric_map = {1: 100, 2: 200, 3: 300, 99: 400}
        
        success_count = 0
        
        for iface in sorted_interfaces:
            priority = get_interface_priority_type(iface['name'])
            metric = metric_map.get(priority, 400)
            
            # Get default route for this interface
            result = subprocess.run(
                ['ip', 'route', 'show', 'default', 'dev', iface['name']],
                capture_output=True,
                timeout=5,
                text=True
            )
            
            if result.returncode == 0 and result.stdout:
                # Delete existing default route for this interface
                del_result = subprocess.run(
                    ['sudo', '-n', 'ip', 'route', 'del', 'default', 'dev', iface['name']],
                    capture_output=True,
                    timeout=5,
                    text=True
                )
                
                # Add default route with new metric
                # Extract gateway from original route
                match = re.search(r'via\s+([\d.]+)', result.stdout)
                if match:
                    gateway = match.group(1)
                    add_result = subprocess.run(
                        ['sudo', '-n', 'ip', 'route', 'add', 'default', 'via', gateway, 'dev', iface['name'], 'metric', str(metric)],
                        capture_output=True,
                        timeout=5,
                        text=True
                    )
                    if add_result.returncode == 0:
                        logger.debug(f"Set {iface['name']} ({iface['type']}) metric to {metric}")
                        success_count += 1
                    else:
                        logger.debug(f"Warning: Failed to set metric for {iface['name']}: {add_result.stderr}")
                else:
                    # Try without gateway (direct connection)
                    add_result = subprocess.run(
                        ['sudo', '-n', 'ip', 'route', 'add', 'default', 'dev', iface['name'], 'metric', str(metric)],
                        capture_output=True,
                        timeout=5,
                        text=True
                    )
                    if add_result.returncode == 0:
                        logger.debug(f"Set {iface['name']} ({iface['type']}) metric to {metric}")
                        success_count += 1
                    else:
                        logger.debug(f"Warning: Failed to set metric for {iface['name']}: {add_result.stderr}")
            else:
                # No default route exists for this interface, try to add one
                # First, try to get gateway from interface's network
                gateway_result = subprocess.run(
                    ['ip', 'route', 'show', 'dev', iface['name']],
                    capture_output=True,
                    timeout=5,
                    text=True
                )
                if gateway_result.returncode == 0 and gateway_result.stdout:
                    # Try to find a gateway in the routes
                    gateway_match = re.search(r'via\s+([\d.]+)', gateway_result.stdout)
                    if gateway_match:
                        gateway = gateway_match.group(1)
                        add_result = subprocess.run(
                            ['sudo', '-n', 'ip', 'route', 'add', 'default', 'via', gateway, 'dev', iface['name'], 'metric', str(metric)],
                            capture_output=True,
                            timeout=5,
                            text=True
                        )
                        if add_result.returncode == 0:
                            logger.debug(f"Added default route for {iface['name']} ({iface['type']}) with metric {metric}")
                            success_count += 1
        
        return success_count > 0
    except Exception as e:
        logger.error(f"Error in Linux priority reordering: {e}")
        return False


def reorder_windows_priorities(sorted_interfaces):
    """Reorder interface priorities on Windows using interface metrics."""
    try:
        # Assign metrics: lower metric = higher priority
        # Ethernet: 10, WiFi: 20, Cellular: 30
        metric_map = {1: 10, 2: 20, 3: 30, 99: 40}
        
        for iface in sorted_interfaces:
            priority = get_interface_priority_type(iface['name'])
            metric = metric_map.get(priority, 40)
            
            # Set interface metric using netsh
            result = subprocess.run(
                ['netsh', 'interface', 'ip', 'set', 'interface', iface['name'], 'metric=' + str(metric)],
                capture_output=True,
                timeout=5,
                text=True
            )
            
            if result.returncode == 0:
                logger.debug(f"Set {iface['name']} ({iface['type']}) metric to {metric}")
            else:
                logger.debug(f"Warning: Failed to set metric for {iface['name']}: {result.stderr}")
        
        return True
    except Exception as e:
        logger.error(f"Error in Windows priority reordering: {e}")
        return False
