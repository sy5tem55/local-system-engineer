// src/server.ts — HTTP (REST) + WebSocket group server
import * as http from "node:http";
import * as https from "node:https";
import { readFileSync } from "node:fs";
import { WebSocketServer, WebSocket } from "ws";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Store } from "./db.js";
import type { ModelClient, SpeakerPolicy, Room, Message, AgentAccount } from "./protocol.js";
import { makeAuth, generateApiKey, apiKeyHash } from "./auth.js";
import { MentionReplyPolicy, runTurn } from "./orchestrator.js";

export interface ServerDeps {
  store: Store;
  model: ModelClient;
  policy?: SpeakerPolicy;
  secret?: string;
  turnBudget?: number;
  onMessage?: (roomId: string, message: Message, broadcast: (roomId: string, frame: unknown) => void) => Promise<void>;
  // Called once after each runTurn completes (WS + REST). Used by director policies
  // (e.g. the planning controller) to drain and post queued moderator notices.
  onTurnComplete?: (roomId: string, broadcast: (roomId: string, frame: unknown) => void) => Promise<void>;
  staticFiles?: Record<string, string>; // path -> filesystem path to serve
  // Plugin manifest inspection (admins see what each plugin declares before trusting it).
  pluginManifests?: () => Array<{ name: string; version: string; apiVersion: string; capabilities: string[]; commands?: string[]; description?: string }>;
}

export interface RunningServer {
  listen(port?: number): Promise<number>;
  fetch(req: Request): Promise<Response>;
  url(): string;
  wsUrl(token: string): string;
  connectedAccounts(roomId: string): string[];
  close(): Promise<void>;
}

interface WSClient {
  ws: WebSocket;
  accountId: string;
  subscriptions: Set<string>;
}

// Unified request interface for both HTTP and fetch
interface RouteRequest {
  method: string;
  pathname: string;
  searchParams: URLSearchParams;
  headers: Record<string, string>;
  body: unknown;
}

function jsonResp(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function errorResp(message: string, code: number): Response {
  return jsonResp({ error: message, code }, code);
}

export function createServer(deps: ServerDeps): RunningServer {
  const store = deps.store;
  const model = deps.model;
  const policy = deps.policy ?? new MentionReplyPolicy();
  const secret = deps.secret ?? "default-secret";
  const turnBudget = deps.turnBudget;

  const auth = makeAuth(store, secret);
  // Optional TLS: set TLS_CERT + TLS_KEY (PEM file paths) to serve HTTPS/WSS. The ws
  // server is noServer, so the same upgrade path yields wss with no other change.
  const tlsCert = process.env.TLS_CERT;
  const tlsKey = process.env.TLS_KEY;
  const useTls = !!(tlsCert && tlsKey);
  const TLS_PORT = Number(process.env.TLS_PORT ?? 8443);
  // Primary listener is always plain HTTP on PORT — localhost agents (LSE sidecar,
  // hermes, model-agent) connect via http://…:PORT. When TLS_CERT/TLS_KEY are set, a
  // SECOND https listener is started on TLS_PORT in listen() for browsers/iPad; it
  // shares the same request + upgrade handlers, so wss works there too.
  const httpServer = http.createServer();
  let tlsServer: https.Server | null = null;
  const wss = new WebSocketServer({ noServer: true });

  let port: number | null = null;
  const clients = new Map<WebSocket, WSClient>();

  // WebSocket upgrade handler
  httpServer.on("upgrade", (req, socket, head) => {
    const url = new URL(req.url || "", "http://localhost");
    const token = url.searchParams.get("token");
    if (!token) {
      socket.destroy();
      return;
    }
    const accountId = auth.verifyBearer(token);
    if (!accountId) {
      socket.destroy();
      return;
    }
    wss.handleUpgrade(req, socket, head, (ws) => {
      wss.emit("connection", ws, { accountId, token });
    });
  });

  wss.on("connection", (ws, info: { accountId: string; token: string }) => {
    const client: WSClient = { ws, accountId: info.accountId, subscriptions: new Set() };
    const accountId = info.accountId;
    clients.set(ws, client);

    ws.on("message", async (data) => {
      let frame: any;
      try {
        frame = JSON.parse(data.toString());
      } catch {
        ws.send(JSON.stringify({ type: "error", error: "Invalid JSON", code: 400 }));
        return;
      }

      switch (frame.type) {
        case "subscribe": {
          const roomId = frame.roomId as string;
          if (!store.isMember(roomId, accountId)) {
            ws.send(JSON.stringify({ type: "error", error: "Not a member", code: 403 }));
            return;
          }
          client.subscriptions.add(roomId);
          ws.send(JSON.stringify({ type: "presence", roomId, accountId, online: true }));
          break;
        }
        case "send": {
          const roomId = frame.roomId as string;
          const content = frame.content as string;
          if (!store.isMember(roomId, accountId)) {
            ws.send(JSON.stringify({ type: "error", error: "Not a member", code: 403 }));
            return;
          }
          const account = store.getAccount(accountId);
          if (!account) {
            ws.send(JSON.stringify({ type: "error", error: "Account not found", code: 401 }));
            return;
          }
          const room = store.getRoom(roomId);
          if (!room) {
            ws.send(JSON.stringify({ type: "error", error: "Room not found", code: 404 }));
            return;
          }

          const message: Message = {
            id: `u:${accountId}:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            room: roomId,
            author: { id: accountId, kind: account.kind, name: account.handle },
            role: account.kind === "human" ? "user" : "assistant",
            content,
            ts: Date.now(),
          };
          store.appendMessage(message);
          broadcastToRoom(roomId, { type: "message", message });
          ws.send(JSON.stringify({ type: "ack", ref: message.id }));
          // Plugin hook — Gate 3 intercepts "/" commands here
          if (deps.onMessage) {
            await deps.onMessage(roomId, message, broadcastToRoom);
          }

          try {
            await runTurn(room, message, {
              policy,
              model,
              agentsInRoom: (rid) => store.listAgentsInRoom(rid),
              history: (rid) => store.listMessages(rid),
              onReply: async (reply) => {
                store.appendMessage(reply);
                broadcastToRoom(reply.room, { type: "message", message: reply });
              },
              budget: turnBudget,
            });
          } catch (err) {
            console.error('runTurn failed:', err);
            broadcastToRoom(roomId, { type: 'error', error: 'Agent reply failed: ' + String(err) });
          }
          if (deps.onTurnComplete) {
            try { await deps.onTurnComplete(roomId, broadcastToRoom); }
            catch (err) { console.error('onTurnComplete failed:', err); }
          }
          break;
        }
        case "ping":
          ws.send(JSON.stringify({ type: "pong" }));
          break;
        default:
          ws.send(JSON.stringify({ type: "error", error: "Unknown frame type", code: 400 }));
      }
    });

    ws.on("close", () => {
      for (const roomId of client.subscriptions) {
        broadcastToRoom(roomId, { type: "presence", roomId, accountId, online: false });
      }
      clients.delete(ws);
    });
  });

  function broadcastToRoom(roomId: string, frame: unknown) {
    const data = JSON.stringify(frame);
    for (const [ws, client] of clients) {
      if (client.subscriptions.has(roomId) && ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    }
  }

  // Core route handler — works with unified RouteRequest
  async function handleRoute(r: RouteRequest): Promise<Response> {
    // Static file serving (Gate 3 web client)
    if (deps.staticFiles && deps.staticFiles[r.pathname]) {
      const fsPath = deps.staticFiles[r.pathname];
      try {
        const { readFile } = await import("node:fs/promises");
        const data = await readFile(fsPath);
        const ext = fsPath.split(".").pop() || "";
        const ctMap: Record<string, string> = {
          html: "text/html; charset=utf-8", js: "application/javascript",
          css: "text/css", json: "application/json", png: "image/png",
          svg: "image/svg+xml",
        };
        return new Response(data, {
          status: 200,
          headers: { "content-type": ctMap[ext] || "application/octet-stream" },
        });
      } catch {
        return new Response("Not found", { status: 404 });
      }
    }
    const { method, pathname, searchParams, headers, body } = r;

    // Auth routes (no auth required)
    if (pathname === "/auth/register" && method === "POST") {
      const b = body as { handle?: string; password?: string };
      try {
        const result = auth.register(b.handle!, b.password!);
        return jsonResp(result);
      } catch (e: any) {
        return errorResp(e.message, 400);
      }
    }

    if (pathname === "/auth/login" && method === "POST") {
      const b = body as { handle?: string; password?: string };
      try {
        const result = auth.login(b.handle!, b.password!);
        return jsonResp(result);
      } catch (e: any) {
        return errorResp(e.message, 401);
      }
    }

    // All other routes require auth
    const authHeader = headers["authorization"];
    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      return errorResp("Unauthorized", 401);
    }
    const token = authHeader.slice(7);
    const accountId = auth.verifyBearer(token);
    if (!accountId) {
      return errorResp("Unauthorized", 401);
    }

    // Plugin manifest inspection — what each loaded plugin declares (caps/commands).
    if (pathname === "/plugins" && method === "GET") {
      return jsonResp(deps.pluginManifests ? deps.pluginManifests() : []);
    }

    // ── API key management (1.7.0-b; identity-only — scope stored, not enforced) ──
    if (pathname === "/auth/key" && method === "POST") {
      const b = body as { label?: string; scope?: string[]; expires_at?: number; for?: string };
      // Admins can issue a key FOR another account (provision a bot without its password).
      let ownerId = accountId;
      if (b.for) {
        if (!store.isAdmin(accountId)) return errorResp("Only an admin can issue keys for another account", 403);
        const target = store.getAccountByHandle(b.for.trim().toLowerCase());
        if (!target) return errorResp(`No such account: ${b.for}`, 404);
        ownerId = target.id;
      }
      const key = generateApiKey();
      const id = `ak:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      store.createApiKey({ id, userId: ownerId, keyHash: apiKeyHash(key),
        label: b.label, scope: b.scope ? JSON.stringify(b.scope) : undefined, expiresAt: b.expires_at });
      return jsonResp({ id, key, owner: ownerId, label: b.label ?? null, scope: b.scope ?? [],
        note: "Save this key now — it is shown only once." }, 201);
    }
    if (pathname === "/auth/keys" && method === "GET") {
      return jsonResp(store.listApiKeys(accountId).map((k) => ({ ...k, scope: k.scope ? JSON.parse(k.scope) : [] })));
    }
    if (pathname === "/auth/key" && method === "DELETE") {
      const id = searchParams.get("id");
      if (!id) return errorResp("id required", 400);
      if (!store.revokeApiKey(id, accountId)) return errorResp("Key not found", 404);
      return jsonResp({ ok: true });
    }

    // GET /rooms
    if (pathname === "/rooms" && method === "GET") {
      return jsonResp(store.listRooms());
    }

    // POST /rooms — any member can create a room
    if (pathname === "/rooms" && method === "POST") {
      const b = body as { name?: string };
      const room = store.createRoom(b.name!);
      store.addMember(room.id, accountId);
      return jsonResp(room, 201);
    }

    // Room-specific routes
    const roomMatch = pathname.match(/^\/rooms\/([^/]+)(?:\/(.+))?$/);
    if (roomMatch) {
      const roomId = roomMatch[1];
      const subPath = roomMatch[2];
      const room = store.getRoom(roomId);
      if (!room) return errorResp("Room not found", 404);

      // GET /rooms/:id — room info
      if (!subPath && method === "GET") {
        return jsonResp(room);
      }

      // DELETE /rooms/:id — admin can delete the room
      if (!subPath && method === "DELETE") {
        if (!store.isAdmin(accountId)) {
          return errorResp("Only admins can delete rooms", 403);
        }
        store.deleteRoom(roomId);
        broadcastToRoom(roomId, { type: "room_removed", roomId });
        return jsonResp({ ok: true });
      }

      // POST /rooms/:id/clear — admin can clear all messages
      if (subPath === "clear" && method === "POST") {
        if (!store.isAdmin(accountId)) {
          return errorResp("Only admins can clear rooms", 403);
        }
        store.clearMessages(roomId);
        broadcastToRoom(roomId, { type: "room_cleared", roomId });
        return jsonResp({ ok: true });
      }

      // DELETE /rooms/:id/messages/:messageId — admin can delete a single message
      if (subPath && method === "DELETE") {
        const msgMatch = subPath.match(/^messages\/(.+)$/);
        if (msgMatch) {
          if (!store.isAdmin(accountId)) {
            return errorResp("Only admins can delete messages", 403);
          }
          const messageId = decodeURIComponent(msgMatch[1]);
          if (!store.deleteMessage(messageId)) {
            return errorResp("Message not found", 404);
          }
          broadcastToRoom(roomId, { type: "message_deleted", roomId, messageId });
          return jsonResp({ ok: true });
        }
      }

      // POST /rooms/:id/kick — admin can kick a member
      if (subPath === "kick" && method === "POST") {
        if (!store.isAdmin(accountId)) {
          return errorResp("Only admins can kick users", 403);
        }
        const b = body as { accountId?: string };
        const targetAccountId = b.accountId;
        if (!targetAccountId) {
          return errorResp("accountId required", 400);
        }
        if (targetAccountId === accountId) {
          return errorResp("Cannot kick yourself", 403);
        }
        if (!store.isMember(roomId, targetAccountId)) {
          return errorResp("User is not a member", 404);
        }
        store.removeMember(roomId, targetAccountId);
        broadcastToRoom(roomId, { type: "member_kicked", roomId, accountId: targetAccountId });
        return jsonResp({ ok: true });
      }

      // GET /rooms/:id/members — members can view the member list
      if (subPath === "members" && method === "GET") {
        if (!store.isMember(roomId, accountId)) {
          return errorResp("Not a member", 403);
        }
        const members = store.listMembers(roomId);
        return jsonResp(members.map(m => ({ ...m, isAdmin: store.isAdmin(m.accountId) })));
      }

      // Presence: who is currently connected AND subscribed to this room (live).
      if (subPath === "presence" && method === "GET") {
        if (!store.isMember(roomId, accountId)) {
          return errorResp("Not a member", 403);
        }
        const ids = new Set<string>();
        for (const c of clients.values()) if (c.subscriptions.has(roomId)) ids.add(c.accountId);
        return jsonResp([...ids].map((id) => {
          const a = store.getAccount(id);
          return { accountId: id, handle: a?.handle ?? id, kind: a?.kind ?? "model", isAdmin: store.isAdmin(id) };
        }));
      }

      if (subPath === "messages" && method === "GET") {
        if (!store.isMember(roomId, accountId)) {
          return errorResp("Not a member", 403);
        }
        const before = searchParams.get("before");
        const limit = searchParams.get("limit");
        const msgs = store.listMessages(roomId, {
          before: before ? Number(before) : undefined,
          limit: limit ? Number(limit) : undefined,
        });
        return jsonResp(msgs);
      }

      if (subPath === "messages" && method === "POST") {
        if (!store.isMember(roomId, accountId)) {
          return errorResp("Not a member", 403);
        }
        const b = body as { content?: string };
        const account = store.getAccount(accountId)!;
        const message: Message = {
          id: `u:${accountId}:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          room: roomId,
          author: { id: accountId, kind: account.kind, name: account.handle },
          role: account.kind === "human" ? "user" : "assistant",
          content: b.content!,
          ts: Date.now(),
        };
        store.appendMessage(message);
        broadcastToRoom(roomId, { type: "message", message });
        // Plugin hook — Gate 3 intercepts "/" commands here
        if (deps.onMessage) {
          await deps.onMessage(roomId, message, broadcastToRoom);
        }

        try {
          await runTurn(room, message, {
            policy,
            model,
            agentsInRoom: (rid) => store.listAgentsInRoom(rid),
            history: (rid) => store.listMessages(rid),
            onReply: async (reply) => {
              store.appendMessage(reply);
              broadcastToRoom(reply.room, { type: "message", message: reply });
            },
            budget: turnBudget,
          });
        } catch (err) {
          console.error('runTurn failed:', err);
        }
        if (deps.onTurnComplete) {
          try { await deps.onTurnComplete(roomId, broadcastToRoom); }
          catch (err) { console.error('onTurnComplete failed:', err); }
        }
        return jsonResp(message);
      }

      if (subPath === "join" && method === "POST") {
        const membership = store.addMember(roomId, accountId);
        return jsonResp(membership);
      }

      if (subPath === "agents" && method === "POST") {
        const b = body as { handle?: string; endpoint?: string; model?: string; persona?: string };
        const agent = store.upsertAgent({
          kind: "model",
          id: `m:${b.handle!}`,
          handle: b.handle!,
          endpoint: b.endpoint!,
          model: b.model,
          persona: b.persona,
        });
        store.addMember(roomId, agent.id);
        return jsonResp(agent);
      }
    }

    return errorResp("Not found", 404);
  }

  // HTTP server handler
  httpServer.on("request", async (req: IncomingMessage, res: ServerResponse) => {
    try {
      const url = new URL(req.url || "", `http://${req.headers.host || "localhost"}`);
      const bodyText = await readBody(req);
      let body: Record<string, unknown> = {};
      if (bodyText) { try { body = JSON.parse(bodyText); } catch { body = {}; } }

      const routeReq: RouteRequest = {
        method: req.method || "GET",
        pathname: url.pathname,
        searchParams: url.searchParams,
        headers: req.headers as Record<string, string>,
        body,
      };

      const response = await handleRoute(routeReq);
      const headers: Record<string, string> = {};
      for (const [k, v] of response.headers.entries()) {
        headers[k] = v;
      }
      res.writeHead(response.status, headers);
      res.end(await response.text());
    } catch (e: any) {
      res.writeHead(500, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: e.message, code: 500 }));
    }
  });

  // fetch-compatible handler
  async function fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    const bodyText = req.body ? await req.text() : "";
    let body: Record<string, unknown> = {};
    if (bodyText) { try { body = JSON.parse(bodyText); } catch { body = {}; } }

    const routeReq: RouteRequest = {
      method: req.method,
      pathname: url.pathname,
      searchParams: url.searchParams,
      headers: Object.fromEntries(req.headers.entries()),
      body,
    };

    return handleRoute(routeReq);
  }

  return {
    async listen(p?: number): Promise<number> {
      return new Promise((resolve, reject) => {
        const listenPort = p ?? 0;
        httpServer.listen(listenPort, "0.0.0.0", () => {
          const addr = httpServer.address();
          if (addr && typeof addr === "object") {
            port = addr.port;
            if (useTls) {
              tlsServer = https.createServer({ cert: readFileSync(tlsCert!), key: readFileSync(tlsKey!) });
              for (const fn of httpServer.listeners("request")) tlsServer.on("request", fn as any);
              for (const fn of httpServer.listeners("upgrade")) tlsServer.on("upgrade", fn as any);
              tlsServer.on("error", (e) => console.warn(`  TLS listener error: ${e.message}`));
              tlsServer.listen(TLS_PORT, "0.0.0.0", () => console.log(`  TLS: https/wss also on :${TLS_PORT}`));
            }
            resolve(port);
          } else {
            reject(new Error("Failed to get port"));
          }
        });
        httpServer.on("error", reject);
      });
    },

    fetch,

    url(): string {
      return `http://127.0.0.1:${port}`;
    },

    wsUrl(token: string): string {
      return `ws://127.0.0.1:${port}/ws?token=${token}`;
    },

    connectedAccounts(roomId: string): string[] {
      const out = new Set<string>();
      for (const c of clients.values()) if (c.subscriptions.has(roomId)) out.add(c.accountId);
      return [...out];
    },

    async close(): Promise<void> {
      return new Promise((resolve) => {
        for (const [ws] of clients) {
          ws.close();
        }
        wss.close();
        tlsServer?.close();
        httpServer.close(() => resolve());
      });
    },
  };
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    req.on("end", () => resolve(Buffer.concat(chunks).toString()));
  });
}