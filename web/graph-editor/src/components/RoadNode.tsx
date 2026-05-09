import { Fragment } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

export type RoadNodeData = {
  logicalId: number;
};

export type RoadNodeType = Node<RoadNodeData, "road">;

const SIDES = [
  { position: Position.Top, id: "top" },
  { position: Position.Right, id: "right" },
  { position: Position.Bottom, id: "bottom" },
  { position: Position.Left, id: "left" },
] as const;

export function RoadNode({ data }: NodeProps<RoadNodeType>) {
  return (
    <div className="road-node">
      {SIDES.map(({ position, id }) => (
        <Fragment key={id}>
          <Handle type="target" position={position} id={`t-${id}`} />
          <Handle type="source" position={position} id={`s-${id}`} />
        </Fragment>
      ))}
      <span className="road-node__label">{data.logicalId}</span>
    </div>
  );
}
