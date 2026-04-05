import { useState, useEffect, useRef } from 'react';
import { useProject } from '../context/ProjectContext';
import { useWorkspace } from '../context/WorkspaceContext';
import { fetchTasksForWorkspace, type Task } from '../api/tasks';
import {
  getVideoReviewData,
  createHlsPreview,
  approveVideo,
  requestVideoChanges,
  type VideoReviewData,
  type Shot,
} from '../api/video';
import styles from './VideoReview.module.css';

type SidebarTab = 'shots' | 'feedback';

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDuration(seconds: number): string {
  return `${seconds.toFixed(1)}s`;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function VideoReview() {
  const { selectedProject } = useProject();
  const { selectedWorkspace } = useWorkspace();

  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [reviewData, setReviewData] = useState<VideoReviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<SidebarTab>('shots');
  const [flaggedShots, setFlaggedShots] = useState<Set<number>>(new Set());
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [feedbackResult, setFeedbackResult] = useState<string | null>(null);

  const [hlsUrl, setHlsUrl] = useState<string | null>(null);
  const [hlsLoading, setHlsLoading] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);

  // Load tasks in final_review status
  useEffect(() => {
    if (!selectedWorkspace) return;
    fetchTasksForWorkspace(selectedWorkspace.id)
      .then((all) => setTasks(all.filter((t) => t.status === 'final_review')))
      .catch(() => setTasks([]));
  }, [selectedWorkspace]);

  // Load review data when task selected
  useEffect(() => {
    if (!selectedTaskId) return;
    setLoading(true);
    setReviewData(null);
    setError(null);
    setFlaggedShots(new Set());
    setNotes('');
    setFeedbackResult(null);
    setHlsUrl(null);

    getVideoReviewData(selectedTaskId)
      .then((data) => {
        setReviewData(data);
        if (data.hls_signed_url) setHlsUrl(data.hls_signed_url);
      })
      .catch(() => setError('Failed to load review data'))
      .finally(() => setLoading(false));
  }, [selectedTaskId]);

  // HLS.js integration
  useEffect(() => {
    if (!hlsUrl || !videoRef.current) return;
    const vid = videoRef.current;

    if (vid.canPlayType('application/vnd.apple.mpegurl')) {
      vid.src = hlsUrl;
    } else {
      import('hls.js').then(({ default: Hls }) => {
        if (Hls.isSupported()) {
          const hls = new Hls();
          hls.loadSource(hlsUrl);
          hls.attachMedia(vid);
        }
      }).catch(() => {
        vid.src = hlsUrl;
      });
    }
  }, [hlsUrl]);

  async function handleGenerateHls() {
    if (!selectedTaskId) return;
    setHlsLoading(true);
    try {
      const result = await createHlsPreview(selectedTaskId);
      setHlsUrl(result.signed_url);
    } catch {
      setError('HLS generation failed');
    } finally {
      setHlsLoading(false);
    }
  }

  function toggleFlag(idx: number) {
    setFlaggedShots((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }

  async function handleApprove() {
    if (!selectedTaskId) return;
    setSubmitting(true);
    try {
      await approveVideo(selectedTaskId, notes);
      setFeedbackResult('Video approved — moving to Scheduled.');
    } catch {
      setError('Approval failed');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRequestChanges() {
    if (!selectedTaskId) return;
    setSubmitting(true);
    try {
      await requestVideoChanges(selectedTaskId, notes, Array.from(flaggedShots));
      setFeedbackResult('Changes requested — task returned to Producing.');
    } catch {
      setError('Request failed');
    } finally {
      setSubmitting(false);
    }
  }

  const shots: Shot[] = reviewData?.shot_list?.shots ?? [];
  const qc = reviewData?.quality_report ?? null;

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <h1>{reviewData?.title ?? 'Video Review'}</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {reviewData?.status && (
            <span className={styles.statusBadge}>{reviewData.status.replace('_', ' ')}</span>
          )}
          {reviewData && (
            <span className={styles.cost}>Cost: ${reviewData.total_cost_usd}</span>
          )}
          {/* Task picker */}
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
      </div>

      {loading && <div className={styles.loading}>Loading review data…</div>}
      {error && <div style={{ padding: 20, color: '#f87171' }}>{error}</div>}

      {reviewData && (
        <div className={styles.body}>
          {/* Player + QC */}
          <div className={styles.playerPanel}>
            <div className={styles.videoWrapper}>
              {hlsUrl ? (
                <video ref={videoRef} controls />
              ) : (
                <div className={styles.hlsNotice}>
                  <span>HLS preview not generated yet</span>
                  <button
                    className={styles.hlsButton}
                    onClick={handleGenerateHls}
                    disabled={hlsLoading}
                  >
                    {hlsLoading ? 'Generating…' : 'Generate HLS Preview'}
                  </button>
                </div>
              )}
            </div>

            {/* Quality Report */}
            {qc && (
              <div className={styles.qualityReport}>
                <h3 className={qc.passed ? styles.qcPassed : styles.qcFailed}>
                  QC {qc.passed ? 'PASSED' : 'FAILED'}
                </h3>
                {qc.errors.length > 0 && (
                  <ul className={styles.qcList}>
                    {qc.errors.map((e, i) => (
                      <li key={i} className={styles.qcError}>{e}</li>
                    ))}
                  </ul>
                )}
                {qc.warnings.length > 0 && (
                  <ul className={styles.qcList} style={{ marginTop: 6 }}>
                    {qc.warnings.map((w, i) => (
                      <li key={i} className={styles.qcWarning}>{w}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className={styles.sidebar}>
            <div className={styles.sidebarTabs}>
              <button
                className={`${styles.tabBtn} ${activeTab === 'shots' ? styles.active : ''}`}
                onClick={() => setActiveTab('shots')}
              >
                Shots ({shots.length})
              </button>
              <button
                className={`${styles.tabBtn} ${activeTab === 'feedback' ? styles.active : ''}`}
                onClick={() => setActiveTab('feedback')}
              >
                Feedback
              </button>
            </div>

            <div className={styles.sidebarContent}>
              {activeTab === 'shots' && (
                <>
                  {shots.map((shot) => (
                    <div
                      key={shot.shot_index}
                      className={`${styles.shotCard} ${flaggedShots.has(shot.shot_index) ? styles.flagged : ''}`}
                    >
                      <div className={styles.shotHeader}>
                        <span className={styles.shotIndex}>Shot {shot.shot_index + 1}</span>
                        <span className={styles.shotDuration}>{formatDuration(shot.duration_seconds)}</span>
                      </div>
                      <div className={styles.shotEnv}>{shot.environment}</div>
                      <div className={styles.shotAction}>{shot.action_description}</div>
                      <button
                        className={`${styles.flagToggle} ${flaggedShots.has(shot.shot_index) ? styles.active : ''}`}
                        onClick={() => toggleFlag(shot.shot_index)}
                      >
                        {flaggedShots.has(shot.shot_index) ? 'Flagged' : 'Flag'}
                      </button>
                    </div>
                  ))}
                  {shots.length === 0 && (
                    <p style={{ color: '#6b7280', fontSize: 13 }}>No shots available.</p>
                  )}
                </>
              )}

              {activeTab === 'feedback' && (
                <div className={styles.feedbackPanel}>
                  {flaggedShots.size > 0 && (
                    <div style={{ fontSize: 12, color: '#fbbf24' }}>
                      {flaggedShots.size} shot(s) flagged for changes
                    </div>
                  )}
                  <label>Notes</label>
                  <textarea
                    className={styles.notesArea}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Describe what needs to change, or approve the video as-is…"
                  />
                  {feedbackResult ? (
                    <div className={styles.successMsg}>{feedbackResult}</div>
                  ) : (
                    <div className={styles.actionRow}>
                      <button
                        className={styles.approveBtn}
                        onClick={handleApprove}
                        disabled={submitting}
                      >
                        Approve
                      </button>
                      <button
                        className={styles.changesBtn}
                        onClick={handleRequestChanges}
                        disabled={submitting}
                      >
                        Request Changes
                      </button>
                    </div>
                  )}
                  {error && <div className={styles.errorMsg}>{error}</div>}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
