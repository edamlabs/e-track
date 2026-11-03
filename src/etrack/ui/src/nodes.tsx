import { Handle, type Node, type NodeProps, Position } from "@xyflow/react";
import type { CallData, StageData } from "./layout";

export function StageNode({ data }: NodeProps<Node<StageData>>) {
  return (
    <div className={`stage ${data.status} ${data.edge}`}>
      <Handle type="target" position={Position.Top} />
      <span className="label" title={data.label}>
        {data.label}
      </span>
      {data.visits > 1 && <span className="visits">×{data.visits}</span>}
      <Handle type="source" position={Position.Bottom} />
      <Handle type="source" id="side" position={Position.Right} />
    </div>
  );
}

export function CallNode({ data }: NodeProps<Node<CallData>>) {
  return (
    <div className={`call ${data.status} ${data.kind}`}>
      <Handle type="target" position={Position.Left} />
      <span className="kind">{data.kind}</span>
      <span className="label" title={data.label}>
        {data.label}
      </span>
    </div>
  );
}

export const NODE_TYPES = { stage: StageNode, call: CallNode };
