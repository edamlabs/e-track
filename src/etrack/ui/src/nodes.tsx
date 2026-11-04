import { Handle, type Node, type NodeProps, Position } from "@xyflow/react";
import { family, STATUS_GLYPH } from "./kinds";
import type { StageData } from "./layout";
import { useActivity } from "./live";

// A declared node, lit by the run: its nature as a coloured border and a written kind, its title, the call it is
// making now and the calls it made, counted by kind. Its size never changes, so the graph never moves.
export function StageNode({ id, data }: NodeProps<Node<StageData>>) {
  const { activity, picked } = useActivity(id);
  const classes = [
    "stage",
    `fam-${data.family}`,
    activity.status,
    data.edge,
    activity.last ? "last" : "",
    picked ? "picked" : "",
  ];
  return (
    <div className={classes.filter(Boolean).join(" ")} title={data.name}>
      <Handle type="target" position={Position.Top} />
      {data.edge ? (
        <span className="title">{data.title}</span>
      ) : (
        <>
          <span className="head">
            <span className={`glyph ${activity.status}`}>{STATUS_GLYPH[activity.status]}</span>
            <span className="kind">{data.kind}</span>
            {activity.visits > 1 && <span className="visits">×{activity.visits}</span>}
          </span>
          <span className="title">{data.title}</span>
          <span className="now">
            {activity.current && (
              <>
                <span className={`kind fam-${family(activity.current.kind)}`}>{activity.current.kind}</span>{" "}
                {activity.current.name}
              </>
            )}
          </span>
          <span className="counts">
            {activity.counts.map(([kind, count]) => (
              <span key={kind} className={`count fam-${family(kind)}`}>
                {kind} {count}
              </span>
            ))}
          </span>
        </>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export const NODE_TYPES = { stage: StageNode };
