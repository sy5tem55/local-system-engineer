#!/usr/bin/env node
// src/index.ts — Gate 1 entry. `npm start` launches the Ink TUI.
// Parse flags (--url, --room, --log), render <App/>, wire Ctrl-C, enforce budget.
import React from "react";
import { render as inkRender } from "ink";

import { App } from "./app.js";

function parseArgs(): { url: string; room: string; log: string | undefined; budgetMs: number } {
  const args = process.argv.slice(2);
  let url = "http://localhost:8080";
  let room = "local";
  let log: string | undefined;
  let budgetMs = 60_000;

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    const next = args[i + 1];
    if (a === "--url" && next) { url = next; i++; }
    else if (a === "--room" && next) { room = next; i++; }
    else if (a === "--log" && next) { log = next; i++; }
    else if (a === "--budget-ms" && next) { budgetMs = parseInt(next, 10); i++; }
    else if (a === "--help" || a === "-h") {
      console.log("Usage: confidant [options]");
      console.log("  --url <url>        llama-server base URL (default: http://localhost:8080)");
      console.log("  --room <name>      room/conversation id (default: local)");
      console.log("  --log <path>       JSONL log file path (optional)");
      console.log("  --budget-ms <ms>   max wall-time per assistant turn (default: 60000)");
      process.exit(0);
    }
  }
  return { url, room, log, budgetMs };
}

const { url, room, log, budgetMs } = parseArgs();

const { unmount } = inkRender(
  React.createElement(App, {
    baseUrl: url,
    room,
    logPath: log,
    budgetMs,
  }),
);

// Clean exit on SIGINT / SIGTERM
const cleanup = () => {
  unmount();
  process.exit(0);
};
process.on("SIGINT", cleanup);
process.on("SIGTERM", cleanup);
