import { useEffect, useState, useCallback } from 'react';
import { useWorkspace } from '../context/WorkspaceContext';
import { useProject } from '../context/ProjectContext';
import type { Task, TaskStatus } from '../api/tasks';
import { STATUS_LABELS, fetchTasksForWorkspace } from '../api/tasks';
import { NewVideoModal } from '../components/NewVideoModal';
import { VideoModal } from '../components/VideoModal';
import { useProject as useProjectCtx } from '../context/ProjectContext';
import styles from './VideoTable.module.css';

const STATUS_COLORS: Record<TaskStatus, string> = {
  brainstorm:      '#6366f1',
  idea_review:     '#818cf8',
  outline:         '#8b5cf6',
  writing_review:  '#a78bfa',
  generate_script: '#f59e0b',
  script_review:   '#fbbf24',
  generate_clips:  '#10b981',
  assemble_clips:  '#34d399',
  video_review:    '#4ade80',
  prepare_metadata:'#3b82f6',
  publish:         '#60a5fa',
  closed:          '#93c5fd',
};

type SortKey = 'title' | 'status';

export default function VideoTable() {
  const { currentWorkspace } = useWorkspace();
  const { currentProject, projects } = useProjectCtx();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalTask, setModalTask] = useState<Task | null>(null);
  const [showNewVideo, setShowNewVideo] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('status');
  const [sortAsc, setSortAsc] = useState(true);
  const [filter, setFilter] = useState('');

  const load = useCallback(async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    try {
      const all = await fetchTasksForWorkspace(currentWorkspace.id);
      setTasks(currentProject ? all.filter(t => t.project_id === currentProject.id) : all);
    } finally {
      setLoading(false);
    }
  }, [currentWorkspace, currentProject]);

  useEffect(() => { load(); }, [load]);

  const handleTaskUpdated = (updated: Task) => {
    setTasks(prev => prev.map(t => t.id === updated.id ? updated : t));
    setModalTask(updated);
  };

  const STATUS_ORDER: Record<TaskStatus, number> = {
    brainstorm: 0, idea_review: 1,
    outline: 2, writing_review: 3,
    generate_script: 4, script_review: 5,
    generate_clips: 6, assemble_clips: 7, video_review: 8,
    prepare_metadata: 9, publish: 10, closed: 11,
  };

  const filtered = tasks.filter(t =>
    !filter || t.title.toLowerCase().includes(filter.toLowerCase()) ||
    (t.concept_brief ?? '').toLowerCase().includes(filter.toLowerCase())
  );

  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    if (sortKey === 'title')  cmp = a.title.localeCompare(b.title);
    if (sortKey === 'status') cmp = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
    return sortAsc ? cmp : -cmp;
  });

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(v => !v);
    else { setSortKey(key); setSortAsc(true); }
  };

  const SortIcon = ({ col }: { col: SortKey }) =>
    sortKey === col ? <span>{sortAsc ? ' ↑' : ' ↓'}</span> : null;

  if (!currentWorkspace) return <main className={styles.container}><p className={styles.empty}>Select a workspace.</p></main>;

  return (
    <main className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>{currentProject ? currentProject.name : 'All Videos'}</h1>
        <div className={styles.headerActions}>
          <input
            className={styles.search}
            placeholder="Search videos…"
            value={filter}
            onChange={e => setFilter(e.target.value)}
          />
          <button className={styles.newBtn} onClick={() => setShowNewVideo(true)}>+ New Video</button>
        </div>
      </div>

      {loading ? (
        <p className={styles.empty}>Loading…</p>
      ) : sorted.length === 0 ? (
        <p className={styles.empty}>{filter ? 'No videos match your search.' : 'No videos yet.'}</p>
      ) : (
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={`${styles.th} ${styles.thSortable}`} onClick={() => toggleSort('title')}>
                  Title <SortIcon col="title" />
                </th>
                <th className={`${styles.th} ${styles.thSortable}`} onClick={() => toggleSort('status')}>
                  Status <SortIcon col="status" />
                </th>
                <th className={styles.th}>Brief</th>
                <th className={styles.th}>Script</th>
                <th className={styles.th}>Audio</th>
                <th className={styles.th}>Video</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(task => (
                <tr key={task.id} className={styles.tr}>
                  <td className={styles.td}>
                    <button className={styles.titleLink} onClick={() => setModalTask(task)}>
                      {task.title}
                    </button>
                  </td>
                  <td className={styles.td}>
                    <span
                      className={styles.statusPill}
                      style={{ color: STATUS_COLORS[task.status], borderColor: STATUS_COLORS[task.status] + '44' }}
                    >
                      {STATUS_LABELS[task.status]}
                    </span>
                  </td>
                  <td className={styles.td}>
                    <span className={styles.briefCell}>
                      {task.concept_brief ? task.concept_brief.slice(0, 60) + (task.concept_brief.length > 60 ? '…' : '') : <span className={styles.missing}>—</span>}
                    </span>
                  </td>
                  <td className={styles.td}>
                    <span className={task.script?.outline ? styles.dot : styles.dotEmpty}>
                      {task.script?.outline ? '●' : '○'}
                    </span>
                  </td>
                  <td className={styles.td}>
                    <span className={task.script?.audio_stems ? styles.dot : styles.dotEmpty}>
                      {task.script?.audio_stems ? '●' : '○'}
                    </span>
                  </td>
                  <td className={styles.td}>
                    <span className={task.final_video_url ? styles.dot : styles.dotEmpty}>
                      {task.final_video_url ? '●' : '○'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalTask && (
        <VideoModal
          task={modalTask}
          onClose={() => setModalTask(null)}
          onUpdated={handleTaskUpdated}
          onDeleted={(id) => { setTasks(prev => prev.filter(t => t.id !== id)); setModalTask(null); }}
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
    </main>
  );
}
