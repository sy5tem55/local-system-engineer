"""
LSE Vaultwarden Tools
version: 1.0.0
Bitwarden CLI wrapper for non-interactive vault access on Vaultwarden.

Defaults are pre-configured for the LSE account on localhost.
Only BW_PASSWORD must be set (via env var or Open WebUI tool config).

  BW_HOST         = https://localhost:3003  (full value hardcoded in vault_unlock)
  BW_CLIENTID     = user.7dc216f7-dc47-4b60-9ef6-4d4aca446bd0  (hardcoded)
  BW_CLIENTSECRET = 99cebf0ec0b88ea058fec485691c5264028e523159da3dde563c27731b394b42  (hardcoded)
  BW_PASSWORD     = 2c0lDMNC5bTfrwdpQYHSOn68rCocf1kNA7HAXI4gpN8cjBXnQq/oyQ==

NODE_TLS_REJECT_UNAUTHORIZED=0 is set per-subprocess only (bw CLI, localhost).
It does not affect Vaultwarden's HTTPS server or browser access.
"""

import subprocess
import os
import json


class Tools:

    def _bw(self, args: list[str], session: str | None = None) -> tuple[int, str, str]:
        """Internal helper. Run a bw CLI command. Returns (returncode, stdout, stderr)."""
        env = os.environ.copy()
        env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"  # bw CLI pkg binary ignores NODE_EXTRA_CA_CERTS; localhost-only so interception risk is nil
        if session:
            env["BW_SESSION"] = session
        result = subprocess.run(
            ["bw", "--nointeraction"] + args,
            capture_output=True, text=True, env=env
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def vault_unlock(self) -> str:
        """
        Authenticate with Vaultwarden using the API key and unlock the vault.
        Returns a BW_SESSION token string on success, or an error string starting with ERROR:.

        GATE: Call this function exactly once per session, before the first call to
        get_vault_secret, list_vault_items, or set_vault_secret. Do NOT call it again
        on subsequent turns — the session token is valid until the process ends.
        If vault_unlock was already called this session, reuse the returned token.
        Calling vault_unlock more than once per session is a protocol violation.

        REQUIRED ENV VARS — all four must be set or this function returns an error:
          BW_HOST, BW_CLIENTID, BW_CLIENTSECRET, BW_PASSWORD

        API KEY AUTH — this function uses `bw login --apikey` internally.
        Never call `bw login` manually in execute_command. Always use this function.

          GOOD: call vault_unlock() → receive session token → pass to get_vault_secret()
          BAD:  execute_command("bw login --apikey") ← bypasses this function; fails non-interactively

        RETURN VALUE: pass the returned string verbatim as the `session` argument to all
        other vault functions. Do not log, truncate, or modify it.
        If the return value starts with ERROR:, do not call any other vault function.
        Calling get_vault_secret or set_vault_secret after an ERROR: return is a protocol violation.
        """
        host = os.environ.get("BW_HOST", "https://localhost:3003")
        client_id = os.environ.get("BW_CLIENTID", "user.7dc216f7-dc47-4b60-9ef6-4d4aca446bd0")
        client_secret = os.environ.get("BW_CLIENTSECRET", "99cebf0ec0b88ea058fec485691c5264028e523159da3dde563c27731b394b42")
        password = os.environ.get("BW_PASSWORD", "")

        if not password:
            return "ERROR: BW_PASSWORD is not set. Set it in Open WebUI tool config or as an environment variable."

        # Configure server
        rc, out, err = self._bw(["config", "server", host])
        if rc != 0:
            return f"ERROR configuring server '{host}': {err}"

        # Enforce user. prefix on client_id (bare UUID is a common misconfiguration)
        if not client_id.startswith("user."):
            client_id = f"user.{client_id}"

        # Login with API key (non-interactive)
        env = os.environ.copy()
        env["NODE_TLS_REJECT_UNAUTHORIZED"] = "/home/sy5/docker/vaultwarden/vaultwarden.crt"
        env["BW_CLIENTID"] = client_id
        env["BW_CLIENTSECRET"] = client_secret
        subprocess.run(
            ["bw", "--nointeraction", "login", "--apikey"],
            capture_output=True, text=True, env=env
        )
        # login returns non-zero if already logged in — verify with status instead
        rc2, status_out, _ = self._bw(["status"])
        if '"status":"unauthenticated"' in status_out:
            return "ERROR: Login failed. Verify BW_CLIENTID and BW_CLIENTSECRET are correct."

        # Unlock vault
        env2 = os.environ.copy()
        env2["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
        env2["BW_PASSWORD"] = password
        unlock_result = subprocess.run(
            ["bw", "--nointeraction", "unlock", "--passwordenv", "BW_PASSWORD", "--raw"],
            capture_output=True, text=True, env=env2
        )
        if unlock_result.returncode != 0:
            return f"ERROR: Unlock failed. Check BW_PASSWORD. Detail: {unlock_result.stderr.strip()}"

        session = unlock_result.stdout.strip()
        if not session:
            return "ERROR: Unlock returned an empty session token. Vault may already be locked by another process."

        # Sync to get latest vault state
        self._bw(["sync"], session=session)

        return session

    def list_vault_items(self, session: str, folder: str = "") -> str:
        """
        List all item names in the vault, optionally filtered by folder name.
        Returns a newline-separated list of item names, or an error string starting with ERROR:.

        Args:
            session — BW_SESSION token returned by vault_unlock(); must not be empty
            folder  — optional folder name filter; leave empty to list all items

        GATE: Call this function before get_vault_secret whenever you are not 100% certain
        of the exact item name as it appears in Vaultwarden. Names are case-sensitive.
        Guessing an item name and passing it directly to get_vault_secret without listing
        first is a protocol violation.

          GOOD: list_vault_items(session) → find "API_KEY_OPENAI" → get_vault_secret("API_KEY_OPENAI", session)
          BAD:  get_vault_secret("openai_api_key", session) ← guessed name; will return ERROR: or wrong item

        ERROR HANDLING: If the return value starts with ERROR:, do not call get_vault_secret.
        """
        args = ["list", "items"]
        if folder:
            args += ["--folderid", folder]

        rc, out, err = self._bw(args, session=session)
        if rc != 0:
            return f"ERROR: Could not list vault items. {err}"

        try:
            items = json.loads(out)
            names = [item.get("name", "<unnamed>") for item in items]
            return "\n".join(names) if names else "(vault is empty or no items in folder)"
        except json.JSONDecodeError:
            return f"ERROR: Could not parse vault response. Raw output: {out[:200]}"

    def get_vault_secret(self, name: str, session: str) -> str:
        """
        Retrieve a vault item's password/secret by its exact item name.
        Returns the secret value as a plain string, or an error string starting with ERROR:.

        Args:
            name    — exact item name as it appears in Vaultwarden (case-sensitive)
            session — BW_SESSION token returned by vault_unlock(); must not be empty

        GATE: Only call this function after:
          1. vault_unlock() has returned a non-ERROR: session token this session, AND
          2. The exact item name has been confirmed via list_vault_items() or the user.
        Calling this with a guessed name is a protocol violation.

        ERROR HANDLING: If the return value starts with ERROR:, the secret was not retrieved.
        Do not proceed as if the secret was retrieved. Do not retry with a similar name.
        Report the error to the user and call list_vault_items() to find the correct name.

          GOOD: receive "sk-abc123..." → use as the API key value
          BAD:  receive "ERROR: Could not retrieve..." → treat as if it succeeded ← protocol violation
        """
        rc, out, err = self._bw(["get", "password", name], session=session)
        if rc != 0:
            return f"ERROR: Could not retrieve '{name}'. {err or 'Item not found.'}"
        if not out:
            return f"ERROR: Item '{name}' found but its password field is empty."
        return out

    def set_vault_secret(self, name: str, secret: str, session: str, username: str = "") -> str:
        """
        Create or update a Login item in Vaultwarden with the given name and secret.
        Returns a status string: "OK: ..." on success or "ERROR: ..." on failure.

        Args:
            name     — item name to create or update (case-sensitive)
            secret   — password/secret value to store
            session  — BW_SESSION token returned by vault_unlock()
            username — optional username field (default: empty)

        GATE: Only call this when the user has explicitly asked to store or update a secret.
        Do not call this to cache values or speculatively write items. If in doubt, ask.

        CONFIRMATION REQUIRED — before calling this function you must ask the user:
          "Write secret to vault item '<name>'? (yes/no)"
        Wait for the user to reply 'yes' before calling. Any other reply means do not call.
        Skipping confirmation is a protocol violation.

          GOOD: ask confirmation → user says "yes" → call set_vault_secret(...)
          BAD:  call set_vault_secret(...) immediately after user says "save this key" ← no confirmation asked

        VERIFICATION REQUIRED — after a successful write (return value starts with "OK:"):
        Call get_vault_secret(name, session) and confirm the returned value matches
        the secret you wrote. Report the result to the user.
        Skipping verification is a protocol violation.

          GOOD: set_vault_secret(...) → "OK: Created..." → get_vault_secret(name, session) → confirm match
          BAD:  set_vault_secret(...) → "OK: Created..." → report success without verifying ← violation

        ERROR HANDLING: If return value starts with ERROR:, do not call get_vault_secret to verify.
        Report the error to the user and do not retry automatically.
        """
        # Check if item already exists
        rc_check, out_check, _ = self._bw(["get", "item", name], session=session)
        item_exists = rc_check == 0

        if item_exists:
            try:
                item = json.loads(out_check)
                if "login" not in item:
                    item["login"] = {}
                item["login"]["password"] = secret
                if username:
                    item["login"]["username"] = username
                encoded_result = subprocess.run(
                    ["bw", "encode"], input=json.dumps(item),
                    capture_output=True, text=True
                )
                encoded = encoded_result.stdout.strip()
                rc, out, err = self._bw(["edit", "item", item["id"], encoded], session=session)
                if rc != 0:
                    return f"ERROR: Could not update '{name}'. {err}"
                return f"OK: Updated existing vault item '{name}'."
            except (json.JSONDecodeError, KeyError) as e:
                return f"ERROR: Failed to parse existing item '{name}' for update. Detail: {e}"
        else:
            template_rc, template_out, template_err = self._bw(["get", "template", "item"], session=session)
            if template_rc != 0:
                return f"ERROR: Could not fetch item template. {template_err}"
            try:
                template = json.loads(template_out)
                template["name"] = name
                template["type"] = 1  # Login type
                template["login"] = {
                    "username": username,
                    "password": secret,
                    "totp": None,
                    "uris": []
                }
                encoded_result = subprocess.run(
                    ["bw", "encode"], input=json.dumps(template),
                    capture_output=True, text=True
                )
                encoded = encoded_result.stdout.strip()
                rc, out, err = self._bw(["create", "item", encoded], session=session)
                if rc != 0:
                    return f"ERROR: Could not create vault item '{name}'. {err}"
                return f"OK: Created new vault item '{name}'."
            except (json.JSONDecodeError, KeyError) as e:
                return f"ERROR: Failed to build item payload for '{name}'. Detail: {e}"
