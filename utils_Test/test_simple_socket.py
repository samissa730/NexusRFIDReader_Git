#!/usr/bin/env python3
"""
Simple socket test - Tests basic Unix socket communication without Azure IoT
Use this to verify IPC is working before testing with Azure IoT Hub
"""

import socket
import json
import time
import sys
from pathlib import Path

SOCKET_PATH = "/var/run/nexus-iot-test.sock"

def test_socket_client():
    """Send a test message to the socket server"""
    print("=" * 60)
    print("Testing Unix Socket Client")
    print("=" * 60)
    print()
    
    # Check if socket exists
    if not Path(SOCKET_PATH).exists():
        print(f"✗ Socket file not found: {SOCKET_PATH}")
        print("  Start the server first:")
        print(f"  sudo python3 utils_Test/test_simple_socket.py server")
        return False
    
    try:
        # Connect to socket
        print(f"Connecting to {SOCKET_PATH}...")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(SOCKET_PATH)
        print("✓ Connected!")
        
        # Send test messages
        for i in range(3):
            message = {
                "type": "scan",
                "data": {
                    "tagName": f"TEST{i:03d}",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "speed": 15 + i
                }
            }
            
            json_data = json.dumps(message) + "\n"
            sock.sendall(json_data.encode('utf-8'))
            print(f"✓ Sent message {i + 1}: {message['data']['tagName']}")
            time.sleep(1)
        
        # Close connection
        sock.close()
        print("\n✓ Test completed successfully!")
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_socket_server():
    """Run a simple socket server to receive messages"""
    print("=" * 60)
    print("Testing Unix Socket Server")
    print("=" * 60)
    print()
    
    # Remove old socket file
    if Path(SOCKET_PATH).exists():
        Path(SOCKET_PATH).unlink()
        print(f"✓ Removed old socket file")
    
    try:
        # Create socket server
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        server.listen(1)
        
        # Set permissions
        import os
        os.chmod(SOCKET_PATH, 0o666)
        
        print(f"✓ Server listening on {SOCKET_PATH}")
        print("\nWaiting for connections...")
        print("Run in another terminal:")
        print(f"  python3 utils_Test/test_simple_socket.py client")
        print("\nPress Ctrl+C to stop")
        print()
        
        while True:
            # Accept connection
            conn, _ = server.accept()
            print("✓ Client connected")
            
            # Receive data
            buffer = ""
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                
                buffer += data.decode('utf-8')
                
                # Process complete messages
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line:
                        try:
                            message = json.loads(line)
                            print(f"✓ Received: {message}")
                        except json.JSONDecodeError as e:
                            print(f"✗ Invalid JSON: {e}")
            
            conn.close()
            print("Client disconnected\n")
            
    except KeyboardInterrupt:
        print("\n\nServer stopped")
    finally:
        if Path(SOCKET_PATH).exists():
            Path(SOCKET_PATH).unlink()
        print("✓ Cleanup completed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        test_socket_server()
    elif len(sys.argv) > 1 and sys.argv[1] == "client":
        test_socket_client()
    else:
        print("Usage:")
        print("  Start server: sudo python3 test_simple_socket.py server")
        print("  Start client: python3 test_simple_socket.py client")
