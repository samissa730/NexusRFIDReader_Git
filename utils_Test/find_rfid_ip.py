#!/usr/bin/env python3
"""
RFID Reader IP Finder

This script uses nmap to scan the 169.254.0.0/16 network range (Link-Local addresses)
to find connected RFID readers. It identifies RFID readers by detecting MAC addresses
associated with "Zebra Technologies" or "Impinj" vendors.

Usage:
    sudo python3 find_rfid_ip.py
    
Output:
    Prints the IP address and product name for each detected RFID reader.
"""

import subprocess
import re
import sys
import platform
from typing import List, Dict, Optional


class RFIDIPFinder:
    """Finds RFID reader IP addresses using nmap."""
    
    # RFID vendor keywords to look for in nmap output
    RFID_VENDORS = ['Zebra', 'Impinj']
    
    def __init__(self, network_range: str = "169.254.0.0/16"):
        """
        Initialize the RFID IP finder.
        
        Args:
            network_range: Network range to scan (default: 169.254.0.0/16 for Link-Local)
        """
        self.network_range = network_range
        self.readers_found = []
    
    def _check_nmap_available(self) -> bool:
        """Check if nmap is available on the system."""
        try:
            result = subprocess.run(
                ['nmap', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _run_nmap_scan(self) -> Optional[str]:
        """
        Run nmap scan to discover hosts on the network.
        
        Returns:
            nmap output as string, or None if scan fails
        """
        if not self._check_nmap_available():
            print("Error: nmap is not installed or not available in PATH", file=sys.stderr)
            print("Please install nmap: sudo apt-get install nmap (Linux) or install from https://nmap.org", file=sys.stderr)
            return None
        
        try:
            # Run nmap scan with -sn (no port scan, just ping sweep)
            # This is faster and sufficient for finding hosts
            cmd = ['sudo', 'nmap', '-sn', self.network_range]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60  # Timeout after 60 seconds
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or "Unknown error"
                if "sudo" in error_msg.lower() or "permission" in error_msg.lower():
                    print("Error: This script requires sudo privileges to run nmap", file=sys.stderr)
                else:
                    print(f"Error running nmap: {error_msg}", file=sys.stderr)
                return None
            
            return result.stdout
            
        except subprocess.TimeoutExpired:
            print("Error: nmap scan timed out after 60 seconds", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Error running nmap: {e}", file=sys.stderr)
            return None
    
    def _parse_nmap_output(self, nmap_output: str) -> List[Dict[str, str]]:
        """
        Parse nmap output to extract RFID reader IP addresses and vendor names.
        
        Args:
            nmap_output: The output from nmap command
            
        Returns:
            List of dictionaries with 'ip' and 'product' keys
        """
        readers = []
        lines = nmap_output.split('\n')
        
        current_ip = None
        
        for i, line in enumerate(lines):
            # Look for "Nmap scan report for" line to get IP address
            ip_match = re.search(r'Nmap scan report for ([\d.]+)', line)
            if ip_match:
                current_ip = ip_match.group(1)
                continue
            
            # Look for MAC Address line with vendor information
            # Format: "MAC Address: XX:XX:XX:XX:XX:XX (Vendor Name)"
            mac_match = re.search(r'MAC Address: ([\w:]+) \((.+?)\)', line)
            if mac_match and current_ip:
                vendor_name = mac_match.group(2)
                
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
                        
                        readers.append({
                            'ip': current_ip,
                            'product': product,
                            'vendor': vendor_name,
                            'mac': mac_match.group(1)
                        })
                        break
        
        return readers
    
    def find_readers(self) -> List[Dict[str, str]]:
        """
        Scan network and find RFID readers.
        
        Returns:
            List of dictionaries with RFID reader information
        """
        print(f"Scanning network {self.network_range} for RFID readers...")
        print("This may take a few moments...\n")
        
        nmap_output = self._run_nmap_scan()
        if nmap_output is None:
            return []
        
        self.readers_found = self._parse_nmap_output(nmap_output)
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
    # Check if running on a system that supports sudo
    if platform.system() == "Windows":
        print("Warning: This script is designed for Linux/Unix systems.", file=sys.stderr)
        print("nmap on Windows may require different privileges.", file=sys.stderr)
        print()
    
    finder = RFIDIPFinder()
    readers = finder.find_readers()
    finder.print_results()
    
    # Exit with appropriate code
    return 0 if readers else 1


if __name__ == "__main__":
    sys.exit(main())

