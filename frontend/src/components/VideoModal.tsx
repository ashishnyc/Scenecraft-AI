import { useEffect, useState } from 'react';
import type { Task, TaskStatus } from '../api/tasks';
import { STATUS_LABELS, transitionTask } from '../api/tasks';
import { updateTask } from '../api/tasks';
import styles from './VideoModal.module.css';

// ── Pipeline timeline ─────────────────────────────────────────────────────────
const PIPELINE: { status: TaskStatus; label: string }[] = [
  { status: 'idea',          label: 'Idea' },
  { status: 'approved',      label: 'Approved' },
  { status: 'scripting',     label: 'Script' },
  { status: 'audio_preview', label: 'Audio' },
  { status: 'script_review', label: 'Review' },
  { status: 'producing',     label: 'Producing' },
  { status: 'final_review',  label: 'Final Review' },
  { status: 'scheduled',     label: 'Scheduled' },
  { status: 'published',     label: 'Published' },
];

const STATUS_INDEX: Record<TaskStatus, number> = Object.fromEntries(
  PIPELINE.map(({ status }, i) => [status, i])
) as Record<TaskStatus, number>;

// ── Script renderer ───────────────────────────────────────────────────────────
function ScriptSection({ script }: { script: Record<string, unknown> | null }) {
  if (!script) return <p className={styles.empty}>No script yet. Approve the video brief to start generation.</p>;

  const outline    = script.outline    as Record<string, unknown> | undefined;
  const fullScript = script.full_script as Record<string, unknown> | undefined;

  return (
    <div className={styles.scriptBody}>
      {outline && (
        <div className={styles.scriptBlock}>
          <div className={styles.blockLabel}>Outline</div>
          {(outline.logline as string) && <p className={styles.logline}>{outline.logline as string}</p>}
          {(outline.acts as unknown[])?.map((act: unknown, i: number) => {
            const a = act as Record<string, unknown>;
            return (
              <div key={i} className={styles.act}>
                <div className={styles.actTitle}>Act {i + 1}{a.title ? ` — ${a.title}` : ''}</div>
                {(a.scenes as unknown[])?.map((scene: unknown, j: number) => {
                  const s = scene as Record<string, unknown>;
                  return (
                    <div key={j} className={styles.scene}>
                      <span className={styles.sceneNum}>Scene {s.scene_number as number}</span>
                      <span className={styles.sceneDesc}>{s.description as string}</span>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      )}
      {fullScript && (
        <div className={styles.scriptBlock}>
          <div className={styles.blockLabel}>Full Script</div>
          {(fullScript.scenes as unknown[])?.map((scene: unknown, i: number) => {
            const s = scene as Record<string, unknown>;
            return (
              <div key={i} className={styles.fullScene}>
                <div className={styles.fullSceneHeader}>Scene {s.scene_number as number}</div>
                {(s.dialogue_beats as unknown[])?.map((beat: unknown, j: number) => {
                  const b = beat as Record<string, unknown>;
                  return (
                    <div key={j} className={styles.beat}>
                      {b.character && <span className={styles.character}>{b.character as string}</span>}
                      <span className={styles.line}>{(b.line || b.action || b.narration) as string}</span>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Audio section ─────────────────────────────────────────────────────────────
function AudioSection({ script }: { script: Record<string, unknown> | null }) {
  const audioStems = script?.audio_stems as Record<string, unknown> | undefined;
  if (!audioStems) return <p className={styles.empty}>No audio generated yet.</p>;

  return (
    <div className={styles.audioBody}>
      {Object.entries(audioStems).map(([character, url]) => (
        <div key={character} className={styles.audioTrack}>
          <div className={styles.audioLabel}>{character}</div>
          {typeof url === 'string' && url ? (
            <audio controls src={url} className={styles.audioPlayer} />
          ) : (
            <span className={styles.audioMissing}>Not generated</span>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Video section ─────────────────────────────────────────────────────────────
function VideoSection({ task }: { task: Task }) {
  if (!task.final_video_url) return <p className={styles.empty}>No video yet.</p>;
  return (
    <div className={styles.videoBody}>
      <video controls src={task.final_video_url} className={styles.videoPlayer} />
      {task.youtube_video_id && (
        <a
          href={`https://youtube.com/watch?v=${task.youtube_video_id}`}
          target="_blank"
          rel="noreferrer"
          className={styles.ytLink}
        >
          ▶ View on YouTube
        </a>
      )}
    </div>
  );
}

// ── Main modal ────────────────────────────────────────────────────────────────
interface Props {
  task: Task;
  onClose: () => void;
  onUpdated: (task: Task) => void;
}

type Tab = 'script' | 'audio' | 'video';

export function VideoModal({ task, onClose, onUpdated }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('script');
  const [editingBrief, setEditingBrief] = useState(false);
  const [brief, setBrief] = useState(task.concept_brief ?? '');
  const [savingBrief, setSavingBrief] = useState(false);
  const currentIdx = STATUS_INDEX[task.status] ?? 0;

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  const handleSaveBrief = async () => {
    setSavingBrief(true);
    try {
      const updated = await updateTask(task.id, { concept_brief: brief });
      onUpdated(updated);
      setEditingBrief(false);
    } finally {
      setSavingBrief(false);
    }
  };

  const hasScript = !!task.script?.outline || !!task.script?.full_script;
  const hasAudio  = !!task.script?.audio_stems;
  const hasVideo  = !!task.final_video_url;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>

        {/* ── Header ── */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <span className={`${styles.statusBadge} ${styles[`badge_${task.status}`]}`}>
              {STATUS_LABELS[task.status]}
            </span>
            <h2 className={styles.title}>{task.title}</h2>
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* ── Pipeline timeline ── */}
        <div className={styles.timeline}>
          {PIPELINE.map(({ status, label }, idx) => {
            const done    = idx < currentIdx;
            const current = idx === currentIdx;
            return (
              <div key={status} className={styles.timelineStep}>
                <div className={`${styles.timelineDot} ${done ? styles.dotDone : ''} ${current ? styles.dotCurrent : ''}`}>
                  {done ? '✓' : idx + 1}
                </div>
                <div className={`${styles.timelineLabel} ${current ? styles.labelCurrent : ''}`}>{label}</div>
                {idx < PIPELINE.length - 1 && (
                  <div className={`${styles.timelineConnector} ${done ? styles.connectorDone : ''}`} />
                )}
              </div>
            );
          })}
        </div>

        {/* ── Concept brief ── */}
        <div className={styles.brief}>
          <div className={styles.briefHeader}>
            <span className={styles.briefLabel}>Video brief</span>
            {!editingBrief && (
              <button className={styles.briefEdit} onClick={() => setEditingBrief(true)}>Edit</button>
            )}
          </div>
          {editingBrief ? (
            <div className={styles.briefEditRow}>
              <textarea className={styles.briefTextarea} value={brief} onChange={e => setBrief(e.target.value)} rows={3} />
              <div className={styles.briefActions}>
                <button className={styles.briefSave} onClick={handleSaveBrief} disabled={savingBrief}>
                  {savingBrief ? 'Saving…' : 'Save'}
                </button>
                <button className={styles.briefCancel} onClick={() => { setEditingBrief(false); setBrief(task.concept_brief ?? ''); }}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <p className={styles.briefText}>{task.concept_brief || <span className={styles.briefMissing}>No brief yet — add one to approve this video</span>}</p>
          )}
        </div>

        {/* ── Content tabs ── */}
        <div className={styles.tabs}>
          {([
            { id: 'script' as Tab, label: 'Script',  has: hasScript },
            { id: 'audio'  as Tab, label: 'Audio',   has: hasAudio },
            { id: 'video'  as Tab, label: 'Video',   has: hasVideo },
          ]).map(({ id, label, has }) => (
            <button
              key={id}
              className={`${styles.tab} ${activeTab === id ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(id)}
            >
              {label}
              {has && <span className={styles.tabDot} />}
            </button>
          ))}
        </div>

        {/* ── Tab content ── */}
        <div className={styles.body}>
          {activeTab === 'script' && <ScriptSection script={task.script} />}
          {activeTab === 'audio'  && <AudioSection script={task.script} />}
          {activeTab === 'video'  && <VideoSection task={task} />}
        </div>
      </div>
    </div>
  );
}
