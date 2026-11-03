"""Optional host-side DoH connectivity check; does not exercise iPhone routing."""
import base64
from concurrent.futures import ThreadPoolExecutor
import struct
import time
import urllib.request

ENDPOINTS = (
    "https://dns.alidns.com/dns-query",
    "https://doh.pub/dns-query",
    "https://1.1.1.1/dns-query",
    "https://8.8.8.8/dns-query",
)


def probe(endpoint):
    # RFC 8484 wire-format A query, id=0, recursion desired, example.com.
    question = b"\x07example\x03com\x00\x00\x01\x00\x01"
    query = struct.pack("!6H", 0, 0x0100, 1, 0, 0, 0) + question
    encoded = base64.urlsafe_b64encode(query).decode().rstrip("=")
    start = time.monotonic()
    try:
        request = urllib.request.Request(endpoint + "?dns=" + encoded,
                                         headers={"Accept": "application/dns-message"})
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(65536)
            if response.headers.get_content_type() != "application/dns-message":
                raise ValueError("unexpected Content-Type")
        ident, flags, qd, answers, _, _ = struct.unpack("!6H", data[:12])
        if ident != 0 or not flags & 0x8000 or flags & 0x000F or qd != 1 or answers == 0:
            raise ValueError("invalid/error DNS answer")
        print(f"PASS {endpoint}: {answers} answers, {(time.monotonic()-start)*1000:.0f} ms")
        return True
    except (OSError, ValueError, struct.error) as error:
        print(f"FAIL {endpoint}: {error}")
        return False


if __name__ == "__main__":
    print("Host network only (including configured OS/environment proxies); not an iPhone leak test.")
    with ThreadPoolExecutor(max_workers=4) as pool:
        passed = list(pool.map(probe, ENDPOINTS))
    raise SystemExit(0 if all(passed) else 1)
