import { useState } from 'react';
import type { CharacterCreate, RoleType } from '../api/characters';
import styles from './NewProjectModal.module.css'; // reuse same modal styles

const ROLE_OPTIONS: { value: RoleType; label: string }[] = [
  { value: 'lead', label: 'Lead' },
  { value: 'supporting', label: 'Supporting' },
  { value: 'recurring', label: 'Recurring' },
  { value: 'narrator', label: 'Narrator' },
  { value: 'villain', label: 'Villain' },
];

interface Props {
  onConfirm: (data: CharacterCreate) => Promise<void>;
  onCancel: () => void;
}

export function CreateCharacterModal({ onConfirm, onCancel }: Props) {
  const [name, setName] = useState('');
  const [roleType, setRoleType] = useState<RoleType>('lead');
  const [age, setAge] = useState('');
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
        role_type: roleType,
        age: age ? Number(age) : undefined,
      });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to create character';
      setError(msg);
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.title}>Create Character</h2>
        <form onSubmit={handleSubmit} className={styles.form}>
          <label className={styles.label}>
            Name
            <input
              className={styles.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Dr. Elena Voss"
              autoFocus
              required
            />
          </label>

          <label className={styles.label}>
            Role type
            <select className={styles.select} value={roleType} onChange={(e) => setRoleType(e.target.value as RoleType)}>
              {ROLE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>

          <label className={styles.label}>
            Age (optional)
            <input
              className={styles.input}
              type="number"
              min="0"
              value={age}
              onChange={(e) => setAge(e.target.value)}
              placeholder="—"
            />
          </label>

          <label className={styles.label}>
            Image upload
            <input className={styles.input} type="file" accept="image/*" disabled title="Image upload coming soon" />
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Coming soon</span>
          </label>

          {error && <p style={{ fontSize: 'var(--text-sm)', color: '#fca5a5' }}>{error}</p>}

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
