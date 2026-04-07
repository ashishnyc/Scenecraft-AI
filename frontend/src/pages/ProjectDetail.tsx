import { useState, useEffect } from 'react';
import { useProject } from '../context/ProjectContext';
import type { ProjectUpdate, VideoConceptSuggestion } from '../api/projects';
import { updateProject, generateMoreConcepts, deleteProject } from '../api/projects';
import type { Task } from '../api/tasks';
import { fetchTasksForWorkspace, createTask, STATUS_LABELS } from '../api/tasks';
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
  const { currentProject, refreshProjects, selectProject } = useProject();
  const { currentWorkspace } = useWorkspace();

  const [name, setName] = useState('');
  const [status, setStatus] = useState<ProjectUpdate['status']>('active');
  const [episodeCount, setEpisodeCount] = useState('');
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const [episodes, setEpisodes] = useState<Task[]>([]);
  const [epLoading, setEpLoading] = useState(false);

  // Episode concept cards
  const [concepts, setConcepts] = useState<VideoConceptSuggestion[]>([]);
  const [seriesConcept, setSeriesConcept] = useState('');
  const [generating, setGenerating] = useState(false);
  const [creatingFrom, setCreatingFrom] = useState<number | null>(null); // index of concept being created

  // Sync form when project changes
  useEffect(() => {
    if (!currentProject) return;
    setName(currentProject.name);
    setStatus(currentProject.status);
    setEpisodeCount(currentProject.episode_count != null ? String(currentProject.episode_count) : '');

    const bible = currentProject.story_bible as Record<string, unknown> | null;
    setSeriesConcept((bible?.series_concept as string) ?? '');
    setConcepts((bible?.base_video_concepts as VideoConceptSuggestion[]) ?? []);
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
      await updateProject(currentProject.id, {
        name: name.trim(),
        status,
        episode_count: episodeCount ? Number(episodeCount) : undefined,
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

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteProject(currentProject.id);
      selectProject(null);
      await refreshProjects();
    } catch {
      setToast({ message: 'Failed to delete project', type: 'error' });
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const handleGenerateMore = async () => {
    setGenerating(true);
    try {
      const newConcepts = await generateMoreConcepts(currentProject.id);
      const merged = [...concepts, ...newConcepts];
      setConcepts(merged);
      // Persist the updated concepts into story_bible
      const bible = (currentProject.story_bible as Record<string, unknown> | null) ?? {};
      await updateProject(currentProject.id, {
        story_bible: { ...bible, base_video_concepts: merged },
      });
      await refreshProjects();
    } catch {
      setToast({ message: 'Could not generate ideas. Check Ollama is running.', type: 'error' });
    } finally {
      setGenerating(false);
    }
  };

  const handleCreateEpisode = async (concept: VideoConceptSuggestion, idx: number) => {
    setCreatingFrom(idx);
    try {
      await createTask(currentProject.id, concept.title, concept.concept);
      // Reload episodes
      if (currentWorkspace) {
        const all = await fetchTasksForWorkspace(currentWorkspace.id);
        setEpisodes(all.filter((t) => t.project_id === currentProject.id));
      }
      setToast({ message: `Episode "${concept.title}" created`, type: 'success' });
    } catch {
      setToast({ message: 'Failed to create episode', type: 'error' });
    } finally {
      setCreatingFrom(null);
    }
  };

  return (
    <main className={styles.container}>
      <h1 className={styles.title}>{currentProject.name}</h1>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Series settings</h2>
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
            Video count
            <input className={styles.input} type="number" min="1" value={episodeCount}
              onChange={(e) => setEpisodeCount(e.target.value)} placeholder="—" />
          </label>

          <div className={styles.formActions}>
            <button type="submit" className={styles.saveBtn} disabled={saving}>
              {saving ? 'Saving…' : 'Save changes'}
            </button>
            {!confirmDelete ? (
              <button type="button" className={styles.deleteBtn} onClick={() => setConfirmDelete(true)}>
                Delete project
              </button>
            ) : (
              <div className={styles.confirmRow}>
                <span className={styles.confirmText}>Delete "{currentProject.name}"?</span>
                <button type="button" className={styles.confirmDeleteBtn} onClick={handleDelete} disabled={deleting}>
                  {deleting ? 'Deleting…' : 'Yes, delete'}
                </button>
                <button type="button" className={styles.cancelDeleteBtn} onClick={() => setConfirmDelete(false)}>
                  Cancel
                </button>
              </div>
            )}
          </div>
        </form>
      </section>

      {/* ── Episode Ideas ── */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Video ideas</h2>
          <button
            type="button"
            className={styles.generateBtn}
            onClick={handleGenerateMore}
            disabled={generating}
          >
            {generating ? 'Generating…' : '✦ Generate more ideas'}
          </button>
        </div>

        {seriesConcept && (
          <p className={styles.seriesConcept}>{seriesConcept}</p>
        )}

        {concepts.length === 0 ? (
          <p className={styles.empty}>
            No episode ideas yet. Use the AI brief when creating a project, or click "Generate more ideas".
          </p>
        ) : (
          <div className={styles.conceptGrid}>
            {concepts.map((c, i) => (
              <div key={i} className={styles.conceptCard}>
                <div className={styles.conceptCardBody}>
                  <span className={styles.conceptTitle}>{c.title}</span>
                  <span className={styles.conceptDesc}>{c.concept}</span>
                </div>
                <button
                  type="button"
                  className={styles.createEpBtn}
                  onClick={() => handleCreateEpisode(c, i)}
                  disabled={creatingFrom === i}
                >
                  {creatingFrom === i ? 'Creating…' : '→ Create Episode'}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Videos</h2>
        {epLoading ? (
          <p className={styles.empty}>Loading…</p>
        ) : episodes.length === 0 ? (
          <p className={styles.empty}>No videos yet. Create one from an idea above.</p>
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
