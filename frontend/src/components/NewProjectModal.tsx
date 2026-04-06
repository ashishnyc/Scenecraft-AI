import { useState } from 'react';
import type { ProjectCreate, ProjectType } from '../api/projects';
import { Select } from './Select';
import type { SelectOption } from './Select';
import styles from './NewProjectModal.module.css';

const PROJECT_TYPE_OPTIONS: SelectOption<ProjectType>[] = [
  { value: 'serialised', label: 'Serialised' },
  { value: 'anthology', label: 'Anthology' },
];

interface Props {
  onConfirm: (data: ProjectCreate) => Promise<void>;
  onCancel: () => void;
}

export function NewProjectModal({ onConfirm, onCancel }: Props) {
  const [name, setName] = useState('');
  const [type, setType] = useState<ProjectType>('serialised');
  const [episodeCount, setEpisodeCount] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm({
        name: name.trim(),
        type,
        episode_count: episodeCount ? Number(episodeCount) : undefined,
      });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to create project';
      setError(msg);
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.title}>New Project</h2>
        <form onSubmit={handleSubmit} className={styles.form}>
          <label className={styles.label}>
            Name
            <input
              className={styles.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Midnight Manor"
              autoFocus
              required
            />
          </label>

          <label className={styles.label}>
            Type
            <Select
              value={type}
              options={PROJECT_TYPE_OPTIONS}
              onChange={setType}
            />
          </label>

          <label className={styles.label}>
            Episode count (optional)
            <input
              className={styles.input}
              type="number"
              min="1"
              value={episodeCount}
              onChange={(e) => setEpisodeCount(e.target.value)}
              placeholder="e.g. 10"
            />
          </label>

          {error && <p className={styles.error}>{error}</p>}

          <div className={styles.actions}>
            <button type="button" className={styles.cancelBtn} onClick={onCancel} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className={styles.submitBtn} disabled={submitting || !name.trim()}>
              {submitting ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
