import httpx

for port in [8000, 8001, 5048]:
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/", timeout=3.0)
        print(f"Port {port}: {r.status_code} - {r.text[:100]}")
    except Exception as e:
        print(f"Port {port}: Error - {e}")
