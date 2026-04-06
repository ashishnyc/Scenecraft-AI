import { useState } from 'react';
import type { ProjectCreate, ProjectType, VideoConceptSuggestion } from '../api/projects';
import { suggestProject } from '../api/projects';
import { Select } from './Select';
import type { SelectOption } from './Select';
import { useWorkspace } from '../context/WorkspaceContext';
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
  const { currentWorkspace } = useWorkspace();

  // AI brief
  const [brief, setBrief] = useState('');
  const [suggesting, setSuggesting] = useState(false);
  const [concepts, setConcepts] = useState<VideoConceptSuggestion[]>([]);
  const [seriesConcept, setSeriesConcept] = useState('');
  const [suggestError, setSuggestError] = useState<string | null>(null);

  // Form fields
  const [name, setName] = useState('');
  const [type, setType] = useState<ProjectType>('serialised');
  const [episodeCount, setEpisodeCount] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSuggest = async () => {
    if (!brief.trim() || !currentWorkspace) return;
    setSuggesting(true);
    setSuggestError(null);
    setConcepts([]);
    setSeriesConcept('');
    try {
      const result = await suggestProject(currentWorkspace.id, brief);
      setName(result.name);
      setSeriesConcept(result.series_concept);
      setConcepts(result.video_concepts);
    } catch {
      setSuggestError('Could not reach the LLM. Check Ollama is running.');
    } finally {
      setSuggesting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const storyBible = seriesConcept
        ? { series_concept: seriesConcept, base_video_concepts: concepts }
        : undefined;
      await onConfirm({
        name: name.trim(),
        type,
        episode_count: episodeCount ? Number(episodeCount) : undefined,
        story_bible: storyBible,
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

          {/* ── AI Brief ── */}
          <div className={styles.briefSection}>
            <label className={styles.label}>
              Describe your channel concept
              <textarea
                className={styles.briefInput}
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
                placeholder="e.g. A horror channel that explores real haunted locations across the UK, mixing investigation footage with dramatic re-enactments…"
                rows={3}
              />
            </label>
            <button
              type="button"
              className={styles.suggestBtn}
              onClick={handleSuggest}
              disabled={suggesting || !brief.trim()}
            >
              {suggesting ? 'Thinking…' : '✦ AI Suggest'}
            </button>
            {suggestError && <p className={styles.error}>{suggestError}</p>}
          </div>

          {/* ── AI Suggestions preview ── */}
          {concepts.length > 0 && (
            <div className={styles.suggestionsBox}>
              {seriesConcept && (
                <p className={styles.seriesConcept}>{seriesConcept}</p>
              )}
              <p className={styles.suggestionsLabel}>Base video concepts</p>
              <ul className={styles.conceptList}>
                {concepts.map((c, i) => (
                  <li key={i} className={styles.conceptItem}>
                    <span className={styles.conceptTitle}>{c.title}</span>
                    <span className={styles.conceptDesc}>{c.concept}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className={styles.divider} />

          {/* ── Form fields ── */}
          <label className={styles.label}>
            Project name
            <input
              className={styles.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Midnight Manor"
              autoFocus={!brief}
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
