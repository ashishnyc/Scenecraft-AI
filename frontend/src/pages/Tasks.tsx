import { useState, useEffect, useCallback } from 'react';
import type { DragEndEvent, DragStartEvent } from '@dnd-kit/core';
import {
  DndContext, DragOverlay,
  PointerSensor, useSensor, useSensors, closestCorners,
  useDroppable, useDraggable,
} from '@dnd-kit/core';
import { useWorkspace } from '../context/WorkspaceContext';
import { useProject } from '../context/ProjectContext';
import type { Task, TaskStatus } from '../api/tasks';
import { TASK_STATUSES, STATUS_LABELS, fetchTasksForWorkspace, transitionTask } from '../api/tasks';
import { useTaskEvents } from '../hooks/useTaskEvents';
import { Toast } from '../components/Toast';
import { VideoModal } from '../components/VideoModal';
import { NewVideoModal } from '../components/NewVideoModal';
import styles from './Tasks.module.css';

// ── Next-action hints per status ──────────────────────────────────────────────
const NEXT_ACTION: Record<TaskStatus, string> = {
  idea:          'Add video brief to start',
  approved:      'Drag to Scripting to generate script',
  scripting:     'AI is writing the script…',
  audio_preview: 'Review script & audio',
  script_review: 'Approve or request changes',
  producing:     'Video production in progress…',
  final_review:  'Review video & approve',
  scheduled:     'Set thumbnail & metadata',
  published:     'Live on YouTube',
};

// ── Phase groups ──────────────────────────────────────────────────────────────
const PHASES = [
  { label: 'Writing',    statuses: ['idea', 'approved', 'scripting'] as TaskStatus[] },
  { label: 'Review',     statuses: ['audio_preview', 'script_review', 'final_review'] as TaskStatus[] },
  { label: 'Production', statuses: ['producing', 'scheduled', 'published'] as TaskStatus[] },
];

// Map each status back to its phase
const PHASE_FOR_STATUS: Record<TaskStatus, typeof PHASES[number]> = {} as Record<TaskStatus, typeof PHASES[number]>;
for (const phase of PHASES) {
  for (const s of phase.statuses) PHASE_FOR_STATUS[s] = phase;
}

// Statuses that indicate active background processing
const ACTIVE_STATUSES = new Set<TaskStatus>(['scripting', 'audio_preview', 'producing']);

// ── Task card ─────────────────────────────────────────────────────────────────
interface TaskCardProps {
  task: Task;
  isDragging?: boolean;
  onClick?: () => void;
}

function TaskCard({ task, isDragging, onClick }: TaskCardProps) {
  const isActive = ACTIVE_STATUSES.has(task.status);
  const hasBrief = !!task.concept_brief;
  const phase = PHASE_FOR_STATUS[task.status];
  const currentIdx = phase.statuses.indexOf(task.status);

  return (
    <div
      className={`${styles.card} ${isDragging ? styles.cardDragging : ''}`}
      onClick={onClick}
    >
      <div className={styles.cardBody}>
        <div className={styles.cardLeft}>
          <div className={styles.cardHeader}>
            <p className={styles.cardTitle}>{task.title}</p>
            {isActive && <span className={styles.activeDot} title="Processing…" />}
          </div>
          {!hasBrief && task.status === 'idea' && (
            <span className={styles.noBriefHint}>needs brief</span>
          )}
        </div>

        {/* Mini vertical pipeline timeline — right side */}
        <div className={styles.cardTimeline}>
          {phase.statuses.map((s, idx) => {
            const done    = idx < currentIdx;
            const current = idx === currentIdx;
            const isLast  = idx === phase.statuses.length - 1;
            return (
              <div key={s} className={styles.cardTimelineRow}>
                <div className={styles.cardTimelineLeft}>
                  <div className={`${styles.cardTlDot} ${done ? styles.cardTlDotDone : current ? styles.cardTlDotCurrent : ''}`}>
                    {done && <span className={styles.cardTlCheck}>✓</span>}
                  </div>
                  {!isLast && <div className={styles.cardTlLine} />}
                </div>
                <span className={`${styles.cardTlLabel} ${done ? styles.cardTlLabelDone : current ? styles.cardTlLabelCurrent : ''}`}>
                  {STATUS_LABELS[s]}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function DraggableCard({ task, onOpen }: { task: Task; onOpen: (t: Task) => void }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: task.id });
  return (
    <div ref={setNodeRef} {...listeners} {...attributes} style={{ opacity: isDragging ? 0.4 : 1 }}>
      <TaskCard task={task} onClick={() => onOpen(task)} />
    </div>
  );
}

// ── Flat phase column (single droppable, no inner timeline) ──────────────────
function PhaseColumn({
  phase,
  tasksByStatus,
  onOpen,
}: {
  phase: { label: string; statuses: TaskStatus[] };
  tasksByStatus: Record<TaskStatus, Task[]>;
  onOpen: (t: Task) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: phase.label });
  const tasks = phase.statuses.flatMap((s) => tasksByStatus[s]);
  return (
    <div className={`${styles.phaseCol} ${isOver ? styles.phaseColOver : ''}`}>
      <div className={styles.phaseColHeader}>
        <span className={styles.phaseColLabel}>{phase.label}</span>
        {tasks.length > 0 && <span className={styles.phaseColCount}>{tasks.length}</span>}
      </div>
      <div className={styles.phaseColBody} ref={setNodeRef}>
        {tasks.length === 0
          ? <p className={styles.phaseColEmpty}>Drop cards here</p>
          : tasks.map((task) => <DraggableCard key={task.id} task={task} onOpen={onOpen} />)
        }
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Tasks() {
  const { currentWorkspace } = useWorkspace();
  const { currentProject, projects } = useProject();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [modalTask, setModalTask] = useState<Task | null>(null);
  const [showNewVideo, setShowNewVideo] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const load = useCallback(async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    try {
      const taskData = await fetchTasksForWorkspace(currentWorkspace.id);
      setTasks(taskData);
    } finally {
      setLoading(false);
    }
  }, [currentWorkspace]);

  useEffect(() => { load(); }, [load]);

  // Live updates from WebSocket
  useTaskEvents(useCallback((event) => {
    if (!currentWorkspace || event.workspace_id !== currentWorkspace.id) return;
    setTasks((prev) =>
      prev.map((t) =>
        t.id === event.task_id ? { ...t, status: event.status as TaskStatus } : t
      )
    );
  }, [currentWorkspace]));

  const visibleTasks = currentProject
    ? tasks.filter((t) => t.project_id === currentProject.id)
    : tasks;

  const tasksByStatus = TASK_STATUSES.reduce<Record<TaskStatus, Task[]>>((acc, s) => {
    acc[s] = visibleTasks.filter((t) => t.status === s);
    return acc;
  }, {} as Record<TaskStatus, Task[]>);

  const handleDragStart = ({ active }: DragStartEvent) => {
    setActiveTask(tasks.find((t) => t.id === active.id) ?? null);
  };

  const handleDragEnd = async ({ active, over }: DragEndEvent) => {
    setActiveTask(null);
    if (!over) return;
    const task = tasks.find((t) => t.id === active.id);
    if (!task) return;
    // Resolve phase label → first status of that phase
    const targetPhase = PHASES.find((p) => p.label === over.id);
    if (!targetPhase) return;
    // Already in this phase — no-op
    if (targetPhase.statuses.includes(task.status)) return;
    const targetStatus = targetPhase.statuses[0];

    setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, status: targetStatus } : t));

    try {
      const updated = await transitionTask(task.id, targetStatus);
      setTasks((prev) => prev.map((t) => t.id === updated.id ? updated : t));
    } catch (err: unknown) {
      setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, status: task.status } : t));
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Invalid transition';
      setToast(msg);
    }
  };

  const handleTaskUpdated = (updated: Task) => {
    setTasks((prev) => prev.map((t) => t.id === updated.id ? updated : t));
    setModalTask(updated);
  };

  if (!currentWorkspace) {
    return <main className={styles.container}><p className={styles.empty}>Select a workspace first.</p></main>;
  }

  return (
    <main className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>{currentProject ? currentProject.name : 'All Videos'}</h1>
        <button className={styles.newVideoBtn} onClick={() => setShowNewVideo(true)}>
          + New Video
        </button>
      </div>

      {loading ? (
        <p className={styles.empty}>Loading…</p>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCorners} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
          <div className={styles.board}>

            {/* Phase columns: Writing, Review, Production */}
            {PHASES.map((phase) => (
              <PhaseColumn
                key={phase.label}
                phase={phase}
                tasksByStatus={tasksByStatus}
                onOpen={setModalTask}
              />
            ))}
          </div>

          <DragOverlay>
            {activeTask ? <TaskCard task={activeTask} isDragging /> : null}
          </DragOverlay>
        </DndContext>
      )}

      {modalTask && (
        <VideoModal
          task={modalTask}
          onClose={() => setModalTask(null)}
          onUpdated={handleTaskUpdated}
        />
      )}

      {showNewVideo && (
        <NewVideoModal
          projects={projects}
          defaultProjectId={currentProject?.id}
          onCreated={() => { setShowNewVideo(false); load(); }}
          onCancel={() => setShowNewVideo(false)}
        />
      )}

      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </main>
  );
}
