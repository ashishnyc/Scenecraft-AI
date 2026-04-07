import { useEffect, useState } from 'react';
import { useWorkspace } from '../context/WorkspaceContext';
import { useProject } from '../context/ProjectContext';
import type { Task, TaskStatus } from '../api/tasks';
import { TASK_STATUSES, STATUS_LABELS, fetchTasksForWorkspace } from '../api/tasks';
import { VideoModal } from '../components/VideoModal';
import styles from './SeriesDashboard.module.css';

const PHASE_MAP: Record<TaskStatus, { phase: string; color: string }> = {
  brainstorm:      { phase: 'Idea',       color: '#6366f1' },
  idea_review:     { phase: 'Idea',       color: '#818cf8' },
  outline:         { phase: 'Writing',    color: '#8b5cf6' },
  writing_review:  { phase: 'Writing',    color: '#a78bfa' },
  generate_script: { phase: 'Scripting',  color: '#f59e0b' },
  script_review:   { phase: 'Scripting',  color: '#fbbf24' },
  generate_clips:  { phase: 'Video',      color: '#10b981' },
  assemble_clips:  { phase: 'Video',      color: '#34d399' },
  video_review:    { phase: 'Video',      color: '#4ade80' },
  prepare_metadata:{ phase: 'Upload',     color: '#3b82f6' },
  publish:         { phase: 'Upload',     color: '#60a5fa' },
  closed:          { phase: 'Upload',     color: '#93c5fd' },
};

const STAGE_GROUPS = [
  { label: 'Idea',      statuses: ['brainstorm', 'idea_review'] as TaskStatus[] },
  { label: 'Writing',   statuses: ['outline', 'writing_review'] as TaskStatus[] },
  { label: 'Scripting', statuses: ['generate_script', 'script_review'] as TaskStatus[] },
  { label: 'Video',     statuses: ['generate_clips', 'assemble_clips', 'video_review'] as TaskStatus[] },
  { label: 'Upload',    statuses: ['prepare_metadata', 'publish', 'closed'] as TaskStatus[] },
];

export default function SeriesDashboard() {
  const { currentWorkspace } = useWorkspace();
  const { currentProject } = useProject();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalTask, setModalTask] = useState<Task | null>(null);

  useEffect(() => {
    if (!currentWorkspace) return;
    setLoading(true);
    fetchTasksForWorkspace(currentWorkspace.id)
      .then(all => setTasks(currentProject ? all.filter(t => t.project_id === currentProject.id) : all))
      .finally(() => setLoading(false));
  }, [currentWorkspace, currentProject]);

  const handleTaskUpdated = (updated: Task) => {
    setTasks(prev => prev.map(t => t.id === updated.id ? updated : t));
    setModalTask(updated);
  };

  const total = tasks.length;
  const published = tasks.filter(t => t.status === 'publish' || t.status === 'closed').length;
  const inProgress = tasks.filter(t => !['brainstorm', 'publish', 'closed'].includes(t.status)).length;
  const ideas = tasks.filter(t => t.status === 'brainstorm').length;

  const recentTasks = [...tasks]
    .sort((a, b) => (a.title > b.title ? 1 : -1))
    .slice(0, 5);

  if (!currentWorkspace) return <main className={styles.container}><p className={styles.empty}>Select a workspace.</p></main>;
  if (!currentProject)   return <main className={styles.container}><p className={styles.empty}>Select a series.</p></main>;

  const seriesConcept = (currentProject.story_bible as Record<string, string> | null)?.series_concept;

  return (
    <main className={styles.container}>
      {/* ── Series header ── */}
      <div className={styles.seriesHeader}>
        <div className={styles.seriesName}>{currentProject.name}</div>
        {seriesConcept && <p className={styles.seriesConcept}>{seriesConcept}</p>}
      </div>

      {loading ? <p className={styles.empty}>Loading…</p> : (
        <>
          {/* ── Stats row ── */}
          <div className={styles.statsRow}>
            {[
              { label: 'Total Videos',  value: total },
              { label: 'Ideas',         value: ideas },
              { label: 'In Progress',   value: inProgress },
              { label: 'Published',     value: published },
            ].map(({ label, value }) => (
              <div key={label} className={styles.statCard}>
                <div className={styles.statValue}>{value}</div>
                <div className={styles.statLabel}>{label}</div>
              </div>
            ))}
          </div>

          {/* ── Pipeline breakdown ── */}
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Pipeline Status</div>
            <div className={styles.pipelineGroups}>
              {STAGE_GROUPS.map(({ label, statuses }) => {
                const count = statuses.reduce((n, s) => n + tasks.filter(t => t.status === s).length, 0);
                return (
                  <div key={label} className={styles.pipelineGroup}>
                    <div className={styles.pipelineGroupLabel}>{label}</div>
                    <div className={styles.pipelineGroupCount}>{count}</div>
                    <div className={styles.pipelineStatuses}>
                      {statuses.map(s => {
                        const n = tasks.filter(t => t.status === s).length;
                        return (
                          <div key={s} className={styles.pipelineStatus}>
                            <div
                              className={styles.pipelineDot}
                              style={{ background: n > 0 ? PHASE_MAP[s].color : undefined }}
                            />
                            <span className={styles.pipelineStatusLabel}>{STATUS_LABELS[s]}</span>
                            <span className={styles.pipelineStatusCount}>{n}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── Video progress bar ── */}
          {total > 0 && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Series Progress</div>
              <div className={styles.progressBar}>
                {TASK_STATUSES.filter(s => tasks.some(t => t.status === s)).map(s => {
                  const count = tasks.filter(t => t.status === s).length;
                  return (
                    <div
                      key={s}
                      className={styles.progressSegment}
                      style={{ width: `${(count / total) * 100}%`, background: PHASE_MAP[s].color }}
                      title={`${STATUS_LABELS[s]}: ${count}`}
                    />
                  );
                })}
              </div>
              <div className={styles.progressLegend}>
                {TASK_STATUSES.filter(s => tasks.some(t => t.status === s)).map(s => (
                  <div key={s} className={styles.legendItem}>
                    <div className={styles.legendDot} style={{ background: PHASE_MAP[s].color }} />
                    <span>{STATUS_LABELS[s]} ({tasks.filter(t => t.status === s).length})</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Recent videos ── */}
          {recentTasks.length > 0 && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Videos</div>
              <div className={styles.videoList}>
                {recentTasks.map(task => (
                  <div key={task.id} className={styles.videoRow} onClick={() => setModalTask(task)}>
                    <div className={styles.videoInfo}>
                      <div className={styles.videoTitle}>{task.title}</div>
                      {task.concept_brief && <div className={styles.videoBrief}>{task.concept_brief.slice(0, 100)}{task.concept_brief.length > 100 ? '…' : ''}</div>}
                    </div>
                    <span
                      className={styles.videoStatus}
                      style={{ color: PHASE_MAP[task.status].color }}
                    >
                      {STATUS_LABELS[task.status]}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {total === 0 && (
            <p className={styles.empty}>No videos in this series yet. Use the Kanban view to add one.</p>
          )}
        </>
      )}

      {modalTask && (
        <VideoModal
          task={modalTask}
          onClose={() => setModalTask(null)}
          onUpdated={handleTaskUpdated}
          onDeleted={(id) => { setTasks(prev => prev.filter(t => t.id !== id)); setModalTask(null); }}
        />
      )}
    </main>
  );
}
