import { Handle, type Node, type NodeProps, Position } from "@xyflow/react";
import { STATUS_GLYPH } from "./kinds";
import type { CallData, StageData } from "./layout";

export function StageNode({ data, selected }: NodeProps<Node<StageData>>) {
  const renamed = data.title !== data.name;
  return (
    <div
      className={`stage fam-${data.family} ${data.status} ${data.edge} ${selected ? "selected" : ""}`}
      title={data.name}
    >
      <Handle type="target" position={Position.Top} />
      <span className={`glyph ${data.status}`}>{STATUS_GLYPH[data.status]}</span>
      {data.kind !== "node" && <span className="kind">{data.kind}</span>}
      <span className="text">
        <span className="label">{data.title}</span>
        {renamed && <span className="name">{data.name}</span>}
      </span>
      {data.visits > 1 && <span className="visits">×{data.visits}</span>}
      <Handle type="source" position={Position.Bottom} />
      <Handle type="source" id="side" position={Position.Right} />
    </div>
  );
}

export function CallNode({ data, selected }: NodeProps<Node<CallData>>) {
  return (
    <div className={`call fam-${data.family} ${data.status} ${selected ? "selected" : ""}`} title={data.label}>
      <Handle type="target" position={Position.Left} />
      <span className={`glyph ${data.status}`}>{STATUS_GLYPH[data.status]}</span>
      <span className="kind">{data.kind}</span>
      <span className="label">{data.label}</span>
    </div>
  );
}

export const NODE_TYPES = { stage: StageNode, call: CallNode };
