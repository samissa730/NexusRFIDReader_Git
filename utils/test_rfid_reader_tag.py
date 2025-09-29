"""
Real-time RFID reader demo (no unittest).
Run: python test_rfid_reader_tag.py [--host 169.254.x.x] [--port 5084]

This script establishes a connection to the RFID reader and prints tags
in real-time, similar to test_network_status.py.
"""

import argparse
import json
import os
import signal
import sys
import threading
import time
from typing import Dict, Any, Optional, Tuple


# Ensure local utils can be imported when running directly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from settings import RFID_CONFIG
    from utils.logger import logger
except Exception:
    # Fallback if running from within utils directory without package context
    from settings import RFID_CONFIG  # type: ignore
    from logger import logger  # type: ignore

try:
    # Local RFID thread wrapper built on sllurp LLRP client
    from rfid import RFID
except ImportError as e:
    print(f"Import Error: {e}")
    print("Ensure you run from the project root or add the path to PYTHONPATH.")
    sys.exit(1)


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RFID Reader Real-time Tag Demo")
    parser.add_argument("--host", default=RFID_CONFIG.get("reader_ip", ""), help="RFID reader IP address")
    parser.add_argument("--port", default=RFID_CONFIG.get("port", 5084), type=int, help="RFID reader LLRP port")
    parser.add_argument("--print-json", action="store_true", help="Print full tag JSON objects")
    return parser.parse_args()


def extract_tag_summary(tag: Dict[str, Any]) -> Tuple[str, Optional[int], Optional[int]]:
    """
    Extract common fields from a tag dict in a resilient way across readers:
    - EPC (or TagID)
    - Antenna ID
    - RSSI (PeakRSSI)
    Returns (epc_str, antenna_id, rssi)
    """
    epc_keys = [
        "EPC", "EPC-96", "epc", "tag", "TagID", "id",
    ]
    antenna_keys = ["AntennaID", "antenna", "antenna_id"]
    rssi_keys = ["PeakRSSI", "RSSI", "rssi", "peak_rssi"]

    epc_val = None
    for k in epc_keys:
        if k in tag:
            epc_val = tag.get(k)
            break
    if epc_val is None:
        # Try to find any key that contains 'epc'
        for k, v in tag.items():
            if isinstance(k, str) and "epc" in k.lower():
                epc_val = v
                break

    antenna_val = None
    for k in antenna_keys:
        if k in tag:
            antenna_val = tag.get(k)
            break

    rssi_val = None
    for k in rssi_keys:
        if k in tag:
            rssi_val = tag.get(k)
            break

    try:
        epc_str = str(epc_val) if epc_val is not None else json.dumps(tag)
    except Exception:
        epc_str = str(epc_val) if epc_val is not None else str(tag)

    try:
        antenna_id = int(antenna_val) if antenna_val is not None else None
    except Exception:
        antenna_id = None

    try:
        rssi = int(rssi_val) if rssi_val is not None else None
    except Exception:
        # Some readers report RSSI as negative dBm float or string
        try:
            rssi = int(float(rssi_val)) if rssi_val is not None else None
        except Exception:
            rssi = None

    return epc_str, antenna_id, rssi


def print_header(host: str, port: int) -> None:
    print("\n" + "=" * 60)
    print("RFID READER TAG STREAM")
    print("=" * 60)
    print(f"Reader: {host}:{port}")
    print("Press Ctrl+C to stop.\n")


def main() -> None:
    args = parse_cli_args()

    host = args.host or RFID_CONFIG.get("reader_ip", "")
    port = int(args.port)
    print_header(host, port)

    rfid = RFID()

    # If CLI host differs from config, reconfigure reader
    if host and host != rfid.host:
        rfid.set_reader(host, False)

    # Start the background thread which manages connection and pings
    rfid.start()

    # Track state for concise status output
    last_connectivity: Optional[bool] = None
    last_print_time = 0.0
    printed_intro = False

    stop_event = threading.Event()

    def handle_sigint(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sigint)
    if hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, handle_sigint)
        except Exception:
            pass

    try:
        # Wait a short period for initial connection attempt
        start_wait = time.time()
        while time.time() - start_wait < 5 and not stop_event.is_set():
            conn = rfid.get_connectivity_status()
            if conn:
                break
            time.sleep(0.1)

        # Main loop: watch connectivity and stream tags
        while not stop_event.is_set():
            connected = rfid.get_connectivity_status()
            if connected != last_connectivity:
                last_connectivity = connected
                if connected:
                    print("[STATUS] Connected to RFID reader.")
                else:
                    print("[STATUS] Disconnected from RFID reader.")

            tag_list = rfid.get_last_tag_data()
            if tag_list:
                # When a new report arrives, print each tag
                for tag in tag_list:
                    if args.__dict__.get("print_json"):
                        try:
                            print("[TAG] " + json.dumps(tag, ensure_ascii=False))
                        except Exception:
                            print(f"[TAG] {tag}")
                    else:
                        epc, antenna_id, rssi = extract_tag_summary(tag)
                        details = []
                        if antenna_id is not None:
                            details.append(f"ant={antenna_id}")
                        if rssi is not None:
                            details.append(f"rssi={rssi}")
                        suffix = (" (" + ", ".join(details) + ")") if details else ""
                        print(f"[TAG] {epc}{suffix}")

                # Rate-limit non-tag heartbeat prints
                last_print_time = time.time()
                printed_intro = True

            else:
                # Periodic heartbeat so user knows it's running when idle
                now = time.time()
                if not printed_intro or (now - last_print_time) > 5:
                    if connected:
                        print("[WAIT] Listening for tags...")
                    else:
                        print("[WAIT] Attempting to connect...")
                    printed_intro = True
                    last_print_time = now

            time.sleep(0.1)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Error in RFID demo: {e}")
    finally:
        print("\nStopping reader...")
        try:
            rfid.stop()
        except Exception:
            pass
        print("Done.")


if __name__ == "__main__":
    main()


