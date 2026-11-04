import type { EventKind } from "./contract";

// Four hue families and a neutral, validated as a set on the canvas surface (#0b1522, every pair, colour-blind
// included: worst CVD ΔE 9.4, worst normal-vision ΔE 16.8). The yellow sits above the lightness band on purpose — a
// border read from afar — and the kind is always written beside its colour: identity never rests on colour alone.
export type Family = "model" | "action" | "delegation" | "control" | "neutral";

const FAMILIES: Record<EventKind, Family> = {
  llm: "model",
  embedding: "model",
  tool: "action",
  mcp: "action",
  retrieval: "action",
  agent: "delegation",
  subagent: "delegation",
  evaluation: "control",
  interrupt: "control",
  state: "control",
  run: "neutral",
  node: "neutral",
  custom: "neutral",
};

export function family(kind: string): Family {
  return FAMILIES[kind as EventKind] ?? "neutral";
}

export const LEGEND: { family: Family; label: string }[] = [
  { family: "model", label: "model" },
  { family: "action", label: "action" },
  { family: "delegation", label: "delegation" },
  { family: "control", label: "control" },
  { family: "neutral", label: "step" },
];

// Status is a shape, never a hue shared with the kinds: ◌ running, ✓ done, ✕ error.
export const STATUS_GLYPH: Record<string, string> = { running: "◌", done: "✓", error: "✕", idle: "" };
