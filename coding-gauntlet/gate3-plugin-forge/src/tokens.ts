// src/tokens.ts — typed loader for the FROZEN opencode design tokens plus the
// color helpers the renderer and the acceptance harness share. Authored (frozen).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dir = dirname(fileURLToPath(import.meta.url));
const TOKENS_PATH = resolve(__dir, "../../design-tokens/opencode-tokens.json");

export interface Tokens {
  color: Record<string, { hex: string; confirmed: boolean; role: string }>;
  syntax: Record<string, string>;
  [k: string]: any;
}

export const tokens: Tokens = JSON.parse(readFileSync(TOKENS_PATH, "utf8"));

/** The four LOCKED opencode signature colors — Gate 1 must keep these exact. */
export const SIGNATURE = {
  background: "#0a0a0a",
  primary: "#fab283",
  accent: "#9d7cd8",
  secondary: "#5c9cf5",
} as const;

export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

// ANSI 24-bit truecolor SGR builders.
export const fg = (hex: string) => {
  const [r, g, b] = hexToRgb(hex);
  return `\x1b[38;2;${r};${g};${b}m`;
};
export const bg = (hex: string) => {
  const [r, g, b] = hexToRgb(hex);
  return `\x1b[48;2;${r};${g};${b}m`;
};
export const RESET = "\x1b[0m";

// ── ΔE76 (CIE76) in CIELab — adequate for a palette-tolerance gate ────────────
function srgbToLin(c: number) {
  c /= 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}
function rgbToXyz([r, g, b]: [number, number, number]) {
  const R = srgbToLin(r), G = srgbToLin(g), B = srgbToLin(b);
  return [
    R * 0.4124 + G * 0.3576 + B * 0.1805,
    R * 0.2126 + G * 0.7152 + B * 0.0722,
    R * 0.0193 + G * 0.1192 + B * 0.9505,
  ] as [number, number, number];
}
function pivot(t: number) {
  return t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116;
}
function rgbToLab(rgb: [number, number, number]) {
  let [x, y, z] = rgbToXyz(rgb);
  x /= 0.95047; y /= 1.0; z /= 1.08883;
  const fx = pivot(x), fy = pivot(y), fz = pivot(z);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)] as [number, number, number];
}
export function deltaE(hexA: string, hexB: string): number {
  const a = rgbToLab(hexToRgb(hexA));
  const b = rgbToLab(hexToRgb(hexB));
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

/** Every token color (color.* + syntax.*) as a flat hex list — for rogue-color checks. */
export function allTokenHexes(): string[] {
  const out: string[] = [];
  for (const v of Object.values(tokens.color)) out.push(v.hex);
  for (const v of Object.values(tokens.syntax))
    if (typeof v === "string" && v.startsWith("#")) out.push(v);
  return out;
}
