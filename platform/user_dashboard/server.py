from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


PLATFORM_ROOT = Path(__file__).resolve().parents[1]


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/platform/user_dashboard/"):
            target = parsed.path.removeprefix("/platform")
            if parsed.query:
                target = f"{target}?{parsed.query}"
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()
            return
        super().do_GET()

    def translate_path(self, path):
        parsed = urlparse(path)
        if parsed.path.startswith("/user_dashboard/index.html/"):
            return str(PLATFORM_ROOT / "user_dashboard" / "index.html")
        return super().translate_path(path)


def main():
    handler = partial(DashboardHandler, directory=str(PLATFORM_ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 5500), handler)
    print("User dashboard serving on http://127.0.0.1:5500/user_dashboard/index.html")
    server.serve_forever()


if __name__ == "__main__":
    main()
