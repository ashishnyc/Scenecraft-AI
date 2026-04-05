/**
 * PublishWorkflow — SA-39 (Thumbnail Selector) + SA-40 (Title/Description/Tags Editor)
 *
 * Displayed for tasks in `scheduled` status. Lets the creator:
 *   1. Pick one of 5 AI-generated thumbnails (or upload custom)
 *   2. Review/edit the LLM-pre-filled YouTube metadata
 *   3. Save and queue for publishing
 */
import { useState, useEffect, useRef, KeyboardEvent } from 'react';
import { useWorkspace } from '../context/WorkspaceContext';
import { fetchTasksForWorkspace, type Task } from '../api/tasks';
import {
  generateThumbnails,
  selectThumbnail,
  uploadCustomThumbnail,
  generateMetadata,
  saveMetadata,
  type ThumbnailOption,
  type YoutubeMetadata,
} from '../api/video';
import styles from './PublishWorkflow.module.css';

export default function PublishWorkflow() {
  const { selectedWorkspace } = useWorkspace();

  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  // SA-39: Thumbnails
  const [thumbnails, setThumbnails] = useState<ThumbnailOption[]>([]);
  const [selectedThumbIdx, setSelectedThumbIdx] = useState<number | null>(null);
  const [thumbLoading, setThumbLoading] = useState(false);
  const [thumbSaved, setThumbSaved] = useState(false);

  // SA-40: Metadata
  const [metadata, setMetadata] = useState<YoutubeMetadata>({
    title: '', description: '', tags: [], scheduled_at: null,
  });
  const [tagInput, setTagInput] = useState('');
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaSaved, setMetaSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load tasks in scheduled status
  useEffect(() => {
    if (!selectedWorkspace) return;
    fetchTasksForWorkspace(selectedWorkspace.id)
      .then((all) => setTasks(all.filter((t) => t.status === 'scheduled')))
      .catch(() => setTasks([]));
  }, [selectedWorkspace]);

  // Reset state when task changes
  useEffect(() => {
    setThumbnails([]);
    setSelectedThumbIdx(null);
    setThumbSaved(false);
    setMetadata({ title: '', description: '', tags: [], scheduled_at: null });
    setMetaSaved(false);
    setError(null);
  }, [selectedTaskId]);

  // ── Thumbnails ──────────────────────────────────────────────────────────────

  async function handleGenerateThumbnails() {
    if (!selectedTaskId) return;
    setThumbLoading(true);
    setError(null);
    try {
      const opts = await generateThumbnails(selectedTaskId);
      setThumbnails(opts);
    } catch {
      setError('Thumbnail generation failed');
    } finally {
      setThumbLoading(false);
    }
  }

  async function handleSelectThumbnail(idx: number) {
    if (!selectedTaskId) return;
    setSelectedThumbIdx(idx);
    try {
      await selectThumbnail(selectedTaskId, idx);
      setThumbSaved(true);
    } catch {
      setError('Failed to save thumbnail selection');
    }
  }

  async function handleCustomUpload(e: React.ChangeEvent<HTMLInputElement>) {
    if (!selectedTaskId || !e.target.files?.length) return;
    const file = e.target.files[0];
    const reader = new FileReader();
    reader.onload = async () => {
      const b64 = (reader.result as string).split(',')[1];
      try {
        await uploadCustomThumbnail(selectedTaskId, b64);
        setSelectedThumbIdx(-1); // -1 = custom
        setThumbSaved(true);
      } catch {
        setError('Custom thumbnail upload failed');
      }
    };
    reader.readAsDataURL(file);
  }

  // ── Metadata ────────────────────────────────────────────────────────────────

  async function handlePrefillMetadata() {
    if (!selectedTaskId) return;
    setMetaLoading(true);
    setError(null);
    try {
      const data = await generateMetadata(selectedTaskId);
      setMetadata(data);
    } catch {
      setError('Metadata generation failed');
    } finally {
      setMetaLoading(false);
    }
  }

  async function handleSaveMetadata() {
    if (!selectedTaskId) return;
    setMetaLoading(true);
    setError(null);
    try {
      await saveMetadata(selectedTaskId, metadata);
      setMetaSaved(true);
    } catch {
      setError('Failed to save metadata');
    } finally {
      setMetaLoading(false);
    }
  }

  function handleTagKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if ((e.key === 'Enter' || e.key === ',') && tagInput.trim()) {
      e.preventDefault();
      const newTag = tagInput.trim().replace(/,+$/, '');
      if (newTag && !metadata.tags.includes(newTag)) {
        setMetadata((m) => ({ ...m, tags: [...m.tags, newTag] }));
      }
      setTagInput('');
    } else if (e.key === 'Backspace' && !tagInput && metadata.tags.length > 0) {
      setMetadata((m) => ({ ...m, tags: m.tags.slice(0, -1) }));
    }
  }

  function removeTag(tag: string) {
    setMetadata((m) => ({ ...m, tags: m.tags.filter((t) => t !== tag) }));
  }

  const selectedTask = tasks.find((t) => t.id === selectedTaskId);

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <h1>Publish Workflow</h1>
        <select
          value={selectedTaskId ?? ''}
          onChange={(e) => setSelectedTaskId(e.target.value || null)}
          style={{
            background: '#111117', color: '#e0e0e0', border: '1px solid #2a2a30',
            borderRadius: 6, padding: '6px 10px', fontSize: 13,
          }}
        >
          <option value="">Select task…</option>
          {tasks.map((t) => (
            <option key={t.id} value={t.id}>{t.title}</option>
          ))}
        </select>
      </div>

      {!selectedTaskId ? (
        <div className={styles.loading}>Select a scheduled task to begin.</div>
      ) : (
        <div className={styles.body}>
          {/* ── SA-39: Thumbnail Panel ── */}
          <div className={styles.thumbnailPanel}>
            <h2>Thumbnail</h2>

            <button
              className={styles.generateBtn}
              onClick={handleGenerateThumbnails}
              disabled={thumbLoading}
            >
              {thumbLoading ? 'Generating…' : 'Generate AI Thumbnails'}
            </button>

            {thumbnails.length > 0 && (
              <div className={styles.thumbnailGrid}>
                {thumbnails.map((opt, i) => (
                  <div
                    key={opt.index}
                    className={`${styles.thumbCard} ${selectedThumbIdx === i ? styles.selected : ''}`}
                    onClick={() => handleSelectThumbnail(i)}
                  >
                    <img src={opt.signed_url} alt={`Thumbnail option ${i + 1}`} />
                    <div className={styles.thumbCaption}>Option {i + 1}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Custom upload */}
            <div className={styles.customUpload}>
              <label>Or upload your own</label>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className={styles.uploadInput}
                onChange={handleCustomUpload}
              />
              <button
                className={styles.uploadBtn}
                onClick={() => fileInputRef.current?.click()}
              >
                Click to upload custom thumbnail
              </button>
            </div>

            {thumbSaved && (
              <div className={styles.successMsg} style={{ marginTop: 8 }}>
                Thumbnail saved.
              </div>
            )}
          </div>

          {/* ── SA-40: Metadata Panel ── */}
          <div className={styles.metadataPanel}>
            <h2>YouTube Metadata</h2>

            <div className={styles.field}>
              <label>Title</label>
              <input
                className={styles.input}
                value={metadata.title}
                onChange={(e) => setMetadata((m) => ({ ...m, title: e.target.value }))}
                maxLength={100}
                placeholder="Video title…"
              />
            </div>

            <div className={styles.field}>
              <label>Description</label>
              <textarea
                className={styles.textarea}
                value={metadata.description}
                onChange={(e) => setMetadata((m) => ({ ...m, description: e.target.value }))}
                placeholder="YouTube description…"
              />
            </div>

            <div className={styles.field}>
              <label>Tags (press Enter or comma to add)</label>
              <div className={styles.tagsContainer} onClick={() => document.getElementById('tag-input')?.focus()}>
                {metadata.tags.map((tag) => (
                  <span key={tag} className={styles.tag}>
                    {tag}
                    <button className={styles.tagRemove} onClick={() => removeTag(tag)}>×</button>
                  </span>
                ))}
                <input
                  id="tag-input"
                  className={styles.tagInput}
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={handleTagKeyDown}
                  placeholder={metadata.tags.length === 0 ? 'Add tags…' : ''}
                />
              </div>
            </div>

            <div className={styles.field}>
              <label>Scheduled publish date (optional)</label>
              <input
                className={styles.input}
                type="datetime-local"
                value={metadata.scheduled_at?.replace('Z', '') ?? ''}
                onChange={(e) =>
                  setMetadata((m) => ({
                    ...m,
                    scheduled_at: e.target.value ? `${e.target.value}:00Z` : null,
                  }))
                }
              />
            </div>

            {error && <div className={styles.errorMsg}>{error}</div>}
            {metaSaved && <div className={styles.successMsg}>Metadata saved.</div>}

            <div className={styles.actionRow}>
              <button
                className={styles.prefillBtn}
                onClick={handlePrefillMetadata}
                disabled={metaLoading}
              >
                {metaLoading ? 'Generating…' : 'AI Pre-fill'}
              </button>
              <button
                className={styles.saveBtn}
                onClick={handleSaveMetadata}
                disabled={metaLoading || !metadata.title}
              >
                Save Metadata
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
