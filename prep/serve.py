"""Local dev server for basin_app with HTTP Range support (PMTiles needs 206 responses;
`python -m http.server` does not provide them).

Usage:  python prep/serve.py [port]     (serves the basin_app folder on 127.0.0.1, default 8765)
"""
import functools
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

from RangeHTTPServer import RangeRequestHandler


class Quiet(RangeRequestHandler):
    extensions_map = {**RangeRequestHandler.extensions_map,
                      ".md": "text/markdown; charset=utf-8",
                      ".geojson": "application/geo+json"}

    def log_message(self, fmt, *args):   # one line per request is enough
        sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))


class Server(ThreadingHTTPServer):
    # the default listen backlog (5) overflows on Windows when MapLibre fires a burst of parallel range
    # requests at the PMTiles archives: connections get refused and tiles silently go missing
    request_queue_size = 64
    daemon_threads = True


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    root = Path(__file__).resolve().parents[1]
    handler = functools.partial(Quiet, directory=str(root))
    print(f"serving {root} at http://127.0.0.1:{port}/site/", flush=True)
    Server(("127.0.0.1", port), handler).serve_forever()


if __name__ == "__main__":
    main()
