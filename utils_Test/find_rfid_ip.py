#!/usr/bin/env python3
"""
RFID Reader IP Finder

This script uses arp-scan to scan the 169.254.0.0/16 network range (Link-Local addresses)
to find connected RFID readers. It identifies RFID readers by detecting MAC addresses
associated with "Zebra Technologies" or "Impinj" vendors.

Usage:
    sudo python3 find_rfid_ip.py [--interface eth0] [--network 169.254.0.0/16]
    
Output:
    Prints the IP address and product name for each detected RFID reader.
"""

import subprocess
import re
import sys
import platform
import os
from typing import List, Dict, Optional


class RFIDIPFinder:
    """Finds RFID reader IP addresses using arp-scan."""
    
    # RFID vendor keywords to look for in arp-scan output
    RFID_VENDORS = ['Zebra', 'Impinj']
    
    def __init__(self, network_range: str = "169.254.0.0/16", interface: Optional[str] = None, debug: bool = False):
        """
        Initialize the RFID IP finder.
        
        Args:
            network_range: Network range to scan (default: 169.254.0.0/16 for Link-Local)
            interface: Network interface to use (default: auto-detect or 'eth0')
            debug: Enable debug output (default: False)
        """
        self.network_range = network_range
        self.interface = interface or self._detect_interface()
        self.readers_found = []
        self.debug = debug
    
    def _detect_interface(self) -> str:
        """Auto-detect network interface, default to eth0."""
        try:
            # Try to get default route interface
            result = subprocess.run(
                ['ip', 'route', 'show', 'default'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout:
                # Extract interface from route output
                match = re.search(r'dev\s+(\w+)', result.stdout)
                if match:
                    return match.group(1)
        except:
            pass
        
        # Try common interface names
        for iface in ['eth0', 'eth1', 'enp0s3', 'enp0s8']:
            try:
                # Check if interface exists
                result = subprocess.run(
                    ['ip', 'link', 'show', iface],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    return iface
            except:
                continue
        
        # Default fallback
        return 'eth0'
    
    def _check_arpscan_available(self) -> bool:
        """Check if arp-scan is available on the system."""
        try:
            result = subprocess.run(
                ['arp-scan', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _check_sudo_privileges(self) -> bool:
        """Check if running with sudo/root privileges."""
        return os.geteuid() == 0 if hasattr(os, 'geteuid') else False
    
    def _run_arpscan(self) -> Optional[str]:
        """
        Run arp-scan to discover hosts on the network.
        
        Returns:
            arp-scan output as string, or None if scan fails
        """
        if not self._check_arpscan_available():
            print("Error: arp-scan is not installed or not available in PATH", file=sys.stderr)
            print("Please install arp-scan: sudo apt-get install arp-scan", file=sys.stderr)
            return None
        
        # Check if we have sudo privileges
        has_sudo = self._check_sudo_privileges()
        
        if self.debug:
            print(f"DEBUG: Running with sudo privileges: {has_sudo}", file=sys.stderr)
            print(f"DEBUG: UID: {os.getuid() if hasattr(os, 'getuid') else 'N/A'}, EUID: {os.geteuid() if hasattr(os, 'geteuid') else 'N/A'}", file=sys.stderr)
            print(f"DEBUG: Using interface: {self.interface}", file=sys.stderr)
        
        if not has_sudo:
            print("Warning: Not running with sudo privileges.", file=sys.stderr)
            print("Attempting to run arp-scan directly (may fail if privileges required)...", file=sys.stderr)
        
        # arp-scan requires sudo/root privileges
        # Build command: arp-scan --interface=<interface> <network_range>
        # Don't use --quiet so we can see progress and debug output
        cmd = ['arp-scan', '--interface', self.interface, self.network_range]
        
        if self.debug:
            print(f"DEBUG: Running command: {' '.join(cmd)}", file=sys.stderr)
            print(f"DEBUG: Network range: {self.network_range}", file=sys.stderr)
            print(f"DEBUG: Starting arp-scan subprocess...", file=sys.stderr)
        
        try:
            # Run with longer timeout - arp-scan on /16 network can take time
            # Also use stderr=subprocess.STDOUT to capture both streams
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # Timeout after 300 seconds (5 minutes) for large network ranges
                bufsize=1  # Line buffered
            )
            
            # Combine stdout and stderr - arp-scan outputs header info to stderr
            combined_output = ""
            if result.stderr:
                combined_output += result.stderr
            if result.stdout:
                combined_output += "\n" + result.stdout if combined_output else result.stdout
            
            if self.debug:
                print(f"DEBUG: Return code: {result.returncode}", file=sys.stderr)
                print(f"DEBUG: stdout length: {len(result.stdout)} chars", file=sys.stderr)
                print(f"DEBUG: stderr length: {len(result.stderr)} chars", file=sys.stderr)
                print(f"DEBUG: Combined output length: {len(combined_output)} chars", file=sys.stderr)
                
                if result.stderr:
                    print(f"DEBUG: stderr content:\n{result.stderr}", file=sys.stderr)
                if result.stdout:
                    print(f"DEBUG: stdout content:\n{result.stdout}", file=sys.stderr)
                if combined_output:
                    print(f"DEBUG: Combined full output:\n{combined_output}", file=sys.stderr)
            
            # Check stderr for actual errors (before combining)
            error_output = result.stderr.strip() if result.stderr else ""
            
            # Check for permission errors
            if error_output and ("permission" in error_output.lower() or 
                                "Operation not permitted" in error_output or
                                "pcap_activate" in error_output.lower()):
                if not has_sudo:
                    print("\nError: arp-scan requires root/sudo privileges to scan networks.", file=sys.stderr)
                    print("Please run this script with sudo:", file=sys.stderr)
                    print("  sudo python3 utils_Test/find_rfid_ip.py", file=sys.stderr)
                else:
                    print(f"\nError: Permission issue detected even with sudo: {error_output}", file=sys.stderr)
                return None
            
            # Return combined output - parsing will extract the actual data
            # arp-scan outputs results to stdout, header info to stderr
            # We need both for complete parsing
            return combined_output
            
        except subprocess.TimeoutExpired as e:
            if self.debug:
                print("DEBUG: Timeout exception caught", file=sys.stderr)
                print(f"DEBUG: Timeout after 300 seconds", file=sys.stderr)
            if not has_sudo:
                print("\nError: arp-scan timed out (likely waiting for sudo password or missing privileges).", file=sys.stderr)
                print("arp-scan requires root privileges for network scanning.", file=sys.stderr)
                print("Please run this script with sudo:", file=sys.stderr)
                print("  sudo python3 utils_Test/find_rfid_ip.py", file=sys.stderr)
            else:
                print("Error: arp-scan timed out after 300 seconds", file=sys.stderr)
                print("This may indicate network issues or a large network range.", file=sys.stderr)
                print("Try running arp-scan manually to verify it works:", file=sys.stderr)
                print(f"  sudo arp-scan --interface={self.interface} {self.network_range}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Error running arp-scan: {e}", file=sys.stderr)
            if not has_sudo:
                print("Tip: Try running with sudo: sudo python3 utils_Test/find_rfid_ip.py", file=sys.stderr)
            return None
    
    def _parse_arpscan_output(self, arpscan_output: str) -> List[Dict[str, str]]:
        """
        Parse arp-scan output to extract RFID reader IP addresses and vendor names.
        
        arp-scan output format:
        169.254.10.1    c4:7d:cc:68:d8:93       Zebra Technologies Inc
        
        Args:
            arpscan_output: The output from arp-scan command
            
        Returns:
            List of dictionaries with 'ip', 'product', 'vendor', and 'mac' keys
        """
        readers = []
        lines = arpscan_output.split('\n')
        
        if self.debug:
            print(f"DEBUG: Parsing {len(lines)} lines from arp-scan output", file=sys.stderr)
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            if self.debug and i < 30:  # Debug first 30 lines
                print(f"DEBUG: Line {i}: {line[:80]}", file=sys.stderr)
            
            # Skip header lines and summary lines (but keep for debug)
            # Note: "Interface:" and "Starting" appear in stderr output, "packets" in summary
            if any(skip in line.lower() for skip in ['interface:', 'type:', 'mac:', 'ipv4:', 'starting arp-scan', 'ending', 'packets sent', 'hosts found']):
                if self.debug:
                    print(f"DEBUG: Skipping header/summary line: {line[:80]}", file=sys.stderr)
                continue
            
            # Parse arp-scan output format: IP    MAC    VENDOR
            # Example: 169.254.10.1    c4:7d:cc:68:d8:93       Zebra Technologies Inc
            # Use regex to match IP, MAC, and vendor (handles variable whitespace)
            match = re.match(r'^(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F:]{17})\s+(.+)$', line)
            if match:
                ip_address = match.group(1)
                mac_address = match.group(2)
                vendor_name = match.group(3).strip()
                
                if self.debug:
                    print(f"DEBUG: Found entry - IP: {ip_address}, MAC: {mac_address}, Vendor: {vendor_name}", file=sys.stderr)
                
                # Check if vendor is an RFID manufacturer
                for rfid_vendor in self.RFID_VENDORS:
                    if rfid_vendor.lower() in vendor_name.lower():
                        # Determine product name based on vendor
                        if 'zebra' in vendor_name.lower():
                            product = "Zebra"
                        elif 'impinj' in vendor_name.lower():
                            product = "Impinj"
                        else:
                            product = vendor_name
                        
                        if self.debug:
                            print(f"DEBUG: Matched RFID vendor: {rfid_vendor} -> Product: {product}", file=sys.stderr)
                        
                        readers.append({
                            'ip': ip_address,
                            'product': product,
                            'vendor': vendor_name,
                            'mac': mac_address
                        })
                        break
        
        if self.debug:
            print(f"DEBUG: Found {len(readers)} RFID reader(s) after parsing", file=sys.stderr)
        
        return readers
    
    def find_readers(self) -> List[Dict[str, str]]:
        """
        Scan network and find RFID readers.
        
        Returns:
            List of dictionaries with RFID reader information
        """
        print(f"Scanning network {self.network_range} on interface {self.interface} for RFID readers...")
        print("This may take a few moments...\n")
        
        arpscan_output = self._run_arpscan()
        if arpscan_output is None:
            return []
        
        self.readers_found = self._parse_arpscan_output(arpscan_output)
        return self.readers_found
    
    def print_results(self):
        """Print the found RFID readers in a formatted way."""
        if not self.readers_found:
            print("No RFID readers found on the network.")
            print("\nPossible reasons:")
            print("  - RFID reader is not connected")
            print("  - RFID reader is on a different network")
            print("  - RFID reader is not powered on")
            print("  - MAC address vendor information not recognized")
            return
        
        print(f"\nFound {len(self.readers_found)} RFID reader(s):\n")
        print("-" * 60)
        
        for i, reader in enumerate(self.readers_found, 1):
            print(f"Reader {i}:")
            print(f"  IP Address: {reader['ip']}")
            print(f"  Product: {reader['product']}")
            print(f"  Vendor: {reader['vendor']}")
            print(f"  MAC Address: {reader['mac']}")
            print("-" * 60)
        
        print(f"\nPrimary RFID Reader IP: {self.readers_found[0]['ip']}")
        print(f"Product: {self.readers_found[0]['product']}")


def main():
    """Main function to run the RFID IP finder."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Find RFID reader IP addresses using arp-scan')
    parser.add_argument('--debug', action='store_true', 
                       help='Enable debug output showing arp-scan command and parsing details')
    parser.add_argument('--network', default='169.254.0.0/16',
                       help='Network range to scan (default: 169.254.0.0/16)')
    parser.add_argument('--interface', default=None,
                       help='Network interface to use (default: auto-detect or eth0)')
    args = parser.parse_args()
    
    # Check if running on a system that supports sudo
    if platform.system() == "Windows":
        print("Warning: This script is designed for Linux/Unix systems.", file=sys.stderr)
        print("arp-scan on Windows may require different tools.", file=sys.stderr)
        print()
    
    # Check for sudo privileges at start
    has_sudo = os.geteuid() == 0 if hasattr(os, 'geteuid') else False
    if args.debug:
        print(f"DEBUG: Starting with sudo privileges: {has_sudo}", file=sys.stderr)
    
    if not has_sudo and platform.system() != "Windows":
        print("Note: This script requires sudo privileges for network scanning.")
        print("If you encounter permission errors, please run: sudo python3 utils_Test/find_rfid_ip.py\n")
    
    finder = RFIDIPFinder(network_range=args.network, interface=args.interface, debug=args.debug)
    readers = finder.find_readers()
    finder.print_results()
    
    # Exit with appropriate code
    return 0 if readers else 1


if __name__ == "__main__":
    sys.exit(main())

