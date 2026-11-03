import type { EventKind } from "./contract";

// Three hue families, validated as a set on the canvas surface (every pair, colour-blind included); every other kind
// stays neutral. The kind is always written beside its colour: identity never rests on colour alone.
export type Family = "model" | "action" | "delegation" | "neutral";

const FAMILIES: Record<EventKind, Family> = {
  llm: "model",
  embedding: "model",
  tool: "action",
  mcp: "action",
  agent: "delegation",
  subagent: "delegation",
  run: "neutral",
  node: "neutral",
  retrieval: "neutral",
  interrupt: "neutral",
  state: "neutral",
  evaluation: "neutral",
  custom: "neutral",
};

export function family(kind: string): Family {
  return FAMILIES[kind as EventKind] ?? "neutral";
}

export const LEGEND: { family: Family; label: string }[] = [
  { family: "model", label: "model · llm, embedding" },
  { family: "action", label: "action · tool, mcp" },
  { family: "delegation", label: "delegation · agent, subagent" },
];

// Status is a shape, never a hue shared with the kinds: ◌ running, ✓ done, ✕ error.
export const STATUS_GLYPH: Record<string, string> = { running: "◌", done: "✓", error: "✕", idle: "" };
