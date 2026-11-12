import type { EventKind, RunEvent, Usage } from "./contract";

export type Status = "running" | "done" | "error";

export interface Span {
  id: string;
  parent: string;
  kind: EventKind;
  name: string;
  ns: string;
  status: Status;
  seq: number;
  latency: number | null;
  text: string;
  reasoning: string;
  usage: Usage | null;
  error: string;
  input: unknown;
  output: unknown;
}

const CLOSED: Partial<Record<RunEvent["phase"], Status>> = { end: "done", error: "error", instant: "done" };

function opened(event: RunEvent): Span {
  return {
    id: event.id,
    parent: event.parent ?? "",
    kind: event.kind,
    name: event.name || event.kind,
    ns: event.ns ?? "",
    status: event.phase === "start" ? "running" : (CLOSED[event.phase] ?? "done"),
    seq: event.seq,
    latency: null,
    text: "",
    reasoning: "",
    usage: null,
    error: "",
    input: event.payload ?? {},
    output: null,
  };
}

function delta(span: Span, event: RunEvent): Span {
  const piece = String((event.payload as { delta?: unknown } | undefined)?.delta ?? "");
  return event.part === "reasoning"
    ? { ...span, reasoning: span.reasoning + piece }
    : { ...span, text: span.text + piece };
}

function closed(span: Span, event: RunEvent): Span {
  return {
    ...span,
    status: CLOSED[event.phase] ?? "done",
    latency: event.latency_ms ?? null,
    usage: event.usage ?? null,
    error: event.error ? `${event.error.type}: ${event.error.message ?? ""}` : "",
    output: event.payload ?? null,
  };
}

// One run's frames folded into its spans, keyed by id; frames arrive in `seq` order per run. The map is the caller's,
// filled in place: one fold over a run is O(frames), never a copy per frame.
export function fold(spans: Map<string, Span>, event: RunEvent): Map<string, Span> {
  const known = spans.get(event.id);
  switch (event.phase) {
    case "start":
    case "instant":
      spans.set(event.id, opened(event));
      break;
    case "delta":
      if (known) spans.set(event.id, delta(known, event));
      break;
    default:
      if (known) spans.set(event.id, closed(known, event));
  }
  return spans;
}

// A span's ancestors, nearest first; a cycle in a broken stream ends the walk instead of looping.
function ancestors(spans: Map<string, Span>, span: Span): Span[] {
  const found: Span[] = [];
  const seen = new Set([span.id]);
  let current = spans.get(span.parent);
  while (current && !seen.has(current.id)) {
    found.push(current);
    seen.add(current.id);
    current = spans.get(current.parent);
  }
  return found;
}

// Whether a span belongs to the declared graph's own run: no subagent above it. A subagent runs its own graph,
// whose nodes may share names with the outer ones; they show in the span tree, not on the declared nodes.
export function outer(spans: Map<string, Span>, span: Span): boolean {
  return !ancestors(spans, span).some((above) => above.kind === "subagent");
}

// The declared node a call runs under: its nearest node ancestor, when the call is the outer graph's own.
export function hostNode(spans: Map<string, Span>, span: Span): Span | undefined {
  return outer(spans, span) ? ancestors(spans, span).find((above) => above.kind === "node") : undefined;
}
