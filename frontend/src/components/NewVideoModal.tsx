import { useState } from 'react';
import { createTask } from '../api/tasks';
import type { Project } from '../api/projects';
import styles from './NewVideoModal.module.css';

interface Props {
  projects: Project[];
  defaultProjectId?: string;
  onCreated: () => void;
  onCancel: () => void;
}

export function NewVideoModal({ projects, defaultProjectId, onCreated, onCancel }: Props) {
  const [projectId, setProjectId] = useState(defaultProjectId ?? projects[0]?.id ?? '');
  const [title, setTitle] = useState('');
  const [brief, setBrief] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !title.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await createTask(projectId, title.trim(), brief.trim() || undefined);
      onCreated();
    } catch {
      setError('Failed to create video');
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.title}>New Video</h2>
        <form onSubmit={handleSubmit} className={styles.form}>
          <label className={styles.label}>
            Series
            <select
              className={styles.select}
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              required
            >
              {projects.length === 0 && (
                <option value="" disabled>No series yet — create one first</option>
              )}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </label>

          <label className={styles.label}>
            Video title
            <input
              className={styles.input}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. S01E01 – The Haunting of Harrow House"
              autoFocus
              required
            />
          </label>

          <label className={styles.label}>
            Video brief
            <span className={styles.hint}>Optional now — required before AI starts writing</span>
            <textarea
              className={styles.textarea}
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              rows={4}
              placeholder="Describe the hook, key scenes, tone, and what makes this video compelling…"
            />
          </label>

          {error && <p className={styles.error}>{error}</p>}

          <div className={styles.actions}>
            <button type="button" className={styles.cancelBtn} onClick={onCancel} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className={styles.submitBtn} disabled={submitting || !title.trim() || !projectId}>
              {submitting ? 'Creating…' : 'Create Video'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
