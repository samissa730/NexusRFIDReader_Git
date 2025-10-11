#!/usr/bin/env python3
"""
Encryption/Decryption utilities for sensitive data using built-in libraries
"""

import base64
import os
import hashlib
import platform
from typing import Tuple


class CryptoManager:
    """Handles encryption and decryption of sensitive data using XOR cipher"""
    
    def __init__(self):
        self.key = None
        self._load_or_generate_key()
    
    def _load_or_generate_key(self):
        """Load existing key or generate a new one"""
        key_file = self._get_key_file_path()
        
        if os.path.exists(key_file):
            # Load existing key
            with open(key_file, 'rb') as f:
                self.key = f.read()
        else:
            # Generate new key
            self.key = self._generate_key()
            # Save key for future use
            os.makedirs(os.path.dirname(key_file), exist_ok=True)
            with open(key_file, 'wb') as f:
                f.write(self.key)
    
    def _get_key_file_path(self):
        """Get the path to the encryption key file"""
        if platform.system() == "Linux" and os.path.exists("/proc/device-tree/model"):
            # Raspberry Pi
            return os.path.expanduser("~/.nexusrfid/.crypto_key")
        else:
            # Windows/Other
            return os.path.expanduser("~/Documents/.nexusrfid/.crypto_key")
    
    def _generate_key(self):
        """Generate a new encryption key based on system info"""
        # Use a combination of system info for key generation
        system_info = f"{platform.system()}{platform.machine()}{os.getcwd()}"
        
        # Create a hash of system info
        key_hash = hashlib.sha256(system_info.encode()).digest()
        
        # Use first 32 bytes as key
        return key_hash[:32]
    
    def _xor_encrypt_decrypt(self, data: bytes, key: bytes) -> bytes:
        """XOR encrypt/decrypt data with key"""
        result = bytearray()
        key_len = len(key)
        
        for i, byte in enumerate(data):
            result.append(byte ^ key[i % key_len])
        
        return bytes(result)
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string"""
        if not plaintext:
            return ""
        
        # Convert to bytes
        data = plaintext.encode('utf-8')
        
        # XOR encrypt
        encrypted_data = self._xor_encrypt_decrypt(data, self.key)
        
        # Base64 encode for safe storage
        return base64.urlsafe_b64encode(encrypted_data).decode()
    
    def decrypt(self, encrypted_text: str) -> str:
        """Decrypt an encrypted string"""
        if not encrypted_text:
            return ""
        
        try:
            # Base64 decode
            encrypted_data = base64.urlsafe_b64decode(encrypted_text.encode())
            
            # XOR decrypt
            decrypted_data = self._xor_encrypt_decrypt(encrypted_data, self.key)
            
            # Convert back to string
            return decrypted_data.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")
    
    def encrypt_credentials(self, client_id: str, client_secret: str) -> Tuple[str, str]:
        """Encrypt both client credentials"""
        encrypted_id = self.encrypt(client_id)
        encrypted_secret = self.encrypt(client_secret)
        return encrypted_id, encrypted_secret


# Global crypto manager instance
crypto_manager = CryptoManager()


def encrypt_text(text: str) -> str:
    """Convenience function to encrypt text"""
    return crypto_manager.encrypt(text)


def decrypt_text(encrypted_text: str) -> str:
    """Convenience function to decrypt text"""
    return crypto_manager.decrypt(encrypted_text)


def encrypt_credentials(client_id: str, client_secret: str) -> Tuple[str, str]:
    """Convenience function to encrypt credentials"""
    return crypto_manager.encrypt_credentials(client_id, client_secret)
