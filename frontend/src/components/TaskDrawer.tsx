import { useState, useEffect } from 'react';
import type { Task } from '../api/tasks';
import { updateTask, STATUS_LABELS } from '../api/tasks';
import styles from './TaskDrawer.module.css';

interface Props {
  task: Task;
  onClose: () => void;
  onUpdated: (task: Task) => void;
}

export function TaskDrawer({ task, onClose, onUpdated }: Props) {
  const [conceptBrief, setConceptBrief] = useState(task.concept_brief ?? '');
  const [creatorNotes, setCreatorNotes] = useState(task.creator_notes ?? '');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Reset fields when task changes
  useEffect(() => {
    setConceptBrief(task.concept_brief ?? '');
    setCreatorNotes(task.creator_notes ?? '');
    setSaved(false);
  }, [task.id]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await updateTask(task.id, {
        concept_brief: conceptBrief.trim() || undefined,
        creator_notes: creatorNotes.trim() || undefined,
      });
      onUpdated(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} />
      <aside className={styles.drawer}>
        <div className={styles.header}>
          <div className={styles.headerMeta}>
            <span className={`${styles.statusBadge} ${styles[`badge_${task.status}`]}`}>
              {STATUS_LABELS[task.status]}
            </span>
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>

        <h2 className={styles.title}>{task.title}</h2>

        <form onSubmit={handleSave} className={styles.form}>
          <label className={styles.label}>
            Concept brief
            <span className={styles.labelHint}>Required to approve</span>
            <textarea
              className={styles.textarea}
              value={conceptBrief}
              onChange={(e) => setConceptBrief(e.target.value)}
              rows={5}
              placeholder="Describe the episode concept, hook, and what makes it compelling…"
            />
          </label>

          <label className={styles.label}>
            Creator notes
            <span className={styles.labelHint}>Optional — style, tone, special instructions</span>
            <textarea
              className={styles.textarea}
              value={creatorNotes}
              onChange={(e) => setCreatorNotes(e.target.value)}
              rows={4}
              placeholder="e.g. Keep the tone dark but grounded, emphasise witness testimonies…"
            />
          </label>

          <button type="submit" className={styles.saveBtn} disabled={saving}>
            {saving ? 'Saving…' : saved ? '✓ Saved' : 'Save'}
          </button>
        </form>
      </aside>
    </>
  );
}
