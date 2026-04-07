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
import { TaskDrawer } from '../components/TaskDrawer';
import styles from './Tasks.module.css';

// Statuses that indicate active background processing
const ACTIVE_STATUSES = new Set<TaskStatus>(['scripting', 'audio_preview', 'producing']);

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

function DroppableColumn({ status, tasks, onOpen }: { status: TaskStatus; tasks: Task[]; onOpen: (t: Task) => void }) {
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

export default function Tasks() {
  const { currentWorkspace } = useWorkspace();
  const { currentProject } = useProject();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [drawerTask, setDrawerTask] = useState<Task | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const load = useCallback(async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    try {
      const data = await fetchTasksForWorkspace(currentWorkspace.id);
      setTasks(data);
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

    // Optimistic update
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

  if (!currentWorkspace) {
    return <main className={styles.container}><p className={styles.empty}>Select a workspace first.</p></main>;
  }

  return (
    <main className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>{currentProject ? currentProject.name : 'All Tasks'}</h1>
      </div>

      {loading ? (
        <p className={styles.empty}>Loading…</p>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCorners} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
          <div className={styles.board}>
            {TASK_STATUSES.map((status) => (
              <DroppableColumn key={status} status={status} tasks={tasksByStatus[status]} onOpen={setDrawerTask} />
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

      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </main>
  );
}
