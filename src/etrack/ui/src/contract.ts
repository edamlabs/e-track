/* Generated from msgspec.json.schema by `make ui-types`: never edit by hand. */

/**
 * What a span is. `CUSTOM` is the fallback for whatever a source or a project names that no other kind covers.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "EventKind".
 */
export type EventKind =
  | "agent"
  | "custom"
  | "embedding"
  | "evaluation"
  | "interrupt"
  | "llm"
  | "mcp"
  | "node"
  | "retrieval"
  | "run"
  | "state"
  | "subagent"
  | "tool";
/**
 * Where a span is in its life; `INSTANT` is a span that is born and closed at once (an interrupt, a state, a score).
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "EventPhase".
 */
export type EventPhase = "delta" | "end" | "error" | "instant" | "start";
/**
 * What a streamed piece carries — LangChain's v1 content blocks, AG-UI's message kinds; `CUSTOM` for the rest.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Part".
 */
export type Part = "audio" | "custom" | "file" | "image" | "reasoning" | "text" | "tool_call" | "video";

export interface Contract {}
/**
 * The declared graph: its nodes, its arcs, and the grid's extent once placed.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Topology".
 */
export interface Topology {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  ranks?: number;
  lanes?: number;
}
/**
 * One declared node: its id, the name a span carries when it runs, and its place once laid out.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "TopologyNode".
 */
export interface TopologyNode {
  id: string;
  name: string;
  entry?: boolean;
  exit?: boolean;
  rank?: number;
  lane?: number;
}
/**
 * One declared arc: conditional when a router chooses it, `loop` when it closes a cycle.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "TopologyEdge".
 */
export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  conditional?: boolean;
  label?: string;
  loop?: boolean;
}
/**
 * A kept thread as a picker lists it: its next offset, its runs in the order they began, its last frame's time.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "LiveSummary".
 */
export interface LiveSummary {
  thread: string;
  offset: number;
  runs: string[];
  last: string;
}
/**
 * One frame of a run: who, where in the tree, what and when, and what it carried.
 *
 * `node`, `ns` and `step` are the graph coordinates when the source has a graph (the node a span runs under, its
 * subgraph path, the superstep); `visit` counts how many times the run has entered that node. `message_id` and
 * `call_id` tie a frame to the chat message or the tool call a client renders. `latency_ms` is set on END and ERROR.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "RunEvent".
 */
export interface RunEvent {
  v?: number;
  run_id: string;
  thread_id?: string;
  seq: number;
  id: string;
  parent?: string;
  kind: EventKind;
  phase: EventPhase;
  name?: string;
  node?: string;
  ns?: string;
  step?: number | null;
  visit?: number | null;
  part?: Part | null;
  message_id?: string;
  call_id?: string;
  at?: string;
  latency_ms?: number | null;
  model?: ModelRef | null;
  usage?: Usage | null;
  error?: Failure | null;
  payload?: {};
  attributes?: {};
}
/**
 * Which model served a call: the provider, the model's name, and the request parameters worth keeping.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ModelRef".
 */
export interface ModelRef {
  provider?: string;
  name?: string;
  params?: {};
}
/**
 * Tokens a model call spent, by kind, and its cost when the source knows it.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Usage".
 */
export interface Usage {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  reasoning_tokens?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
  cost_usd?: number | null;
}
/**
 * Why a span failed: the exception's type and its message.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Failure".
 */
export interface Failure {
  type: string;
  message?: string;
}
