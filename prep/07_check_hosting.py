"""P0.7 - hosting probe: do Hugging Face dataset URLs support HTTP range requests and CORS,
as PMTiles needs? (Requested report before P4.)

Checks, against a real file in the existing CHIRPS dataset repo:
  1. GET with Range: bytes=0-1023  -> expect 206 Partial Content and 1024 bytes
  2. CORS preflight-relevant headers on the ranged GET with an Origin header
     -> expect Access-Control-Allow-Origin: * (and Range allowed)
  3. Redirect behaviour (HF resolve URLs redirect to a CDN) - fetch() follows redirects, but the
     final host must also answer range + CORS, so both hops are probed.

Usage:  python 07_check_hosting.py
"""
import requests

from prep_common import CHIRPS, log, setup_logging

PROBE = f"{CHIRPS}/time/c/0"
ORIGIN = "https://example.org"


def probe(url, name):
    h = {"Range": "bytes=0-1023", "Origin": ORIGIN}
    r = requests.get(url, headers=h, timeout=60, allow_redirects=False)
    log.info("[%s] %s", name, url.split("?")[0][:110])
    log.info("  status %s | len %s | accept-ranges=%s | content-range=%s",
             r.status_code, len(r.content), r.headers.get("Accept-Ranges"), r.headers.get("Content-Range"))
    log.info("  CORS: allow-origin=%s expose=%s", r.headers.get("Access-Control-Allow-Origin"),
             r.headers.get("Access-Control-Expose-Headers"))
    return r


def main():
    setup_logging()
    from urllib.parse import urljoin
    url = PROBE
    r = probe(url, "hf resolve")
    hops = 0
    while r.status_code in (301, 302, 303, 307, 308) and hops < 4:
        hops += 1
        url = urljoin(url, r.headers["Location"])
        r = probe(url, f"redirect {hops}")
    ok_range = r.status_code == 206 and len(r.content) == 1024
    ok_cors = r.headers.get("Access-Control-Allow-Origin") in ("*", ORIGIN)
    log.info("VERDICT: range=%s cors=%s -> %s", ok_range, ok_cors,
             "HF can host PMTiles for the app" if ok_range and ok_cors
             else "HF NOT suitable as-is; use object storage/CDN or internal server")


if __name__ == "__main__":
    main()
