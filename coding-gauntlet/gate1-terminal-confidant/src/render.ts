// src/render.ts — opencode ANSI renderer.
// Renders ONE Message to an ANSI truecolor string on the #0a0a0a ground.
// Markdown: bold, headings, links, inline-code, fenced code blocks.
// Every emitted color must be within ΔE<=2 of an opencode token.
import type { Message } from "./schema.js";
import { tokens, fg, bg, RESET } from "./tokens.js";

export interface RenderOpts {
  width?: number;
}

// ── palette shortcuts (all from tokens) ──────────────────────────────────────
const P = tokens.color as Record<string, { hex: string }>;
const S = tokens.syntax as Record<string, string>;

const TEXT      = P.text?.hex      ?? "#e0e0e0";
const TEXT_MUTE = P.textMuted?.hex ?? "#808080";
const PRIMARY   = P.primary?.hex   ?? "#fab283";
const ACCENT    = P.accent?.hex    ?? "#9d7cd8";
const SECONDARY = P.secondary?.hex ?? "#5c9cf5";
const BG        = P.background?.hex ?? "#0a0a0a";

const SYNTAX = {
  comment:  S.comment  ?? TEXT_MUTE,
  keyword:  S.keyword  ?? ACCENT,
  function: S.function ?? SECONDARY,
  string:   S.string   ?? P.success?.hex ?? "#7fd88f",
  number:   S.number   ?? PRIMARY,
  type:     S.type     ?? SECONDARY,
  variable: S.variable ?? TEXT,
};

// ── lean Python highlighter ──────────────────────────────────────────────────
function highlightPython(line: string): string {
  // Very small state-machine: string literal → keyword → function call → number → comment
  const parts: string[] = [];
  let i = 0;
  const len = line.length;

  while (i < len) {
    // comment (rest of line)
    if (line[i] === "#") {
      parts.push(fg(SYNTAX.comment) + line.slice(i) + RESET);
      break;
    }
    // string literals (single or double quoted)
    if (line[i] === "'" || line[i] === '"') {
      const q = line[i];
      let j = i + 1;
      while (j < len && line[j] !== q) j++;
      j++; // include closing quote
      parts.push(fg(SYNTAX.string) + line.slice(i, j) + RESET);
      i = j;
      continue;
    }
    // number
    if (/\d/.test(line[i]) && (i === 0 || /[\s(,=+\-*/]/.test(line[i - 1]))) {
      let j = i;
      while (j < len && /[\d.xXa-fA-F]/.test(line[j])) j++;
      parts.push(fg(SYNTAX.number) + line.slice(i, j) + RESET);
      i = j;
      continue;
    }
    // word token
    if (/[a-zA-Z_]/.test(line[i])) {
      let j = i;
      while (j < len && /[a-zA-Z0-9_]/.test(line[j])) j++;
      const word = line.slice(i, j);
      const kw = new Set([
        "def", "class", "return", "if", "else", "elif", "for", "while",
        "import", "from", "as", "try", "except", "with", "in", "not",
        "and", "or", "is", "None", "True", "False", "lambda", "yield",
        "raise", "pass", "break", "continue", "global", "nonlocal", "assert",
      ]);
      let color = SYNTAX.variable;
      if (kw.has(word)) color = SYNTAX.keyword;
      // function call: word followed by (
      if (j < len && line[j] === "(" && !kw.has(word)) color = SYNTAX.function;
      parts.push(fg(color) + word + RESET);
      i = j;
      continue;
    }
    // decorator
    if (line[i] === "@") {
      let j = i + 1;
      while (j < len && /[a-zA-Z0-9_.]/.test(line[j])) j++;
      parts.push(fg(SYNTAX.function) + line.slice(i, j) + RESET);
      i = j;
      continue;
    }
    // plain char
    parts.push(fg(TEXT) + line[i]);
    i++;
  }
  return parts.join("");
}

// ── generic (non-Python) highlighter — just keyword + string + comment ───────
function highlightGeneric(line: string): string {
  const parts: string[] = [];
  let i = 0;
  const len = line.length;
  const commonKw = new Set([
    "if", "else", "for", "while", "return", "function", "const", "let",
    "var", "class", "import", "export", "from", "as", "try", "catch",
    "new", "this", "true", "false", "null", "undefined", "async", "await",
    "switch", "case", "break", "continue", "default", "throw", "typeof",
  ]);
  while (i < len) {
    if ((line[i] === "/" && line[i + 1] === "/") || line[i] === "#") {
      parts.push(fg(SYNTAX.comment) + line.slice(i) + RESET);
      break;
    }
    if (line[i] === '"' || line[i] === "'" || line[i] === "`") {
      const q = line[i];
      let j = i + 1;
      while (j < len && line[j] !== q) { if (line[j] === "\\") j++; j++; }
      j++;
      parts.push(fg(SYNTAX.string) + line.slice(i, j) + RESET);
      i = j;
      continue;
    }
    if (/[a-zA-Z_$]/.test(line[i])) {
      let j = i;
      while (j < len && /[a-zA-Z0-9_$]/.test(line[j])) j++;
      const word = line.slice(i, j);
      let color = SYNTAX.variable;
      if (commonKw.has(word)) color = SYNTAX.keyword;
      else if (j < len && line[j] === "(") color = SYNTAX.function;
      parts.push(fg(color) + word + RESET);
      i = j;
      continue;
    }
    if (/\d/.test(line[i]) && (i === 0 || !/[a-zA-Z_$]/.test(line[i - 1]))) {
      let j = i;
      while (j < len && /[\d.xXa-fA-FeE+\-]/.test(line[j])) j++;
      parts.push(fg(SYNTAX.number) + line.slice(i, j) + RESET);
      i = j;
      continue;
    }
    parts.push(fg(TEXT) + line[i]);
    i++;
  }
  return parts.join("");
}

// ── inline markdown → ANSI ───────────────────────────────────────────────────
function renderInline(text: string): string {
  const parts: string[] = [];
  let i = 0;
  const len = text.length;

  while (i < len) {
    // bold: **text**
    if (text[i] === "*" && text[i + 1] === "*") {
      let j = i + 2;
      while (j < len - 1 && !(text[j] === "*" && text[j + 1] === "*")) j++;
      // j now points to first * of closing **
      const inner = text.slice(i + 2, j);
      parts.push(fg(ACCENT) + inner + RESET);
      i = j + 2;
      continue;
    }
    // inline code: `text`
    if (text[i] === "`") {
      let j = i + 1;
      while (j < len && text[j] !== "`") j++;
      parts.push(fg(PRIMARY) + bg(P.backgroundElement?.hex ?? "#1c1c1c") +
                 text.slice(i + 1, j) + RESET);
      i = j + 1;
      continue;
    }
    // link: [text](url)
    if (text[i] === "[" && text.indexOf("](", i) !== -1) {
      const bracketEnd = text.indexOf("](", i);
      const parenEnd = text.indexOf(")", bracketEnd + 2);
      if (parenEnd !== -1) {
        const label = text.slice(i + 1, bracketEnd);
        parts.push(fg(SECONDARY) + label + RESET);
        i = parenEnd + 1;
        continue;
      }
    }
    // heading marker: # text
    if (text[i] === "#" && (i === 0 || text[i - 1] === "\n")) {
      let level = 0;
      let j = i;
      while (j < len && text[j] === "#") { j++; level++; }
      // skip space after #
      if (j < len && text[j] === " ") j++;
      let end = j;
      while (end < len && text[end] !== "\n") end++;
      const headingText = text.slice(j, end);
      const hColor = level <= 2 ? ACCENT : SECONDARY;
      parts.push(fg(hColor) + headingText + RESET);
      i = end;
      continue;
    }
    parts.push(fg(TEXT) + text[i]);
    i++;
  }
  return parts.join("");
}

// ── main renderer ────────────────────────────────────────────────────────────
export function renderMessageToAnsi(msg: Message, _opts: RenderOpts = {}): string {
  const lines = msg.content.split("\n");
  const output: string[] = [];
  let inCode = false;
  let codeLang = "";
  let codeStartLine = "";

  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];

    // fenced code block toggle
    const fenceMatch = line.match(/^(```|~~~)(\w*)/);
    if (fenceMatch) {
      if (!inCode) {
        inCode = true;
        codeLang = fenceMatch[2].toLowerCase();
        continue;
      } else {
        // closing fence
        inCode = false;
        continue;
      }
    }

    if (inCode) {
      // syntax-highlighted code line
      let highlighted: string;
      if (codeLang === "python" || codeLang === "py") {
        highlighted = highlightPython(line);
      } else {
        highlighted = highlightGeneric(line);
      }
      output.push(bg(BG) + highlighted + RESET);
      continue;
    }

    // empty line
    if (line === "") {
      output.push("");
      continue;
    }

    // inline markdown
    output.push(renderInline(line));
  }

  return output.join("\n") + "\n";
}
