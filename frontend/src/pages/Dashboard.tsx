import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWorkspace } from '../context/WorkspaceContext';
import { useProject } from '../context/ProjectContext';
import type { Project } from '../api/projects';
import { fetchProjects } from '../api/projects';
import { getWorkspaceAnalyticsSummary, type WorkspaceAnalyticsSummary } from '../api/video';
import type { Task } from '../api/tasks';
import { apiClient } from '../api/client';
import styles from './Dashboard.module.css';

const STATUS_ORDER = [
  'brainstorm', 'idea_review',
  'outline', 'writing_review',
  'generate_script', 'script_review',
  'generate_clips', 'assemble_clips', 'video_review',
  'prepare_metadata', 'publish', 'closed',
];

const PHASE_COLORS: Record<string, string> = {
  brainstorm: '#6366f1',      idea_review: '#6366f1',
  outline: '#8b5cf6',         writing_review: '#8b5cf6',
  generate_script: '#f59e0b', script_review: '#f59e0b',
  generate_clips: '#10b981',  assemble_clips: '#10b981', video_review: '#10b981',
  prepare_metadata: '#3b82f6',publish: '#3b82f6', closed: '#3b82f6',
};

function StatusBar({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (total === 0) return <div className={styles.statusBarEmpty}>No videos yet</div>;
  return (
    <div className={styles.statusBar} title={`${total} videos total`}>
      {STATUS_ORDER.filter((s) => counts[s] > 0).map((s) => (
        <div
          key={s}
          className={styles.statusSegment}
          style={{
            width: `${(counts[s] / total) * 100}%`,
            background: PHASE_COLORS[s],
          }}
          title={`${s}: ${counts[s]}`}
        />
      ))}
    </div>
  );
}

export default function Dashboard() {
  const { currentWorkspace } = useWorkspace();
  const { selectProject } = useProject();
  const navigate = useNavigate();

  const [series, setSeries] = useState<Project[]>([]);
  const [tasksBySeries, setTasksBySeries] = useState<Record<string, Task[]>>({});
  const [analytics, setAnalytics] = useState<WorkspaceAnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!currentWorkspace) return;
    setLoading(true);

    const loadAll = async () => {
      const [projects, analyticsSummary] = await Promise.all([
        fetchProjects(currentWorkspace.id),
        getWorkspaceAnalyticsSummary(currentWorkspace.id).catch(() => null),
      ]);
      setSeries(projects);
      setAnalytics(analyticsSummary);

      // Load task counts per series
      const taskMap: Record<string, Task[]> = {};
      await Promise.all(
        projects.map(async (p) => {
          try {
            const res = await apiClient.get<Task[]>(`/projects/${p.id}/tasks`);
            taskMap[p.id] = res.data;
          } catch {
            taskMap[p.id] = [];
          }
        })
      );
      setTasksBySeries(taskMap);
    };

    loadAll().finally(() => setLoading(false));
  }, [currentWorkspace]);

  const handleOpenSeries = (project: Project) => {
    selectProject(project);
    navigate('/projects');
  };

  if (!currentWorkspace) {
    return (
      <main className={styles.container}>
        <p className={styles.empty}>Select or create a workspace to get started.</p>
      </main>
    );
  }

  const totalVideos = Object.values(tasksBySeries).reduce((n, tasks) => n + tasks.length, 0);
  const publishedVideos = Object.values(tasksBySeries)
    .flat()
    .filter((t) => t.status === 'publish' || t.status === 'closed').length;

  return (
    <main className={styles.container}>
      {/* ── Channel header ── */}
      <div className={styles.channelHeader}>
        <div className={styles.channelAvatar}>
          {currentWorkspace.name.slice(0, 2).toUpperCase()}
        </div>
        <div className={styles.channelMeta}>
          <h1 className={styles.channelName}>{currentWorkspace.name}</h1>
          <span className={styles.channelHandle}>
            @{currentWorkspace.name.toLowerCase().replace(/\s+/g, '')}
          </span>
        </div>
      </div>

      {/* ── Stats row ── */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{series.length}</span>
          <span className={styles.statLabel}>Series</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{totalVideos}</span>
          <span className={styles.statLabel}>Total videos</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{publishedVideos}</span>
          <span className={styles.statLabel}>Published</span>
        </div>
        {analytics && (
          <>
            <div className={styles.statCard}>
              <span className={styles.statValue}>
                {analytics.total_views >= 1000
                  ? `${(analytics.total_views / 1000).toFixed(1)}k`
                  : analytics.total_views}
              </span>
              <span className={styles.statLabel}>Total views</span>
            </div>
            <div className={styles.statCard}>
              <span className={styles.statValue}>{analytics.total_likes}</span>
              <span className={styles.statLabel}>Total likes</span>
            </div>
          </>
        )}
      </div>

      {/* ── Series gallery ── */}
      <div className={styles.sectionHeader}>
        <h2 className={styles.sectionTitle}>Series</h2>
      </div>

      {loading ? (
        <p className={styles.empty}>Loading…</p>
      ) : series.length === 0 ? (
        <p className={styles.empty}>No series yet. Create one from the sidebar.</p>
      ) : (
        <div className={styles.seriesGrid}>
          {series.map((project) => {
            const tasks = tasksBySeries[project.id] ?? [];
            const counts = tasks.reduce<Record<string, number>>((acc, t) => {
              acc[t.status] = (acc[t.status] ?? 0) + 1;
              return acc;
            }, {});
            const bible = project.story_bible as Record<string, unknown> | null;
            const concept = bible?.series_concept as string | undefined;
            const isOneOffs = project.name === 'One-Offs';

            return (
              <div
                key={project.id}
                className={`${styles.seriesCard} ${isOneOffs ? styles.seriesCardOneOffs : ''}`}
                onClick={() => handleOpenSeries(project)}
              >
                <div className={styles.seriesCardTop}>
                  <div className={styles.seriesCardTitle}>{project.name}</div>
                  <div className={styles.seriesCardBadges}>
                    <span className={styles.typeBadge}>{project.type}</span>
                    <span className={`${styles.statusBadge} ${styles[`status_${project.status}`]}`}>
                      {project.status}
                    </span>
                  </div>
                </div>

                {concept && (
                  <p className={styles.seriesConcept}>{concept}</p>
                )}

                <StatusBar counts={counts} />

                <div className={styles.seriesCardFooter}>
                  <span className={styles.videoCount}>{tasks.length} video{tasks.length !== 1 ? 's' : ''}</span>
                  <span className={styles.openLink}>Open series →</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
