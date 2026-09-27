#!/usr/bin/env python3
"""Toy loopback HTTP target; use only for the documented local example."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from json_transform_process import transform


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/transform":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 32768:
                self.send_error(413)
                return
            request = json.loads(self.rfile.read(size))
            if request["profile"] != "json-transform-v1":
                self.send_error(400)
                return
            response = json.dumps({"target_id": "toy-json-v1", "output": transform(request["input"])},
                                  separators=(",", ":")).encode("utf-8")
        except (ValueError, KeyError, TypeError):
            self.send_error(400)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print("toy target listening on 127.0.0.1:%d" % server.server_port, flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
