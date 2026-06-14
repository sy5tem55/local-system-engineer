// src/app.tsx — Ink TUI for the Terminal Confidant.
// Truecolor, monospace, #0a0a0a ground. Message pane + input box + streaming.
import React, { useState, useRef, useEffect } from "react";
import { Box, Text, useInput, useApp } from "ink";

import { streamChat } from "./transport.js";
import { renderMessageToAnsi } from "./render.js";
import { MessageLog } from "./log.js";
import type { Message } from "./schema.js";
import { tokens } from "./tokens.js";

const TEXT = tokens.color.text?.hex ?? "#e0e0e0";
const PRIMARY = tokens.color.primary?.hex ?? "#fab283";
const MUTED = tokens.color.textMuted?.hex ?? "#808080";

export interface AppProps {
  baseUrl: string;
  room?: string;
  logPath?: string;
  initialMessages?: Message[];
  stream?: (opts: {
    baseUrl: string;
    model?: string;
    messages: Message[];
    signal?: AbortSignal;
  }) => AsyncIterable<string>;
  budgetMs?: number;
}

export function App({
  baseUrl,
  room = "local",
  logPath,
  initialMessages,
  stream = streamChat,
  budgetMs = 60_000,
}: AppProps): React.ReactElement {
  const [messages, setMessages] = useState<Message[]>(initialMessages ?? []);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const budgetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { exit } = useApp();

  // Persist messages to logPath when they change
  useEffect(() => {
    if (!logPath || messages.length === 0) return;
    const lastMsg = messages[messages.length - 1];
    try {
      const log = new MessageLog(logPath);
      log.append(lastMsg);
    } catch {
      // log write failures are non-fatal
    }
  }, [messages, logPath]);

  useInput((char, key) => {
    if (streaming) {
      if (key.ctrl && char === "c") {
        abortRef.current?.abort();
        setStreaming(false);
        setStreamText("");
      }
      return;
    }
    if (key.return) {
      const text = input.trim();
      if (!text) return;
      setInput("");
      const userMsg: Message = {
        id: `u-${Date.now()}`,
        room,
        author: { id: "u:local", kind: "human", name: "You" },
        role: "user",
        content: text,
        ts: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setStreaming(true);
      setStreamText("");
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      // Give-up budget: abort after budgetMs
      const timer = setTimeout(() => {
        ctrl.abort();
      }, budgetMs);
      budgetTimerRef.current = timer;

      (async () => {
        try {
          const allMsgs = [...messages, userMsg].map((m) => ({
            role: m.role,
            content: m.content,
          }));
          const it = stream({
            baseUrl,
            messages: allMsgs as unknown as Message[],
            signal: ctrl.signal,
          });
          let accumulated = "";
          for await (const delta of it) {
            accumulated += delta;
            setStreamText(accumulated);
          }
          const assistantMsg: Message = {
            id: `m-${Date.now()}`,
            room,
            author: { id: "m:llama", kind: "model", name: "Assistant" },
            role: "assistant",
            content: accumulated,
            ts: Date.now(),
          };
          setMessages((prev) => [...prev, assistantMsg]);
        } catch (err: unknown) {
          const e = err as { name?: string; message?: string };
          if (e.name !== "AbortError") {
            setStreamText(`Error: ${e.message ?? String(err)}`);
          }
        } finally {
          setStreaming(false);
          setStreamText("");
          abortRef.current = null;
          if (budgetTimerRef.current) {
            clearTimeout(budgetTimerRef.current);
            budgetTimerRef.current = null;
          }
        }
      })();
      return;
    }
    if (key.backspace) {
      setInput((prev) => prev.slice(0, -1));
      return;
    }
    if (key.ctrl && char === "c") {
      exit();
      return;
    }
    if (char.length === 1) {
      setInput((prev) => prev + char);
    }
  });

  return (
    <Box flexDirection="column" height="100%" width="100%">
      <Box flexDirection="column" flexGrow={1} overflow="hidden" paddingY={1}>
        {messages.map((m) => (
          <Box key={m.id} flexDirection="column">
            <Text color={MUTED}>{m.author.name ?? m.author.id}</Text>
            <Box paddingLeft={1}>
              <Text wrap="wrap">{renderMessageToAnsi(m)}</Text>
            </Box>
          </Box>
        ))}
        {streaming && (
          <Box flexDirection="column">
            <Text color={PRIMARY}>Assistant</Text>
            <Box paddingLeft={1}>
              <Text color={TEXT}>{streamText}</Text>
              <Text color={PRIMARY}>{"▌"}</Text>
            </Box>
          </Box>
        )}
      </Box>
      <Box flexDirection="row" paddingY={1}>
        <Text color={PRIMARY}>{"▌ "}</Text>
        <Text color={TEXT}>{input}</Text>
      </Box>
    </Box>
  );
}
