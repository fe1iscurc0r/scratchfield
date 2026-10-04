"""临时：验证网关启停端点（用后即删）"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

def call(method, path):
    req = urllib.request.Request(f"http://127.0.0.1:8000{path}", method=method)
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=15).read())
        print(f"{method} {path} ->", d)
        return d
    except Exception as e:
        print(f"{method} {path} -> ERR", type(e).__name__, e)
        return None

call("GET", "/openclaw/gateway/status")
