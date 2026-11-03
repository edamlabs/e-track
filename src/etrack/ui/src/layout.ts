import type { Edge, Node } from "@xyflow/react";
import type { Topology } from "./contract";
import { hostNode, outer, type Span, type Status } from "./spans";

export const LANE_GAP = 280;
export const RANK_GAP = 130;
const CHILD_GAP = 38;
const CHILD_SHIFT = 250;
const CHILDREN = 6;
const LIVE_KINDS = new Set(["llm", "tool", "mcp", "subagent", "retrieval", "interrupt"]);

export interface StageData extends Record<string, unknown> {
  label: string;
  status: Status | "idle";
  visits: number;
  edge: "entry" | "exit" | "";
}

export interface CallData extends Record<string, unknown> {
  kind: string;
  label: string;
  status: Status;
  span: string;
}

// The declared graph on the server's grid (rank, lane), each node lit by the newest span of its name.
export function stages(topology: Topology, spans: Map<string, Span>): Node<StageData>[] {
  const widths = new Map<number, number>();
  for (const node of topology.nodes) widths.set(node.rank ?? 0, (widths.get(node.rank ?? 0) ?? 0) + 1);
  const runs = [...spans.values()].filter((span) => span.kind === "node" && outer(spans, span));
  return topology.nodes.map((node) => {
    const mine = runs.filter((span) => span.name === node.name || span.name === node.id);
    const newest = mine.reduce<Span | undefined>(
      (last, span) => (!last || span.seq > last.seq ? span : last),
      undefined,
    );
    const rank = node.rank ?? 0;
    return {
      id: node.id,
      type: "stage",
      position: { x: ((node.lane ?? 0) - ((widths.get(rank) ?? 1) - 1) / 2) * LANE_GAP, y: rank * RANK_GAP },
      data: {
        label: node.name,
        status: newest?.status ?? "idle",
        visits: mine.length,
        edge: node.entry ? "entry" : node.exit ? "exit" : "",
      },
    };
  });
}

export function arcs(topology: Topology, spans: Map<string, Span>): Edge[] {
  const running = new Set([...spans.values()].filter((span) => span.status === "running").map((span) => span.name));
  return topology.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label || undefined,
    animated: running.has(edge.target),
    className: edge.loop ? "loop" : edge.conditional ? "conditional" : "",
  }));
}

// The calls a node made in this run — model, tools, MCP, subagents — drawn beside it, newest last.
export function calls(
  stageNodes: Node<StageData>[],
  spans: Map<string, Span>,
): { nodes: Node<CallData>[]; edges: Edge[] } {
  const byName = new Map(stageNodes.map((node) => [node.data.label, node]));
  const grouped = new Map<string, Span[]>();
  for (const span of spans.values()) {
    if (!LIVE_KINDS.has(span.kind)) continue;
    const host = hostNode(spans, span);
    const stage = host && byName.get(host.name);
    if (stage) grouped.set(stage.id, [...(grouped.get(stage.id) ?? []), span]);
  }
  const nodes: Node<CallData>[] = [];
  const edges: Edge[] = [];
  for (const [stageId, mine] of grouped) {
    const stage = stageNodes.find((node) => node.id === stageId);
    if (!stage) continue;
    const shown = mine.sort((a, b) => a.seq - b.seq).slice(-CHILDREN);
    shown.forEach((span, index) => {
      const id = `call:${span.id}`;
      nodes.push({
        id,
        type: "call",
        position: {
          x: stage.position.x + CHILD_SHIFT,
          y: stage.position.y + (index - (shown.length - 1) / 2) * CHILD_GAP,
        },
        data: { kind: span.kind, label: span.name, status: span.status, span: span.id },
      });
      edges.push({ id: `wire:${span.id}`, source: stageId, target: id, className: "wire", sourceHandle: "side" });
    });
  }
  return { nodes, edges };
}
