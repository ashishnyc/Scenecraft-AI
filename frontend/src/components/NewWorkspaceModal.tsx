import { useState } from 'react';
import { apiClient } from '../api/client';
import styles from './NewProjectModal.module.css';
import modalStyles from './NewWorkspaceModal.module.css';

interface Props {
  onConfirm: (name: string, youtubeChannelId: string) => Promise<void>;
  onCancel: () => void;
}

interface ChannelValidation {
  valid: boolean;
  channel_id: string | null;
  channel_name: string | null;
}

export function NewWorkspaceModal({ onConfirm, onCancel }: Props) {
  const [channelInput, setChannelInput] = useState('');
  const [validation, setValidation] = useState<ChannelValidation | null>(null);
  const [validating, setValidating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleValidate = async () => {
    if (!channelInput.trim()) return;
    setValidating(true);
    setValidation(null);
    setError(null);
    try {
      const res = await apiClient.get<ChannelValidation>('/workspaces/validate-channel', {
        params: { channel_id: channelInput.trim() },
      });
      setValidation(res.data);
      if (!res.data.valid) setError('Channel not found. Check the ID or handle and try again.');
    } catch {
      setError('Could not reach YouTube API. Check your connection and try again.');
    } finally {
      setValidating(false);
    }
  };

  const handleChannelChange = (val: string) => {
    setChannelInput(val);
    setValidation(null);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validation?.valid || !validation.channel_id || !validation.channel_name) return;
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm(validation.channel_name, validation.channel_id);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to create workspace';
      setError(msg);
      setSubmitting(false);
    }
  };

  const canSubmit = validation?.valid === true && !submitting;

  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.title}>New Workspace</h2>
        <form onSubmit={handleSubmit} className={styles.form}>

          <label className={styles.label}>
            YouTube channel
            <div className={modalStyles.channelRow}>
              <input
                className={styles.input}
                value={channelInput}
                onChange={(e) => handleChannelChange(e.target.value)}
                placeholder="UCxxxxxx or @handle"
                autoFocus
                required
              />
              <button
                type="button"
                className={modalStyles.checkBtn}
                onClick={handleValidate}
                disabled={validating || !channelInput.trim()}
              >
                {validating ? '…' : 'Check'}
              </button>
            </div>
            {validation?.valid && (
              <span className={modalStyles.channelValid}>
                ✓ {validation.channel_name} — will be used as workspace name
              </span>
            )}
          </label>

          {error && <p className={styles.error}>{error}</p>}

          <div className={styles.actions}>
            <button type="button" className={styles.cancelBtn} onClick={onCancel} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className={styles.submitBtn} disabled={!canSubmit}>
              {submitting ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
