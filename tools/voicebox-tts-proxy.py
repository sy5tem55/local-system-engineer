#!/usr/bin/env python3
"""
Voicebox TTS Proxy — OpenAI-compatible TTS endpoint for LibreChat.

Listens on port 9710, translates LibreChat's OpenAI TTS format to Voicebox API calls.
Voicebox runs on node3090:17600 with Kokoro-82M engine.

LibreChat config (librechat.yaml):
  speech:
    tts:
      openai:
        url: http://host.docker.internal:9710/v1/audio/speech
        apiKey: proxy
        model: tts-1
        voices: [alloy, echo, fable, onyx, nova, shimmer]

Voice mapping (OpenAI name → Voicebox profile ID):
  alloy   → librechat-alloy   (Kokoro af_alloy)
  echo    → librechat-echo    (Kokoro af_aoede)
  fable   → librechat-fable   (Kokoro bm_fable)
  onyx    → librechat-onyx    (Kokoro am_onyx)
  nova    → librechat-nova    (Kokoro af_nova)
  shimmer → librechat-shimmer (Kokoro af_bella)
"""

import json
import logging
import sys
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

VOICEBOX_URL = "http://node3090:17600"

# Voice mapping: OpenAI voice name → Voicebox profile ID
VOICE_MAP = {
    "alloy":   "9b50353b-de36-4a64-94b9-4b136bcc48e8",  # librechat-alloy → Kokoro af_alloy
    "echo":    "57304e84-e521-4660-844d-adba2418b75e",  # librechat-echo → Kokoro af_aoede
    "fable":   "21c4c2f5-3633-45ee-9292-8616bb7d8c06",  # librechat-fable → Kokoro bm_fable
    "onyx":    "9ea5bb21-057c-420c-89e3-9c7a41169a4a",  # librechat-onyx → Kokoro am_onyx
    "nova":    "936c3105-58ee-446a-ba8f-bbb0f80b4c43",  # librechat-nova → Kokoro af_nova
    "shimmer": "68e0148f-5d64-4bdb-aa50-9b26bcd5ebd1",  # librechat-shimmer → Kokoro af_bella
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("voicebox-tts-proxy")


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in separate threads for concurrency."""
    daemon_threads = True
    allow_reuse_address = True


class TTSProxyHandler(BaseHTTPRequestHandler):
    """Handle OpenAI-compatible TTS requests."""

    def log_message(self, format, *args):
        logger.debug(f"{self.address_string()} - {format % args}")

    def send_error_json(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": {"message": message}}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        if self.path != "/v1/audio/speech":
            self.send_error_json(404, "Not found. Use POST /v1/audio/speech")
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self.send_error_json(400, f"Invalid JSON: {e}")
            return

        # Extract parameters from LibreChat's OpenAI-style request
        text = data.get("input") or data.get("text")
        voice = data.get("voice", "alloy")
        model = data.get("model", "tts-1")

        if not text:
            self.send_error_json(400, "Missing 'input' or 'text' field")
            return

        # Map voice name to profile ID
        profile_id = VOICE_MAP.get(voice)
        if not profile_id:
            available = ", ".join(VOICE_MAP.keys())
            self.send_error_json(400, f"Unknown voice '{voice}'. Available: {available}")
            return

        logger.info(f"TTS request: voice={voice}, text_len={len(text)}, profile={profile_id}")

        # Build Voicebox generation request
        voicebox_payload = {
            "profile_id": profile_id,
            "text": text,
            "engine": "kokoro",
            "language": "en",
            "normalize": True,
        }

        try:
            req = urllib.request.Request(
                f"{VOICEBOX_URL}/generate/stream",
                data=json.dumps(voicebox_payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=120) as resp:
                # Stream the WAV audio back to LibreChat
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                # Copy response body in chunks
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

            logger.info(f"TTS complete: voice={voice}, text_len={len(text)}")

        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            logger.error(f"Voicebox HTTP error {e.code}: {error_body}")
            self.send_error_json(502, f"Voicebox error {e.code}: {error_body}")
        except urllib.error.URLError as e:
            logger.error(f"Voicebox connection error: {e}")
            self.send_error_json(503, f"Cannot reach Voicebox: {e.reason}")
        except Exception as e:
            logger.error(f"TTS generation failed: {e}", exc_info=True)
            self.send_error_json(500, f"TTS generation failed: {e}")


def main():
    port = 9710
    server = ThreadingHTTPServer(("0.0.0.0", port), TTSProxyHandler)
    logger.info(f"Voicebox TTS Proxy v2.2 listening on port {port}")
    logger.info(f"Voicebox backend: {VOICEBOX_URL}")
    logger.info(f"Available voices: {', '.join(VOICE_MAP.keys())}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
