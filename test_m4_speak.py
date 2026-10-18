# M4 Speak Test Script - Using debug endpoint
# Usage: python test_m4_speak.py "你好，这是 M4 测试"

import json
import sys

import requests

BASE_URL = "http://127.0.0.1:48911"

def test_speak(text: str, character: str = "yui", use_auth: bool = False, token: str = ""):
    """Test M4 speak functionality"""
    
    # Use debug endpoint without auth
    if use_auth and token:
        endpoint = f"{BASE_URL}/api/lumo/speak"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    else:
        endpoint = f"{BASE_URL}/api/lumo/speak/test"
        headers = {"Content-Type": "application/json"}
    
    payload = {
        "lanlan_name": character,
        "text": text
    }
    
    mode = "WITH auth" if use_auth else "DEBUG (no auth)"
    print(f"M4 Speak Test [{mode}]")
    print(f"  Endpoint: {endpoint}")
    print(f"  Character: {character}")
    print(f"  Text: {text}")
    print()
    
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("Success!")
            print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
            print()
            print("Check NEKO:")
            print("  1. Did TTS play audio?")
            print("  2. Did subtitle show?")
            print("  3. Did chat window show message?")
            return True
        elif response.status_code == 404:
            print(f"Error: Character '{character}' not found")
            print("Try listing available characters first")
            return False
        else:
            print(f"Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to NEKO")
        print("Make sure NEKO is running on port 48911")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    text = sys.argv[1] if len(sys.argv) > 1 else "你好，这是 M4 测试"
    character = sys.argv[2] if len(sys.argv) > 2 else "yui"
    
    success = test_speak(text, character)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()