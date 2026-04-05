import { useEffect, useState, useCallback } from 'react';
import type { Pitch } from '../api/pitches';
import { fetchPitches, approvePitch, rejectPitch, updatePitchNotes } from '../api/pitches';
import { useWorkspace } from '../context/WorkspaceContext';
import { Toast } from './Toast';
import styles from './PitchInbox.module.css';

type ToastState = { message: string; type: 'success' | 'error' } | null;

interface PitchCardProps {
  pitch: Pitch;
  workspaceId: string;
  onApproved: (pitchId: string) => void;
  onRejected: (pitchId: string) => void;
  onToast: (msg: string, type: 'success' | 'error') => void;
}

function PitchCard({ pitch, workspaceId, onApproved, onRejected, onToast }: PitchCardProps) {
  const [notes, setNotes] = useState(pitch.notes ?? '');
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);

  const handleBlur = async () => {
    if (notes === (pitch.notes ?? '')) return;
    setSaving(true);
    try {
      await updatePitchNotes(workspaceId, pitch.id, notes);
    } catch {
      onToast('Failed to save notes', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleApprove = async () => {
    setBusy(true);
    try {
      await approvePitch(workspaceId, pitch.id);
      onToast(`"${pitch.title}" approved — task created in Idea column`, 'success');
      onApproved(pitch.id);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Approve failed';
      onToast(msg, 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async () => {
    setBusy(true);
    try {
      await rejectPitch(workspaceId, pitch.id);
      onToast(`"${pitch.title}" rejected`, 'success');
      onRejected(pitch.id);
    } catch {
      onToast('Reject failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  const origScore = pitch.originality_score;
  const isLow = origScore !== null && origScore < 0.15;

  return (
    <div className={styles.card} data-testid="pitch-card">
      <div className={styles.cardHeader}>
        <span className={styles.title}>{pitch.title}</span>
        <div className={styles.badges}>
          {origScore !== null && (
            <span className={`${styles.badge} ${isLow ? styles.badgeLow : styles.badgeOriginality}`}>
              {isLow ? 'Low Orig.' : `${Math.round(origScore * 100)}% orig.`}
            </span>
          )}
          {pitch.appeal_score !== null && (
            <span className={`${styles.badge} ${styles.badgeAppeal}`}>
              ★ {pitch.appeal_score?.toFixed(1)}
            </span>
          )}
        </div>
      </div>

      <p className={styles.summary}>{pitch.concept_summary}</p>

      <textarea
        className={styles.notes}
        placeholder="Add notes…"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={handleBlur}
        aria-label="Notes"
      />
      {saving && <span style={{ fontSize: '0.65rem', color: 'var(--color-text-secondary)' }}>Saving…</span>}

      <div className={styles.actions}>
        <button className={styles.approveBtn} onClick={handleApprove} disabled={busy}>
          Approve
        </button>
        <button className={styles.rejectBtn} onClick={handleReject} disabled={busy}>
          Reject
        </button>
      </div>
    </div>
  );
}

interface PitchInboxProps {
  onClose: () => void;
}

export default function PitchInbox({ onClose }: PitchInboxProps) {
  const { currentWorkspace } = useWorkspace();
  const [pitches, setPitches] = useState<Pitch[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<ToastState>(null);

  const load = useCallback(async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    try {
      // Show pending + low_originality pitches only
      const all = await fetchPitches(currentWorkspace.id);
      setPitches(all.filter((p) => p.status === 'pending' || p.status === 'low_originality'));
    } finally {
      setLoading(false);
    }
  }, [currentWorkspace]);

  useEffect(() => { load(); }, [load]);

  const removeFromList = (pitchId: string) =>
    setPitches((prev) => prev.filter((p) => p.id !== pitchId));

  return (
    <>
      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
      <div className={styles.overlay} onClick={onClose} />
      <aside className={styles.drawer} role="dialog" aria-label="AI Inbox">
        <div className={styles.header}>
          <h2>AI Inbox</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className={styles.body}>
          {loading ? (
            <p className={styles.empty}>Loading…</p>
          ) : pitches.length === 0 ? (
            <div className={styles.empty}>
              <div className={styles.emptyIcon}>📭</div>
              <p>No pitches waiting for review.</p>
            </div>
          ) : (
            pitches.map((p) => (
              <PitchCard
                key={p.id}
                pitch={p}
                workspaceId={currentWorkspace!.id}
                onApproved={removeFromList}
                onRejected={removeFromList}
                onToast={(msg, type) => setToast({ message: msg, type })}
              />
            ))
          )}
        </div>
      </aside>
    </>
  );
}
