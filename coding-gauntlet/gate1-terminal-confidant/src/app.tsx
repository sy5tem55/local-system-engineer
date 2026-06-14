// src/app.tsx — AGENT IMPLEMENTS the Ink (React-for-the-terminal) view.
// Truecolor, monospace, #0a0a0a ground. Composes: an input box (primary amber
// cursor), a scrolling message pane that prints renderMessageToAnsi(msg) for
// each entry, and a streaming assistant line fed by streamChat().
// NOTE: not imported by the automated harness — exercised by the live/manual run.
import React from "react";

export interface AppProps {
  baseUrl: string;
  room?: string;
  logPath?: string;
}

export function App(_props: AppProps): React.ReactElement {
  throw new Error("NOT IMPLEMENTED: App — Gate 1 Ink TUI. See SPEC.md §Build.");
}
