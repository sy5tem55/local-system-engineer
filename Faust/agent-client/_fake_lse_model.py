import json, sys, re
from http.server import BaseHTTPRequestHandler, HTTPServer
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8088
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); raw = self.rfile.read(n).decode()
        try: body = json.loads(raw)
        except Exception: body = {}
        content = " ".join(m.get("content", "") for m in body.get("messages", []))
        rounds = [int(x) for x in re.findall(r"planning round (\d+)", content)]
        if "tasking round" in content:
            reply = "@hermes: own the infra workstream and report telemetry [[DONE]]"
        elif rounds and max(rounds) >= 2:
            reply = "lse: agreed, the plan is sound. [[CONVERGED]]"
        else:
            reply = "lse proposes: instrument the funnel first, then cut onboarding to 3 steps behind a flag."
        out = json.dumps({"choices": [{"message": {"role": "assistant", "content": reply}}]}).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(out)
HTTPServer(("127.0.0.1", PORT), H).serve_forever()
