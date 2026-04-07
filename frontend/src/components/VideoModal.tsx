import { useEffect, useState } from 'react';
import type { Task, TaskStatus, OriginalityResult } from '../api/tasks';
import { STATUS_LABELS, transitionTask, updateTask, generateBrief, checkOriginality } from '../api/tasks';
import styles from './VideoModal.module.css';

// ── Pipeline timeline (grouped by stage) ─────────────────────────────────────
const PIPELINE_STAGES: { stage: string; statuses: { status: TaskStatus; label: string }[] }[] = [
  {
    stage: 'Idea',
    statuses: [
      { status: 'brainstorm',  label: 'Brainstorm' },
      { status: 'idea_review', label: 'Pending Review' },
    ],
  },
  {
    stage: 'Writing',
    statuses: [
      { status: 'outline',        label: 'Outline' },
      { status: 'writing_review', label: 'Pending Review' },
    ],
  },
  {
    stage: 'Scripting',
    statuses: [
      { status: 'generate_script', label: 'Generate Script' },
      { status: 'script_review',   label: 'Pending Review' },
    ],
  },
  {
    stage: 'Video',
    statuses: [
      { status: 'generate_clips', label: 'Generate Clips' },
      { status: 'assemble_clips', label: 'Assemble Clips' },
      { status: 'video_review',   label: 'Pending Review' },
    ],
  },
  {
    stage: 'Upload',
    statuses: [
      { status: 'prepare_metadata', label: 'Prepare Metadata' },
      { status: 'publish',          label: 'Publish' },
      { status: 'closed',           label: 'Closed' },
    ],
  },
];

// Flat list for index lookup
const PIPELINE: { status: TaskStatus; label: string }[] = PIPELINE_STAGES.flatMap(s => s.statuses);

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

  // Title editing
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(task.title);
  const [savingTitle, setSavingTitle] = useState(false);

  // Brief editing
  const [editingBrief, setEditingBrief] = useState(false);
  const [brief, setBrief] = useState(task.concept_brief ?? '');
  const [savingBrief, setSavingBrief] = useState(false);
  const [generatingBrief, setGeneratingBrief] = useState(false);

  // Originality
  const [originality, setOriginality] = useState<OriginalityResult | null>(null);
  const [checkingOriginality, setCheckingOriginality] = useState(false);

  const currentIdx = STATUS_INDEX[task.status] ?? 0;

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  const handleSaveTitle = async () => {
    if (!titleDraft.trim() || titleDraft === task.title) { setEditingTitle(false); return; }
    setSavingTitle(true);
    try {
      const updated = await updateTask(task.id, { title: titleDraft.trim() });
      onUpdated(updated);
      setEditingTitle(false);
    } finally {
      setSavingTitle(false);
    }
  };

  const handleGenerateBrief = async () => {
    setGeneratingBrief(true);
    try {
      const generated = await generateBrief(task.id);
      setBrief(generated);
      setEditingBrief(true);
    } finally {
      setGeneratingBrief(false);
    }
  };

  const handleSaveBrief = async () => {
    setSavingBrief(true);
    try {
      const updated = await updateTask(task.id, { concept_brief: brief });
      onUpdated(updated);
      setEditingBrief(false);
      // Auto-run originality check after saving brief
      setCheckingOriginality(true);
      try {
        const result = await checkOriginality(updated.id);
        setOriginality(result);
      } finally {
        setCheckingOriginality(false);
      }
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
            {editingTitle ? (
              <div className={styles.titleEditRow}>
                <input
                  className={styles.titleInput}
                  value={titleDraft}
                  onChange={e => setTitleDraft(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleSaveTitle(); if (e.key === 'Escape') setEditingTitle(false); }}
                  autoFocus
                />
                <button className={styles.titleSaveBtn} onClick={handleSaveTitle} disabled={savingTitle}>
                  {savingTitle ? '…' : '✓'}
                </button>
                <button className={styles.titleCancelBtn} onClick={() => { setEditingTitle(false); setTitleDraft(task.title); }}>✕</button>
              </div>
            ) : (
              <h2 className={styles.title} onClick={() => setEditingTitle(true)} title="Click to edit title">
                {task.title}
                <span className={styles.titleEditHint}>✎</span>
              </h2>
            )}
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* ── Pipeline timeline ── */}
        <div className={styles.timeline}>
          {PIPELINE_STAGES.map(({ stage, statuses }) => {
            const stageStatuses = statuses.map(s => s.status);
            const stageCurrentIdx = stageStatuses.indexOf(task.status);
            const stageDone = currentIdx > PIPELINE.findIndex(p => p.status === stageStatuses[stageStatuses.length - 1]);
            const stageCurrent = stageCurrentIdx !== -1;
            return (
              <div key={stage} className={styles.timelineStage}>
                <div className={`${styles.timelineStageLabel} ${stageDone ? styles.stageDone : stageCurrent ? styles.stageCurrent : ''}`}>
                  {stage}
                </div>
                <div className={styles.timelineSubSteps}>
                  {statuses.map(({ status, label }) => {
                    const idx = PIPELINE.findIndex(p => p.status === status);
                    const done    = idx < currentIdx;
                    const current = idx === currentIdx;
                    return (
                      <div key={status} className={styles.timelineStep}>
                        <div className={`${styles.timelineDot} ${done ? styles.dotDone : ''} ${current ? styles.dotCurrent : ''}`}>
                          {done ? '✓' : ''}
                        </div>
                        <div className={`${styles.timelineLabel} ${current ? styles.labelCurrent : ''}`}>{label}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        {/* ── Concept brief ── */}
        <div className={styles.brief}>
          <div className={styles.briefHeader}>
            <span className={styles.briefLabel}>Video brief</span>
            <div className={styles.briefHeaderActions}>
              <button
                className={styles.briefAiBtn}
                onClick={handleGenerateBrief}
                disabled={generatingBrief}
                title="Generate brief with AI"
              >
                {generatingBrief ? 'Writing…' : '✦ Write with AI'}
              </button>
              {!editingBrief && (
                <button className={styles.briefEdit} onClick={() => setEditingBrief(true)}>Edit</button>
              )}
            </div>
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

          {/* ── Originality check result ── */}
          {checkingOriginality && (
            <div className={styles.originalityChecking}>Checking originality…</div>
          )}
          {originality && !checkingOriginality && (
            <div className={`${styles.originalityResult} ${originality.low_originality ? styles.originalityLow : styles.originalityHigh}`}>
              <div className={styles.originalityHeader}>
                <span className={styles.originalityTitle}>
                  {originality.low_originality ? '⚠ Similar content exists' : '✓ Looks original'}
                </span>
                <span className={styles.originalityScore}>
                  {Math.round(originality.originality_score * 100)}% original
                </span>
              </div>
              {originality.similar_videos.length > 0 && (
                <div className={styles.similarVideos}>
                  {originality.similar_videos.slice(0, 3).map((v) => (
                    <div key={v.video_id} className={styles.similarVideo}>
                      <span className={styles.similarVideoTitle}>{v.title}</span>
                      <span className={styles.similarVideoScore}>{Math.round(v.score * 100)}% match</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
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
