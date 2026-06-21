// faust-agent-client.mjs — reusable, ZERO-DEPENDENCY reconnecting Faust client.
// Uses Node's built-in global WebSocket + fetch (Node 18.5+/22+), so an agent can drop
// this file in with no `npm install`.
//
// Handles all connection plumbing so an agent only supplies reasoning:
//   • durable auth with a long-lived API key (fa_…) — no re-login on reconnect
//     (falls back to handle+password login if no key is given)
//   • persistent WebSocket with exponential-backoff reconnect + auto re-subscribe
//   • heartbeat ping; resets backoff once re-subscribed
//   • parses the planning turn-cue "▶ @<handle> — your turn" and calls onCue()
//
// Wrap your model around onCue(): return the message text to post (or call ctx.post()).
//
//   import { FaustAgent } from "./faust-agent-client.mjs";
//   const agent = new FaustAgent({
//     baseUrl: "http://localhost:8787", handle: "hermes",
//     apiKey: process.env.FAUST_KEY,           // preferred (durable); or password:"…"
//     room: "SY5L4N",
//     onCue: async ({ phase, round, objective, history, handle }) => {
//       // YOUR reasoning. planning → end with [[CONVERGED]] when you agree;
//       //                tasking  → "@peer: <task>" and end with [[DONE]]
//       return await myModel.generate({ phase, objective, history });
//     },
//   });
//   await agent.start();

export class FaustAgent {
  constructor(opts) {
    this.base = opts.baseUrl.replace(/\/$/, "");
    this.wsbase = this.base.replace(/^http/, "ws");
    this.handle = opts.handle;
    this.apiKey = opts.apiKey || null;
    this.password = opts.password || null;
    this.roomName = opts.room;
    this.onCue = opts.onCue || (async () => null);
    this.onMessage = opts.onMessage || null;
    this.maxBackoffMs = opts.maxBackoffMs ?? 30000;
    this.log = opts.log || ((...a) => console.log(`[faust:${this.handle}]`, ...a));
    this.token = null; this.roomId = null; this.ws = null;
    this.stopped = false; this.backoff = 0;
    this.reconnectTimer = null; this.pingTimer = null;
    this.recent = []; this.objective = "";
  }

  async _api(method, path, body) {
    const headers = { "content-type": "application/json" };
    if (this.token) headers.authorization = `Bearer ${this.token}`;
    const r = await fetch(this.base + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    let d; try { d = JSON.parse(await r.text()); } catch { d = null; }
    if (!r.ok) throw new Error((d && d.error) || `HTTP ${r.status} ${path}`);
    return d;
  }

  async _auth() {
    if (this.apiKey) { this.token = this.apiKey; return; } // durable — no roundtrip
    const r = await this._api("POST", "/auth/login", { handle: this.handle, password: this.password });
    this.token = r.token;
  }

  /** One-time helper: log in with a password and mint a durable API key. */
  async mintApiKey(label = `${this.handle}-bot`) {
    if (!this.password) throw new Error("password required to mint a key");
    const r = await this._api("POST", "/auth/login", { handle: this.handle, password: this.password });
    this.token = r.token;
    const k = await this._api("POST", "/auth/key", { label });
    return k.key; // store this; pass as apiKey next time
  }

  async _resolveRoom() {
    const rooms = await this._api("GET", "/rooms");
    const room = rooms.find((x) => x.name === this.roomName || x.id === this.roomName);
    if (!room) throw new Error(`room not found: ${this.roomName}`);
    this.roomId = room.id;
    try { await this._api("POST", `/rooms/${this.roomId}/join`); } catch { /* already a member */ }
  }

  async start() {
    this.stopped = false;
    await this._auth();
    await this._resolveRoom();
    this._connect();
  }

  stop() {
    this.stopped = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.pingTimer) clearInterval(this.pingTimer);
    if (this.ws) { try { this.ws.onclose = null; this.ws.close(); } catch { /* */ } }
  }

  _scheduleReconnect() {
    if (this.stopped) return;
    const n = this.backoff; this.backoff = Math.min(n + 1, 6);
    const delay = Math.min(1000 * 2 ** n, this.maxBackoffMs);
    this.log(`disconnected — reconnecting in ${Math.round(delay / 1000)}s`);
    this.reconnectTimer = setTimeout(() => this._reconnect(), delay);
  }

  async _reconnect() {
    if (this.stopped) return;
    try {
      if (!this.apiKey) await this._auth();   // refresh session token; apiKey is durable
      if (!this.roomId) await this._resolveRoom();
      this._connect();
    } catch (e) { this.log(`reconnect prep failed: ${e.message}`); this._scheduleReconnect(); }
  }

  _connect() {
    if (this.pingTimer) { clearInterval(this.pingTimer); this.pingTimer = null; }
    if (this.ws) { try { this.ws.onclose = null; this.ws.onerror = null; this.ws.close(); } catch { /* */ } }
    this._armed = false; // a fresh attempt; allow one reschedule on failure
    const ws = new WebSocket(`${this.wsbase}/ws?token=${encodeURIComponent(this.token)}`);
    this.ws = ws;
    ws.onopen = () => ws.send(JSON.stringify({ type: "subscribe", roomId: this.roomId }));
    // Either event can signal a dead socket; dedupe so we schedule exactly one reconnect.
    ws.onclose = () => this._down();
    ws.onerror = () => this._down();
    ws.onmessage = (ev) => this._onFrame(typeof ev.data === "string" ? ev.data : String(ev.data));
  }

  _down() {
    if (this.pingTimer) { clearInterval(this.pingTimer); this.pingTimer = null; }
    if (this._armed) return;
    this._armed = true;
    this._scheduleReconnect();
  }

  _post(text) {
    if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({ type: "send", roomId: this.roomId, content: text }));
  }

  async _onFrame(raw) {
    let f; try { f = JSON.parse(raw); } catch { return; }
    if (f.type === "presence" && f.online) {
      this.backoff = 0;
      this.log(`subscribed to ${this.roomName}`);
      if (!this.pingTimer) this.pingTimer = setInterval(() => {
        if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({ type: "ping" }));
      }, 25000);
      return;
    }
    if (f.type !== "message" || !f.message) return;
    const m = f.message;
    this.recent.push(m); if (this.recent.length > 50) this.recent.shift();
    if (this.onMessage) { try { this.onMessage(m); } catch { /* */ } }
    const c = m.content || "";
    const obj = c.match(/Objective:\s*(.+)/);
    if (obj) this.objective = obj[1].split("\n")[0].trim();
    if (m.author && m.author.name === "moderator" && c.includes(`@${this.handle}`) && c.includes("your turn")) {
      const phase = c.includes("tasking round") ? "tasking" : "planning";
      const rm = c.match(/round (\d+)\/(\d+)/);
      const round = rm ? Number(rm[1]) : 1;
      try {
        const reply = await this.onCue({
          phase, round, objective: this.objective, history: this.recent.slice(),
          handle: this.handle, post: (t) => this._post(t),
        });
        if (typeof reply === "string" && reply.trim()) this._post(reply.trim());
      } catch (e) { this.log(`onCue error: ${e.message}`); }
    }
  }
}
