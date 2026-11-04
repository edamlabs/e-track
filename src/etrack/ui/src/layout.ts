import type { Edge, Node } from "@xyflow/react";
import type { Topology } from "./contract";
import { type Family, family } from "./kinds";
import { hostNode, outer, type Span, type Status } from "./spans";

export const LANE_GAP = 280;
export const RANK_GAP = 150;
const CALL_KINDS = new Set(["llm", "embedding", "tool", "mcp", "retrieval", "subagent", "agent", "interrupt"]);

// What never changes while runs go by: the declared node, its place and its nature.
export interface StageData extends Record<string, unknown> {
  name: string;
  title: string;
  kind: string;
  family: Family;
  edge: "entry" | "exit" | "";
}

// What a run does to a declared node: its state, how often it ran, the call it is making, the calls it made by kind.
export interface Activity {
  status: Status | "idle";
  visits: number;
  current: { kind: string; name: string } | null;
  counts: [string, number][];
  last: boolean;
}

export interface Trail {
  walked: Set<string>;
  last: string;
}

export const IDLE: Activity = { status: "idle", visits: 0, current: null, counts: [], last: false };

// What a person reads for a node: its declared or given label, else its name.
export function titleOf(topology: Topology, name: string): string {
  return topology.nodes.find((node) => node.name === name)?.label || name;
}

// The declared graph on the server's grid (rank, lane) — built once per topology: the canvas never adds, drops or
// moves a node while a run goes on; the run only lights what is there.
export function layout(topology: Topology): { nodes: Node<StageData>[]; edges: Edge[] } {
  const widths = new Map<number, number>();
  for (const node of topology.nodes) widths.set(node.rank ?? 0, (widths.get(node.rank ?? 0) ?? 0) + 1);
  const nodes = topology.nodes.map((node): Node<StageData> => {
    const rank = node.rank ?? 0;
    return {
      id: node.id,
      type: "stage",
      position: { x: ((node.lane ?? 0) - ((widths.get(rank) ?? 1) - 1) / 2) * LANE_GAP, y: rank * RANK_GAP },
      data: {
        name: node.name,
        title: node.label || node.name,
        kind: node.kind ?? "node",
        family: family(node.kind ?? "node"),
        edge: node.entry ? "entry" : node.exit ? "exit" : "",
      },
    };
  });
  const edges = topology.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label || undefined,
    className: edge.loop ? "loop" : edge.conditional ? "conditional" : "",
  }));
  return { nodes, edges };
}

// The declared graph's own node visits in this run, oldest first: a subagent's inner nodes are its own graph's.
function visits(spans: Map<string, Span>): Span[] {
  return [...spans.values()].filter((span) => span.kind === "node" && outer(spans, span)).sort((a, b) => a.seq - b.seq);
}

// Every declared node's activity in this run, by node id; the node that ran last is marked.
export function activity(topology: Topology, spans: Map<string, Span>): Map<string, Activity> {
  const ids = new Map(topology.nodes.map((node) => [node.name, node.id]));
  const seen = visits(spans);
  const latest = seen[seen.length - 1];
  const found = new Map<string, Activity>();
  for (const span of seen) {
    const id = ids.get(span.name);
    if (!id) continue;
    const before = found.get(id) ?? IDLE;
    found.set(id, { ...before, status: span.status, visits: before.visits + 1, last: span === latest });
  }
  const counted = new Map<string, Map<string, number>>();
  for (const span of [...spans.values()].sort((a, b) => a.seq - b.seq)) {
    if (!CALL_KINDS.has(span.kind)) continue;
    const id = ids.get(hostNode(spans, span)?.name ?? "");
    const mine = id ? found.get(id) : undefined;
    if (!id || !mine) continue;
    const kinds = counted.get(id) ?? new Map<string, number>();
    kinds.set(span.kind, (kinds.get(span.kind) ?? 0) + 1);
    counted.set(id, kinds);
    if (span.status === "running") found.set(id, { ...mine, current: { kind: span.kind, name: span.name } });
  }
  for (const [id, kinds] of counted) {
    const mine = found.get(id);
    if (mine) found.set(id, { ...mine, counts: [...kinds] });
  }
  return found;
}

// The arcs this run walked: each visit is reached by the arc from the predecessor that ran most recently before it
// (an entry arc when no predecessor ran yet); the arc into the newest visit is the last one walked.
export function trail(topology: Topology, spans: Map<string, Span>): Trail {
  const byName = new Map(topology.nodes.map((node) => [node.name, node.id]));
  const names = new Map(topology.nodes.map((node) => [node.id, node.name]));
  const entries = new Set(topology.nodes.filter((node) => node.entry).map((node) => node.id));
  const into = new Map<string, Topology["edges"]>();
  for (const edge of topology.edges) into.set(edge.target, [...(into.get(edge.target) ?? []), edge]);
  const newest = new Map<string, number>();
  const walked = new Set<string>();
  let last = "";
  for (const span of visits(spans)) {
    const target = byName.get(span.name);
    if (!target) continue;
    let best: { id: string; seq: number } | null = null;
    for (const arc of into.get(target) ?? []) {
      const from = entries.has(arc.source) ? -1 : newest.get(names.get(arc.source) ?? "");
      if (from !== undefined && (!best || from > best.seq)) best = { id: arc.id, seq: from };
    }
    if (best) {
      walked.add(best.id);
      last = best.id;
    }
    newest.set(span.name, span.seq);
  }
  return { walked, last };
}
