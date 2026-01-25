#!/usr/bin/env python3
"""
Test IoT Service - Extended version of iot_service.py with Unix socket server
This version receives scan data via IPC and forwards to Azure IoT Hub
Run this to test the IPC → IoT Hub flow
"""

import json
import time
import signal
import subprocess
import sys
import threading
import socket
import io
from pathlib import Path

# Custom stderr filter to suppress non-critical SDK background thread errors
class StderrFilter:
    """Filter stderr to suppress non-critical Azure IoT SDK background thread errors"""
    def __init__(self, original_stderr):
        self.original_stderr = original_stderr
        self.suppress_patterns = [
            "Exception caught in background thread",
            "ConnectionDroppedError: Unexpected disconnection",
            "HandlerManagerException"
        ]
    
    def write(self, message):
        # Only suppress if message matches known non-critical SDK errors
        if any(pattern in message for pattern in self.suppress_patterns):
            return  # Suppress this message
        self.original_stderr.write(message)
    
    def flush(self):
        self.original_stderr.flush()

try:
    from azure.iot.device import (
        IoTHubDeviceClient,
        MethodResponse,
        ProvisioningDeviceClient
    )
    from azure.iot.device.exceptions import ConnectionDroppedError, ConnectionFailedError
except ImportError:
    print("ERROR: Azure IoT SDK not installed")
    print("Install with: sudo pip3 install azure-iot-device")
    sys.exit(1)

CONFIG_PATH = Path("/etc/azureiotpnp/provisioning_config.json")
SOCKET_PATH = "/var/run/nexus-iot.sock"

class TestAzureIoTService:
    def __init__(self):
        self.client = None
        self.running = True
        self.socket_server = None
        self.socket_thread = None
        self.message_count = 0
        self.client_lock = threading.Lock()  # Lock for thread-safe client operations
        self.connected = False
        self._load_configuration()
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        self.running = False

    def _load_configuration(self):
        """Load configuration from provisioning config"""
        if not CONFIG_PATH.exists():
            print(f"ERROR: Configuration file not found: {CONFIG_PATH}")
            print("Please run device_setup.py first!")
            raise FileNotFoundError("Device not configured")
        
        config = json.loads(CONFIG_PATH.read_text())
        self.global_endpoint = config["globalEndpoint"]
        self.id_scope = config["idScope"]
        self.registration_id = config["registrationId"]
        self.symmetric_key = config["symmetricKey"]
        
        # Load device tags
        tags_from_config = config.get("tags", {})
        self.tag = tags_from_config
        self.nexus_locate = self.tag.get("nexusLocate", {})
        
        print(f"✓ Loaded configuration for device: {self.registration_id}")
        print(f"  Site: {self.nexus_locate.get('siteName', 'N/A')}")
        print(f"  Truck: {self.nexus_locate.get('truckNumber', 'N/A')}")

    def provision_device(self):
        """Provision device using DPS"""
        print("Starting device provisioning...")
        prov_client = ProvisioningDeviceClient.create_from_symmetric_key(
            provisioning_host=self.global_endpoint,
            registration_id=self.registration_id,
            id_scope=self.id_scope,
            symmetric_key=self.symmetric_key
        )
        
        result = prov_client.register()
        if result.status != "assigned":
            print(f"✗ Provisioning failed: {result.status}")
            return False
        
        self.assigned_hub = result.registration_state.assigned_hub
        self.device_id = result.registration_state.device_id
        print(f"✓ Provisioned to hub: {self.assigned_hub}")
        print(f"✓ Device ID: {self.device_id}")
        return True

    def _connection_state_callback(self, connection_state):
        """Handle connection state changes - wrapped in try/except to prevent SDK background thread errors"""
        try:
            # Validate input
            if not connection_state or not isinstance(connection_state, str):
                return
            
            # Don't use locks in callbacks - they're called from SDK background threads
            # Just update the flag and log - keep it simple and fast
            state_lower = connection_state.lower()
            if state_lower == "connected":
                self.connected = True
                print("✓ IoT Hub connection state: Connected")
            elif state_lower == "disconnected":
                self.connected = False
                print("⚠ IoT Hub connection state: Disconnected")
            elif "retrying" in state_lower:
                print("⚠ IoT Hub connection state: Retrying...")
            elif "failed" in state_lower:
                self.connected = False
                print("✗ IoT Hub connection state: Failed")
        except (AttributeError, TypeError, Exception):
            # Silently handle any exceptions in callback to prevent SDK background thread errors
            # The SDK will handle reconnection automatically
            # Don't print here to avoid recursion or additional errors
            pass

    def connect_to_iot_hub(self):
        """Connect to IoT Hub"""
        with self.client_lock:
            try:
                if self.client:
                    try:
                        self.client.disconnect()
                    except:
                        pass
                
                self.client = IoTHubDeviceClient.create_from_symmetric_key(
                    symmetric_key=self.symmetric_key,
                    hostname=self.assigned_hub,
                    device_id=self.device_id
                )
                
                # Note: Connection state callback disabled to avoid HandlerManagerException errors
                # The SDK handles reconnection automatically, and _send_message_safe handles retries
                # Uncomment the line below if you want connection state monitoring (may cause background thread errors)
                # self.client.on_connection_state_change = self._connection_state_callback
                
                self.client.connect()
                self.connected = True
                print("✓ Connected to IoT Hub")
                
                # Report tags to device twin
                self._update_reported_tags()
                return True
            except Exception as e:
                self.connected = False
                print(f"✗ Connection failed: {e}")
                return False

    def _update_reported_tags(self):
        """Report configuration tags to device twin"""
        try:
            if not isinstance(self.tag, dict) or not self.tag:
                return
            self.client.patch_twin_reported_properties({"tags": self.tag})
            print("✓ Reported tags to IoT Hub")
        except Exception as e:
            print(f"Warning: Failed to report tags: {e}")

    def _start_socket_server(self):
        """Start Unix socket server to receive scan data from main app"""
        try:
            # Remove old socket file if exists
            if Path(SOCKET_PATH).exists():
                Path(SOCKET_PATH).unlink()
                print(f"✓ Removed old socket file")
            
            # Create Unix socket server
            self.socket_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket_server.bind(SOCKET_PATH)
            self.socket_server.listen(5)
            
            # Set permissions so main app can connect
            import os
            os.chmod(SOCKET_PATH, 0o666)
            
            print(f"✓ Socket server listening on {SOCKET_PATH}")
            
            # Start accepting connections in background thread
            self.socket_thread = threading.Thread(
                target=self._handle_socket_connections,
                daemon=True
            )
            self.socket_thread.start()
            
        except Exception as e:
            print(f"✗ Failed to start socket server: {e}")
            raise

    def _handle_socket_connections(self):
        """Accept and handle incoming socket connections"""
        print("Socket server ready to accept connections...")
        while self.running:
            try:
                # Set timeout to check self.running periodically
                self.socket_server.settimeout(1.0)
                try:
                    conn, _ = self.socket_server.accept()
                    print(f"✓ New client connected")
                    # Handle each connection in separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(conn,),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
            except Exception as e:
                if self.running:
                    print(f"✗ Socket server error: {e}")

    def _handle_client(self, conn):
        """Handle messages from a connected client"""
        buffer = ""
        try:
            while self.running:
                data = conn.recv(4096)
                if not data:
                    break
                
                buffer += data.decode('utf-8')
                
                # Process complete messages (newline-delimited)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line:
                        self._process_message(line)
                        
        except Exception as e:
            print(f"✗ Client handler error: {e}")
        finally:
            conn.close()
            print("Client disconnected")

    def _send_message_safe(self, message_json):
        """Send message to IoT Hub with automatic reconnection on failure"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.client_lock:
                    if not self.client or not self.connected:
                        # Try to reconnect
                        if not self.connect_to_iot_hub():
                            if attempt < max_retries - 1:
                                time.sleep(2)
                                continue
                            return False
                    
                    # Send message
                    self.client.send_message(message_json)
                    return True
                    
            except (ConnectionDroppedError, ConnectionFailedError) as e:
                print(f"⚠ Connection error on attempt {attempt + 1}: {e}")
                self.connected = False
                if attempt < max_retries - 1:
                    time.sleep(2)
                    # Try to reconnect
                    if not self.connect_to_iot_hub():
                        continue
                else:
                    print(f"✗ Failed to send message after {max_retries} attempts")
                    return False
            except Exception as e:
                print(f"✗ Unexpected error sending message: {e}")
                return False
        
        return False

    def _process_message(self, message_str):
        """Process received scan message and send to IoT Hub"""
        try:
            message = json.loads(message_str)
            msg_type = message.get("type")
            
            if msg_type == "scan":
                scan_data = message.get("data", {})
                
                # Add device identification from config
                enriched_data = {
                    **scan_data,
                    "deviceInfo": {
                        "registrationId": self.registration_id,
                        "deviceId": self.device_id,
                        "siteName": self.nexus_locate.get('siteName'),
                        "truckNumber": self.nexus_locate.get('truckNumber'),
                        "deviceSerial": self.nexus_locate.get('deviceSerial')
                    }
                }
                
                # Send to Azure IoT Hub with automatic reconnection
                iot_message = json.dumps(enriched_data)
                if self._send_message_safe(iot_message):
                    self.message_count += 1
                    print(f"✓ [{self.message_count}] Sent scan to IoT Hub: {scan_data.get('tagName')}")
                    print(f"   Location: ({scan_data.get('latitude')}, {scan_data.get('longitude')})")
                    print(f"   Site: {self.nexus_locate.get('siteName')}, Truck: {self.nexus_locate.get('truckNumber')}")
                else:
                    print(f"✗ Failed to send scan: {scan_data.get('tagName')}")
                
        except json.JSONDecodeError as e:
            print(f"✗ Invalid JSON message: {e}")
        except Exception as e:
            print(f"✗ Failed to process message: {e}")

    def run(self):
        """Main service loop"""
        # Install stderr filter to suppress non-critical SDK background thread errors
        original_stderr = sys.stderr
        sys.stderr = StderrFilter(original_stderr)
        
        try:
            print()
            print("=" * 60)
            print("Test Azure IoT Service with IPC Support")
            print("=" * 60)
            print()
            
            # Provision and connect
            if not self.provision_device():
                return
            if not self.connect_to_iot_hub():
                return
        
            # Start socket server for scan data
            print()
            self._start_socket_server()
            
            # Send initial connection message
            initial_msg = json.dumps({
                "event": "test_service_connected",
                "deviceId": self.device_id,
                "registrationId": self.registration_id,
                "siteName": self.nexus_locate.get('siteName'),
                "truckNumber": self.nexus_locate.get('truckNumber'),
                "timestamp": int(time.time())
            })
            if self._send_message_safe(initial_msg):
                print("✓ Sent initial connection message")
            else:
                print("⚠ Failed to send initial connection message")
            
            print()
            print("=" * 60)
            print("Service is running and ready to receive scan data")
            print("Run test_iot_publisher.py to send test scans")
            print("Press Ctrl+C to stop")
            print("=" * 60)
            print()
            
            try:
            # Keep service alive and send periodic heartbeats to maintain connection
            heartbeat_interval = 60  # Send heartbeat every 60 seconds
            last_heartbeat = time.time()
            
            while self.running:
                current_time = time.time()
                
                # Send heartbeat periodically to keep connection alive
                if current_time - last_heartbeat >= heartbeat_interval:
                    heartbeat = json.dumps({
                        "event": "heartbeat",
                        "deviceId": self.device_id,
                        "registrationId": self.registration_id,
                        "siteName": self.nexus_locate.get('siteName'),
                        "truckNumber": self.nexus_locate.get('truckNumber'),
                        "timestamp": int(current_time),
                        "status": "alive"
                    })
                    
                    if self._send_message_safe(heartbeat):
                        last_heartbeat = current_time
                    else:
                        # If heartbeat fails, try to reconnect
                        if not self.connect_to_iot_hub():
                            time.sleep(5)  # Wait before retrying
                
                time.sleep(1)
            finally:
                # Cleanup
                print("\nShutting down...")
                
                if self.socket_server:
                    try:
                        self.socket_server.close()
                        if Path(SOCKET_PATH).exists():
                            Path(SOCKET_PATH).unlink()
                        print("✓ Socket server closed")
                    except:
                        pass
                
                if self.client:
                    try:
                        disconnect_msg = json.dumps({
                            "event": "test_service_disconnecting",
                            "deviceId": self.device_id,
                            "timestamp": int(time.time()),
                            "messages_sent": self.message_count
                        })
                        # Try to send disconnect message, but don't fail if it doesn't work
                        try:
                            with self.client_lock:
                                if self.connected:
                                    self.client.send_message(disconnect_msg)
                        except:
                            pass
                        with self.client_lock:
                            self.client.disconnect()
                        print("✓ Disconnected from IoT Hub")
                    except Exception as e:
                        print(f"Warning: Error during disconnect: {e}")
                
                print(f"\nTotal messages sent: {self.message_count}")
        finally:
            # Restore original stderr
            sys.stderr = original_stderr


if __name__ == "__main__":
    try:
        service = TestAzureIoTService()
        service.run()
    except FileNotFoundError:
        print("\nDevice setup required! Please ensure Azure IoT is configured.")
        print("Check /etc/azureiotpnp/provisioning_config.json exists")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nService stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
