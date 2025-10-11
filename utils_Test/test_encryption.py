#!/usr/bin/env python3
"""
Simple test script to verify encryption/decryption functionality
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.crypto import encrypt_text, decrypt_text, encrypt_credentials
from settings import API_CONFIG

def test_encryption():
    """Test basic encryption/decryption"""
    print("Testing basic encryption/decryption...")
    
    test_text = "Hello, World!"
    encrypted = encrypt_text(test_text)
    decrypted = decrypt_text(encrypted)
    
    print(f"Original: {test_text}")
    print(f"Encrypted: {encrypted}")
    print(f"Decrypted: {decrypted}")
    print(f"Match: {test_text == decrypted}")
    
    return test_text == decrypted

def test_credentials_encryption():
    """Test credential encryption/decryption"""
    print("\nTesting credential encryption/decryption...")
    
    original_id = "dC1zM4ghLvr8eipSOlmRhAelHRXdtvNC"
    original_secret = "M__OTtIL7Pw754RBKIEEOCrXsxTef61vWny57keAXqwNN6mvylhg5Yc4XNtajqk4"
    
    encrypted_id, encrypted_secret = encrypt_credentials(original_id, original_secret)
    decrypted_id = decrypt_text(encrypted_id)
    decrypted_secret = decrypt_text(encrypted_secret)
    
    print(f"Original ID: {original_id}")
    print(f"Encrypted ID: {encrypted_id}")
    print(f"Decrypted ID: {decrypted_id}")
    print(f"ID Match: {original_id == decrypted_id}")
    
    print(f"Original Secret: {original_secret[:20]}...")
    print(f"Encrypted Secret: {encrypted_secret[:20]}...")
    print(f"Decrypted Secret: {decrypted_secret[:20]}...")
    print(f"Secret Match: {original_secret == decrypted_secret}")
    
    return original_id == decrypted_id and original_secret == decrypted_secret

def test_settings_encryption():
    """Test that settings contain encrypted values"""
    print("\nTesting settings encryption...")
    
    client_id = API_CONFIG.get('client_id', '')
    client_secret = API_CONFIG.get('client_secret', '')
    
    print(f"Settings Client ID: {client_id}")
    print(f"Settings Client Secret: {client_secret[:20]}...")
    
    # These should be encrypted (not the original values)
    original_id = "dC1zM4ghLvr8eipSOlmRhAelHRXdtvNC"
    original_secret = "M__OTtIL7Pw754RBKIEEOCrXsxTef61vWny57keAXqwNN6mvylhg5Yc4XNtajqk4"
    
    id_encrypted = client_id != original_id
    secret_encrypted = client_secret != original_secret
    
    print(f"Client ID is encrypted: {id_encrypted}")
    print(f"Client Secret is encrypted: {secret_encrypted}")
    
    return id_encrypted and secret_encrypted

def test_decryption_from_settings():
    """Test decryption of values from settings"""
    print("\nTesting decryption from settings...")
    
    encrypted_id = API_CONFIG.get('client_id', '')
    encrypted_secret = API_CONFIG.get('client_secret', '')
    
    try:
        decrypted_id = decrypt_text(encrypted_id)
        decrypted_secret = decrypt_text(encrypted_secret)
        
        print(f"Decrypted ID: {decrypted_id}")
        print(f"Decrypted Secret: {decrypted_secret[:20]}...")
        
        # Verify against original values
        original_id = "dC1zM4ghLvr8eipSOlmRhAelHRXdtvNC"
        original_secret = "M__OTtIL7Pw754RBKIEEOCrXsxTef61vWny57keAXqwNN6mvylhg5Yc4XNtajqk4"
        
        id_match = decrypted_id == original_id
        secret_match = decrypted_secret == original_secret
        
        print(f"ID Match: {id_match}")
        print(f"Secret Match: {secret_match}")
        
        return id_match and secret_match
        
    except Exception as e:
        print(f"Error decrypting from settings: {e}")
        return False

def main():
    """Run all encryption tests"""
    print("Testing Encryption/Decryption System")
    print("=" * 50)
    
    tests = [
        ("Basic Encryption", test_encryption),
        ("Credential Encryption", test_credentials_encryption),
        ("Settings Encryption", test_settings_encryption),
        ("Decryption from Settings", test_decryption_from_settings),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{test_name}")
        print("-" * 30)
        try:
            result = test_func()
            results.append((test_name, result))
            print(f"{'PASS' if result else 'FAIL'}")
        except Exception as e:
            print(f"ERROR: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("All tests passed! Encryption system is working correctly.")
        return 0
    else:
        print("Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
