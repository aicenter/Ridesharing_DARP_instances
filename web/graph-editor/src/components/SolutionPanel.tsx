import { useMemo, useState, type CSSProperties } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  closestCorners,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  SOLUTION_POOL_ID,
  formatActionLabel,
  type FleetVehicle,
  type SolutionItems,
} from "../lib/solutionModel";

type Props = {
  items: SolutionItems;
  onItemsChange: (next: SolutionItems) => void;
  vehicles: FleetVehicle[];
  onClose: () => void;
  onResetFromGraph: () => void;
  onExportSolution: () => void;
};

function findContainer(id: string, data: SolutionItems): string | undefined {
  if (id in data) return id;
  for (const [containerId, list] of Object.entries(data)) {
    if (list.includes(id)) return containerId;
  }
  return undefined;
}

function SortableAction({ id, label }: { id: string; label: string }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });
  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.45 : 1,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      className="solution-panel__action"
      {...attributes}
      {...listeners}
    >
      {label}
    </div>
  );
}

function PlanSection({
  containerId,
  title,
  subtitle,
  itemIds,
}: {
  containerId: string;
  title: string;
  subtitle?: string;
  itemIds: string[];
}) {
  const { setNodeRef, isOver } = useDroppable({ id: containerId });
  return (
    <section
      ref={setNodeRef}
      className={`solution-panel__section${isOver ? " solution-panel__section--over" : ""}`}
    >
      <header className="solution-panel__section-head">
        <h3 className="solution-panel__section-title">{title}</h3>
        {subtitle ? <p className="solution-panel__section-sub">{subtitle}</p> : null}
      </header>
      <SortableContext items={itemIds} strategy={verticalListSortingStrategy}>
        <ul className="solution-panel__list">
          {itemIds.map((id) => (
            <li key={id} className="solution-panel__list-item">
              <SortableAction id={id} label={formatActionLabel(id)} />
            </li>
          ))}
        </ul>
      </SortableContext>
      {itemIds.length === 0 ? (
        <p className="solution-panel__empty">Drop actions here</p>
      ) : null}
    </section>
  );
}

function handleDragEndMutation(event: DragEndEvent, items: SolutionItems): SolutionItems | null {
  const { active, over } = event;
  if (!over) return null;

  const activeId = String(active.id);
  const overId = String(over.id);
  if (activeId === overId) return null;

  const activeContainer = findContainer(activeId, items);
  const overContainer = findContainer(overId, items);
  if (!activeContainer || !overContainer) return null;

  if (activeContainer === overContainer) {
    const list = items[activeContainer];
    const oldIndex = list.indexOf(activeId);
    const newIndex = list.indexOf(overId);
    if (oldIndex < 0 || newIndex < 0) return null;
    return {
      ...items,
      [activeContainer]: arrayMove(list, oldIndex, newIndex),
    };
  }

  const fromList = [...items[activeContainer]];
  const toList = [...items[overContainer]];
  const fromIdx = fromList.indexOf(activeId);
  if (fromIdx < 0) return null;
  const [moved] = fromList.splice(fromIdx, 1);

  let insertIndex: number;
  if (overId in items) {
    insertIndex = toList.length;
  } else {
    const overIdx = toList.indexOf(overId);
    insertIndex = overIdx >= 0 ? overIdx : toList.length;
  }
  toList.splice(insertIndex, 0, moved);

  return {
    ...items,
    [activeContainer]: fromList,
    [overContainer]: toList,
  };
}

export function SolutionPanel({
  items,
  onItemsChange,
  vehicles,
  onClose,
  onResetFromGraph,
  onExportSolution,
}: Props) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    }),
  );

  const sortedVehicleIds = useMemo(
    () =>
      [...vehicles]
        .sort((a, b) => a.vehicleId - b.vehicleId)
        .map((v) => v.vehicleId),
    [vehicles],
  );

  const vehicleById = useMemo(() => new Map(vehicles.map((v) => [v.vehicleId, v])), [vehicles]);

  return (
    <aside className="solution-panel" aria-label="Solution builder">
      <header className="solution-panel__header">
        <h2 className="solution-panel__title">Solution</h2>
        <div className="solution-panel__header-actions">
          <button type="button" className="solution-panel__btn" onClick={onExportSolution}>
            Export solution
          </button>
          <button type="button" className="solution-panel__btn" onClick={onResetFromGraph}>
            Reset from graph
          </button>
          <button type="button" className="solution-panel__btn solution-panel__btn--ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </header>
      <p className="solution-panel__hint">
        Drag to reorder within a vehicle or the unassigned list, or move actions between vehicles.
        Use <strong>Reset from graph</strong> after you add or change requests on the map.
      </p>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={({ active }: DragStartEvent) => setActiveId(String(active.id))}
        onDragEnd={(e) => {
          setActiveId(null);
          const next = handleDragEndMutation(e, items);
          if (next) onItemsChange(next);
        }}
        onDragCancel={() => setActiveId(null)}
      >
        <div className="solution-panel__scroll">
          <PlanSection
            containerId={SOLUTION_POOL_ID}
            title="Unassigned"
            subtitle="Pickup / dropoff stops not on a vehicle plan yet"
            itemIds={items[SOLUTION_POOL_ID] ?? []}
          />
          {sortedVehicleIds.map((vid) => {
            const v = vehicleById.get(vid);
            const cid = `v:${vid}`;
            return (
              <PlanSection
                key={cid}
                containerId={cid}
                title={`Vehicle ${vid}`}
                subtitle={v ? `Node ${v.nodeId} · cap ${v.capacity}` : undefined}
                itemIds={items[cid] ?? []}
              />
            );
          })}
          {sortedVehicleIds.length === 0 ? (
            <p className="solution-panel__note">Add vehicles on the map to create plans.</p>
          ) : null}
        </div>

        <DragOverlay dropAnimation={null}>
          {activeId ? (
            <div className="solution-panel__action solution-panel__action--overlay">
              {formatActionLabel(activeId)}
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </aside>
  );
}
