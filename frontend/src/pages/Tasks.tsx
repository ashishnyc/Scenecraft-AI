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
import type { Pitch } from '../api/pitches';
import { fetchPitches, approvePitch, rejectPitch } from '../api/pitches';
import { useTaskEvents } from '../hooks/useTaskEvents';
import { Toast } from '../components/Toast';
import { TaskDrawer } from '../components/TaskDrawer';
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

// ── Phase groups (SA-99) ──────────────────────────────────────────────────────
const PHASES = [
  { label: 'Writing',    statuses: ['idea', 'approved', 'scripting'] as TaskStatus[] },
  { label: 'Review',     statuses: ['audio_preview', 'script_review', 'final_review'] as TaskStatus[] },
  { label: 'Production', statuses: ['producing', 'scheduled', 'published'] as TaskStatus[] },
];

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
  return (
    <div
      className={`${styles.card} ${isDragging ? styles.cardDragging : ''}`}
      onClick={onClick}
    >
      <div className={styles.cardHeader}>
        <p className={styles.cardTitle}>{task.title}</p>
        {isActive && <span className={styles.activeDot} title="Processing…" />}
      </div>
      <p className={styles.nextAction}>{NEXT_ACTION[task.status]}</p>
      <div className={styles.cardFooter}>
        <span className={`${styles.badge} ${styles[`badge_${task.status}`]}`}>
          {STATUS_LABELS[task.status]}
        </span>
        {!hasBrief && task.status === 'idea' && (
          <span className={styles.noBriefHint}>needs brief</span>
        )}
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

function DroppableColumn({
  status, tasks, onOpen,
}: { status: TaskStatus; tasks: Task[]; onOpen: (t: Task) => void }) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  return (
    <div className={`${styles.column} ${isOver ? styles.columnOver : ''}`} ref={setNodeRef}>
      <div className={styles.columnHeader}>
        <span className={styles.columnTitle}>{STATUS_LABELS[status]}</span>
        <span className={styles.columnCount}>{tasks.length}</span>
      </div>
      <div className={styles.columnBody}>
        {tasks.map((task) => <DraggableCard key={task.id} task={task} onOpen={onOpen} />)}
      </div>
    </div>
  );
}

// ── AI Ideas column (SA-97) ───────────────────────────────────────────────────
function PitchCard({
  pitch,
  onApprove,
  onReject,
}: { pitch: Pitch; onApprove: (p: Pitch) => void; onReject: (p: Pitch) => void }) {
  return (
    <div className={styles.pitchCard}>
      <p className={styles.cardTitle}>{pitch.title}</p>
      <p className={styles.pitchSummary}>{pitch.concept_summary}</p>
      {pitch.appeal_score != null && (
        <span className={styles.appealBadge}>Appeal {pitch.appeal_score}/10</span>
      )}
      <div className={styles.pitchActions}>
        <button className={styles.pitchApproveBtn} onClick={() => onApprove(pitch)}>→ Add to board</button>
        <button className={styles.pitchRejectBtn} onClick={() => onReject(pitch)}>✕</button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Tasks() {
  const { currentWorkspace } = useWorkspace();
  const { currentProject, projects } = useProject();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [pitches, setPitches] = useState<Pitch[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [drawerTask, setDrawerTask] = useState<Task | null>(null);
  const [showNewVideo, setShowNewVideo] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const load = useCallback(async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    try {
      const [taskData, pitchData] = await Promise.all([
        fetchTasksForWorkspace(currentWorkspace.id),
        fetchPitches(currentWorkspace.id, 'pending').catch(() => [] as Pitch[]),
      ]);
      setTasks(taskData);
      setPitches(pitchData);
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
    const targetStatus = over.id as TaskStatus;
    const task = tasks.find((t) => t.id === active.id);
    if (!task || task.status === targetStatus) return;

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
    setDrawerTask(updated);
  };

  const handleApprovePitch = async (pitch: Pitch) => {
    if (!currentWorkspace) return;
    try {
      const task = await approvePitch(currentWorkspace.id, pitch.id, currentProject?.id);
      setPitches((prev) => prev.filter((p) => p.id !== pitch.id));
      setTasks((prev) => [...prev, task]);
    } catch {
      setToast('Failed to approve pitch');
    }
  };

  const handleRejectPitch = async (pitch: Pitch) => {
    if (!currentWorkspace) return;
    try {
      await rejectPitch(currentWorkspace.id, pitch.id);
      setPitches((prev) => prev.filter((p) => p.id !== pitch.id));
    } catch {
      setToast('Failed to reject pitch');
    }
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

            {/* AI Ideas column (SA-97) */}
            <div className={styles.phaseGroup}>
              <div className={styles.phaseHeader}>
                <span className={styles.phaseLabel}>AI Ideas</span>
                <span className={styles.phaseCount}>{pitches.length}</span>
              </div>
              <div className={styles.phaseColumns}>
                <div className={styles.column}>
                  <div className={styles.columnHeader}>
                    <span className={styles.columnTitle}>Suggestions</span>
                    <span className={styles.columnCount}>{pitches.length}</span>
                  </div>
                  <div className={styles.columnBody}>
                    {pitches.length === 0 ? (
                      <p className={styles.pitchEmpty}>No AI ideas pending</p>
                    ) : (
                      pitches.map((p) => (
                        <PitchCard
                          key={p.id}
                          pitch={p}
                          onApprove={handleApprovePitch}
                          onReject={handleRejectPitch}
                        />
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Phase groups (SA-99) */}
            {PHASES.map((phase) => (
              <div key={phase.label} className={styles.phaseGroup}>
                <div className={styles.phaseHeader}>
                  <span className={styles.phaseLabel}>{phase.label}</span>
                  <span className={styles.phaseCount}>
                    {phase.statuses.reduce((n, s) => n + tasksByStatus[s].length, 0)}
                  </span>
                </div>
                <div className={styles.phaseColumns}>
                  {phase.statuses.map((status) => (
                    <DroppableColumn key={status} status={status} tasks={tasksByStatus[status]} onOpen={setDrawerTask} />
                  ))}
                </div>
              </div>
            ))}
          </div>

          <DragOverlay>
            {activeTask ? <TaskCard task={activeTask} isDragging /> : null}
          </DragOverlay>
        </DndContext>
      )}

      {drawerTask && (
        <TaskDrawer
          task={drawerTask}
          onClose={() => setDrawerTask(null)}
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
