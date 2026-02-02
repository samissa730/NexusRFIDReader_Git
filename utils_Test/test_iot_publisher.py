#!/usr/bin/env python3
"""
Test IoT Publisher - Sends scan data to Azure IoT service via Unix socket
This simulates what the main RFID app will do
"""

import socket
import json
import time
import sys
from pathlib import Path

class TestIoTPublisher:
    """Test publisher for sending scan data to Azure IoT service via Unix socket"""
    
    def __init__(self, socket_path='/var/run/nexus-iot.sock'):
        self.socket_path = socket_path
        self.socket = None
        
    def connect(self):
        """Connect to Azure IoT service socket"""
        try:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.connect(self.socket_path)
            print(f"✓ Connected to Azure IoT service at {self.socket_path}")
            return True
        except FileNotFoundError:
            print(f"✗ Socket file not found: {self.socket_path}")
            print("  Make sure Azure IoT service is running with socket server enabled")
            return False
        except ConnectionRefusedError:
            print(f"✗ Connection refused to {self.socket_path}")
            print("  Azure IoT service may not be listening on the socket")
            return False
        except Exception as e:
            print(f"✗ Failed to connect: {e}")
            return False
    
    def send_scan(self, scan_record):
        """Send scan data to Azure IoT service"""
        if not self.socket:
            if not self.connect():
                return False
        
        try:
            # Prepare message with type identifier
            message = {
                "type": "scan",
                "data": scan_record
            }
            
            # Send JSON message with newline delimiter
            json_data = json.dumps(message) + "\n"
            self.socket.sendall(json_data.encode('utf-8'))
            print(f"✓ Sent scan to IoT Hub: {scan_record.get('tagName')}")
            return True
            
        except BrokenPipeError:
            print("✗ Connection broken (BrokenPipeError)")
            self.socket = None
            return False
        except ConnectionResetError:
            print("✗ Connection reset by peer")
            self.socket = None
            return False
        except Exception as e:
            print(f"✗ Failed to send scan: {e}")
            return False
    
    def close(self):
        """Close socket connection"""
        if self.socket:
            try:
                self.socket.close()
                print("✓ Socket connection closed")
            except:
                pass
            self.socket = None


def create_test_scan_record():
    """Create a test scan record matching the C# Azure Function format"""
    import uuid
    import time
    
    # Generate test data
    test_tag = f"E20034120B1B0170{int(time.time()) % 100000000:08d}"
    
    # Format matches C# Azure Function IotHubToPostgres.cs
    record = {
        "siteId": "019a9e1e-81ff-75ab-99fc-4115bb92fec6",  # Guid format
        "tagName": test_tag,  # Also supports "epc" field name
        "latitude": 37.7749,  # double
        "longitude": -122.4194,  # double
        "speed": 15.0,  # double
        "deviceId": "1000000012345678",
        "antenna": "1",  # string in C# function
        "barrier": 270.0,  # double in C# function (bearing/heading)
        "comment": None,  # optional string
    }
    
    return record


def main():
    """Test the IoT publisher"""
    print("=" * 60)
    print("Testing IoT Publisher (IPC Communication)")
    print("=" * 60)
    print()
    
    # Check if socket file exists
    socket_path = '/var/run/nexus-iot.sock'
    print(f"Checking for socket file: {socket_path}")
    if Path(socket_path).exists():
        print(f"✓ Socket file exists")
    else:
        print(f"✗ Socket file does not exist")
        print(f"  Please start the test IoT service first:")
        print(f"  sudo python3 utils_Test/test_iot_service.py")
        sys.exit(1)
    
    print()
    
    # Create publisher
    publisher = TestIoTPublisher(socket_path)
    
    # Send test scans
    print("Sending test scan records...")
    print()
    
    num_scans = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    
    for i in range(num_scans):
        print(f"--- Scan {i + 1}/{num_scans} ---")
        
        # Create test record
        scan_record = create_test_scan_record()
        print(f"Tag: {scan_record['tagName']}")
        print(f"Location: ({scan_record['latitude']}, {scan_record['longitude']})")
        print(f"Speed: {scan_record['speed']} km/h")
        
        # Send to IoT Hub via IPC
        success = publisher.send_scan(scan_record)
        
        if not success:
            print("Failed to send scan, aborting test")
            break
        
        print()
        
        # Wait between scans
        if i < num_scans - 1:
            time.sleep(2)
    
    # Close connection
    print()
    publisher.close()
    
    print()
    print("=" * 60)
    print("Test completed!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Check Azure IoT Hub metrics in Azure Portal")
    print("2. Use Azure IoT Explorer to see device messages")
    print("3. Check Azure Function logs for message processing")
    print("4. Verify data in PostgreSQL database")


if __name__ == "__main__":
    main()
