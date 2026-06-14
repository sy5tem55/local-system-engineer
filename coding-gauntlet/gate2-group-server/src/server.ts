// src/server.ts — HTTP (REST) + WebSocket group server
import * as http from "node:http";
import { WebSocketServer, WebSocket } from "ws";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Store } from "./db.js";
import type { ModelClient, SpeakerPolicy, Room, Message, AgentAccount } from "./protocol.js";
import { makeAuth } from "./auth.js";
import { MentionReplyPolicy, runTurn } from "./orchestrator.js";

export interface ServerDeps {
  store: Store;
  model: ModelClient;
  policy?: SpeakerPolicy;
  secret?: string;
  turnBudget?: number;
}

export interface RunningServer {
  listen(port?: number): Promise<number>;
  fetch(req: Request): Promise<Response>;
  url(): string;
  wsUrl(token: string): string;
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
  const httpServer = http.createServer();
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
    const accountId = auth.verifyToken(token);
    if (!accountId) {
      socket.destroy();
      return;
    }
    wss.handleUpgrade(req, socket, head, (ws) => {
      wss.emit("connection", ws, { accountId, token });
    });
  });

  wss.on("connection", (ws, { accountId }) => {
    const client: WSClient = { ws, accountId, subscriptions: new Set() };
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
    const accountId = auth.verifyToken(token);
    if (!accountId) {
      return errorResp("Unauthorized", 401);
    }

    // GET /rooms
    if (pathname === "/rooms" && method === "GET") {
      return jsonResp(store.listRooms());
    }

    // POST /rooms
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
        return jsonResp(message);
      }

      if (subPath === "join" && method === "POST") {
        const membership = store.addMember(roomId, accountId);
        return jsonResp(membership);
      }

      if (subPath === "agents" && method === "POST") {
        const b = body as { handle?: string; endpoint?: string; model?: string; persona?: string };
        const agent = store.upsertAgent({
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
      const body = bodyText ? JSON.parse(bodyText) : {};

      const routeReq: RouteRequest = {
        method: req.method || "GET",
        pathname: url.pathname,
        searchParams: url.searchParams,
        headers: req.headers as Record<string, string>,
        body,
      };

      const response = await handleRoute(routeReq);
      res.writeHead(response.status, { "content-type": "application/json" });
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
    const body = bodyText ? JSON.parse(bodyText) : {};

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
        httpServer.listen(listenPort, "127.0.0.1", () => {
          const addr = httpServer.address();
          if (addr && typeof addr === "object") {
            port = addr.port;
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

    async close(): Promise<void> {
      return new Promise((resolve) => {
        for (const [ws] of clients) {
          ws.close();
        }
        wss.close();
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
