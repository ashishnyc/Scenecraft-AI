import { useState, useEffect } from 'react';
import { useProject } from '../context/ProjectContext';
import type { ProjectUpdate } from '../api/projects';
import { updateProject } from '../api/projects';
import type { Task } from '../api/tasks';
import { fetchTasksForWorkspace, STATUS_LABELS } from '../api/tasks';
import { useWorkspace } from '../context/WorkspaceContext';
import { Toast } from '../components/Toast';
import { Select } from '../components/Select';
import type { SelectOption } from '../components/Select';
import styles from './ProjectDetail.module.css';

const PROJECT_STATUS_OPTIONS: SelectOption<NonNullable<ProjectUpdate['status']>>[] = [
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'completed', label: 'Completed' },
];

export default function ProjectDetail() {
  const { currentProject, refreshProjects } = useProject();
  const { currentWorkspace } = useWorkspace();

  const [name, setName] = useState('');
  const [storyBible, setStoryBible] = useState('');
  const [status, setStatus] = useState<ProjectUpdate['status']>('active');
  const [episodeCount, setEpisodeCount] = useState('');
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const [episodes, setEpisodes] = useState<Task[]>([]);
  const [epLoading, setEpLoading] = useState(false);

  // Sync form when project changes
  useEffect(() => {
    if (!currentProject) return;
    setName(currentProject.name);
    setStoryBible(currentProject.story_bible ? JSON.stringify(currentProject.story_bible, null, 2) : '');
    setStatus(currentProject.status);
    setEpisodeCount(currentProject.episode_count != null ? String(currentProject.episode_count) : '');
  }, [currentProject]);

  // Load episodes for this project
  useEffect(() => {
    if (!currentWorkspace || !currentProject) return;
    setEpLoading(true);
    fetchTasksForWorkspace(currentWorkspace.id)
      .then((all) => setEpisodes(all.filter((t) => t.project_id === currentProject.id)))
      .finally(() => setEpLoading(false));
  }, [currentWorkspace, currentProject]);

  if (!currentProject) {
    return (
      <main className={styles.container}>
        <p className={styles.empty}>Select a project from the sidebar.</p>
      </main>
    );
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      let parsedBible: Record<string, unknown> | undefined;
      if (storyBible.trim()) {
        parsedBible = JSON.parse(storyBible);
      }
      await updateProject(currentProject.id, {
        name: name.trim(),
        status,
        episode_count: episodeCount ? Number(episodeCount) : undefined,
        story_bible: parsedBible,
      });
      await refreshProjects();
      setToast({ message: 'Project saved', type: 'success' });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to save';
      setToast({ message: msg, type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className={styles.container}>
      <h1 className={styles.title}>{currentProject.name}</h1>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Project settings</h2>
        <form onSubmit={handleSave} className={styles.form}>
          <label className={styles.label}>
            Name
            <input className={styles.input} value={name} onChange={(e) => setName(e.target.value)} required />
          </label>

          <label className={styles.label}>
            Status
            <Select
              value={status as NonNullable<ProjectUpdate['status']>}
              options={PROJECT_STATUS_OPTIONS}
              onChange={setStatus}
            />
          </label>

          <label className={styles.label}>
            Episode count
            <input className={styles.input} type="number" min="1" value={episodeCount}
              onChange={(e) => setEpisodeCount(e.target.value)} placeholder="—" />
          </label>

          <label className={styles.label}>
            Story bible (JSON)
            <textarea className={styles.textarea} value={storyBible}
              onChange={(e) => setStoryBible(e.target.value)} rows={6}
              placeholder='{"characters": {}, "plot_threads": [], "timeline": []}' />
          </label>

          <button type="submit" className={styles.saveBtn} disabled={saving}>
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </form>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Episodes</h2>
        {epLoading ? (
          <p className={styles.empty}>Loading…</p>
        ) : episodes.length === 0 ? (
          <p className={styles.empty}>No episodes yet. Create tasks from the Tasks board.</p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>#</th>
                <th className={styles.th}>Title</th>
                <th className={styles.th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {episodes.map((ep, i) => (
                <tr key={ep.id} className={styles.tr}>
                  <td className={styles.td}>{i + 1}</td>
                  <td className={styles.td}>{ep.title}</td>
                  <td className={styles.td}>
                    <span className={styles.badge}>{STATUS_LABELS[ep.status]}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
    </main>
  );
}
