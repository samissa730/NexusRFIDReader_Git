"""
Find Zebra FX7500 RFID reader IP address.

Behavior:
- Try known defaults (169.254.10.1) and any cached last-known IP (if provided via env).
- Enumerate local IPv4 interfaces and scan their /24 for TCP port 5084 (LLRP).
- Also probe common private subnets 192.168.0.0/24, 192.168.1.0/24, 10.0.0.0/24.

Usage:
  python utils_Test/find_rfid_ip.py

Output:
- Prints the discovered IP to stdout and exits 0.
- Exits with non-zero code if not found.
"""

import ipaddress
import os
import socket
import subprocess
import sys
from typing import Iterable, List, Optional, Tuple


LLRP_PORT = 5084
CONNECT_TIMEOUT_S = 0.2


def _tcp_port_open(ip: str, port: int, timeout: float) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((ip, port)) == 0
    except Exception:
        return False


def _candidate_subnets_from_windows_ipconfig() -> List[Tuple[str, str]]:
    try:
        result = subprocess.run(
            ["ipconfig"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        lines = result.stdout.splitlines()
        subnets: List[Tuple[str, str]] = []
        current_ip: Optional[str] = None
        current_mask: Optional[str] = None
        for raw in lines:
            line = raw.strip()
            if line.lower().startswith("ipv4 address") or line.lower().startswith("ipv4-adresse"):
                # e.g. "IPv4 Address. . . . . . . . . . . : 192.168.1.50"
                parts = line.split(":")
                if len(parts) >= 2:
                    current_ip = parts[-1].strip()
            elif line.lower().startswith("subnet mask") or line.lower().startswith("subnetzmaske"):
                parts = line.split(":")
                if len(parts) >= 2:
                    current_mask = parts[-1].strip()
            if current_ip and current_mask:
                subnets.append((current_ip, current_mask))
                current_ip, current_mask = None, None
        return subnets
    except Exception:
        return []


def _iter_hosts_from_ip_mask(ip: str, mask: str) -> Iterable[str]:
    try:
        network = ipaddress.IPv4Network((ip, mask), strict=False)
        # Limit to /24 sized scans for speed; if larger, reduce
        if network.prefixlen < 24:
            # Create a new /24 network anchored at IP
            octets = ip.split(".")
            cidr24 = ".".join(octets[:3]) + ".0/24"
            network = ipaddress.IPv4Network(cidr24, strict=False)
        for host in network.hosts():
            yield str(host)
    except Exception:
        return


def _unique(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _build_candidate_ips() -> List[str]:
    candidates: List[str] = []

    # 1) Known FX7500 factory default (link-local when not configured)
    candidates.append("169.254.10.1")

    # 2) If caller supplies a last-known IP, try it early
    last_ip = os.environ.get("FX7500_LAST_IP", "").strip()
    if last_ip:
        candidates.append(last_ip)

    # 3) From local interfaces (/24 scan)
    for ip, mask in _candidate_subnets_from_windows_ipconfig():
        # Skip localhost and APIPA host IPs themselves; we'll scan the subnet
        if ip.startswith("127."):
            continue
        for host in _iter_hosts_from_ip_mask(ip, mask):
            candidates.append(host)

    # 4) Common private subnets
    for base in ("192.168.0.", "192.168.1.", "10.0.0."):
        for last in range(1, 255):
            candidates.append(f"{base}{last}")

    return _unique(candidates)


def discover_fx7500_ip() -> Optional[str]:
    for ip in _build_candidate_ips():
        if _tcp_port_open(ip, LLRP_PORT, CONNECT_TIMEOUT_S):
            return ip
    return None


def main() -> int:
    ip = discover_fx7500_ip()
    if ip:
        print(ip)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())


