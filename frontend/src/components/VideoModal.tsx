import { useEffect, useState } from 'react';
import type { Task, TaskStatus, OriginalityResult, BriefVersion } from '../api/tasks';
import { STATUS_LABELS, updateTask, deleteTask, generateBrief, checkOriginality } from '../api/tasks';
import styles from './VideoModal.module.css';

// ── Stage tabs ────────────────────────────────────────────────────────────────
type Tab = 'idea' | 'writing' | 'script' | 'video' | 'upload';

const TABS: { id: Tab; label: string; stages: TaskStatus[] }[] = [
  { id: 'idea',    label: 'Idea',    stages: ['brainstorm', 'idea_review'] },
  { id: 'writing', label: 'Writing', stages: ['outline', 'writing_review'] },
  { id: 'script',  label: 'Script',  stages: ['generate_script', 'script_review'] },
  { id: 'video',   label: 'Video',   stages: ['generate_clips', 'assemble_clips', 'video_review'] },
  { id: 'upload',  label: 'Upload',  stages: ['prepare_metadata', 'publish', 'closed'] },
];

// Determine the active tab from the task's current status
function tabForStatus(status: TaskStatus): Tab {
  return TABS.find(t => t.stages.includes(status))?.id ?? 'idea';
}

// ── Idea tab ──────────────────────────────────────────────────────────────────
interface IdeaTabProps {
  task: Task;
  onUpdated: (t: Task) => void;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function IdeaTab({ task, onUpdated }: IdeaTabProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(task.concept_brief ?? '');
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [originality, setOriginality] = useState<OriginalityResult | null>(null);
  const [checkingOriginality, setCheckingOriginality] = useState(false);
  const [history, setHistory] = useState<BriefVersion[]>(task.brief_history ?? []);

  const handleEdit = () => {
    setDraft(task.concept_brief ?? '');
    setEditing(true);
  };

  const handleCancel = () => {
    setDraft(task.concept_brief ?? '');
    setEditing(false);
  };

  const handleGenerateBrief = async () => {
    setGenerating(true);
    try {
      const generated = await generateBrief(task.id);
      setDraft(generated);
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    if (draft === task.concept_brief) { setEditing(false); return; }
    setSaving(true);
    try {
      const source = generating ? 'ai' : 'manual';
      const updated = await updateTask(task.id, { concept_brief: draft, _source: source });
      onUpdated(updated);
      setHistory(updated.brief_history ?? []);
      setEditing(false);
      setCheckingOriginality(true);
      try {
        const result = await checkOriginality(updated.id);
        setOriginality(result);
      } finally {
        setCheckingOriginality(false);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteVersion = async (indexInReversed: number) => {
    const reversed = [...history].reverse();
    reversed.splice(indexInReversed, 1);
    const newHistory = [...reversed].reverse();
    const updated = await updateTask(task.id, { brief_history: newHistory });
    onUpdated(updated);
    setHistory(updated.brief_history ?? []);
  };

  const versions = [...history].reverse();

  return (
    <div className={styles.tabContent}>
      {/* ── Current brief — styled same as history items ── */}
      <div className={styles.historyTimeline}>
        <div className={styles.historyItem}>
          <div className={`${styles.historyDot} ${styles.historyDotCurrent}`} />
          <div className={styles.historyLine} />
          <div className={styles.historyBody}>
            <div className={styles.historyMeta}>
              <span className={styles.sectionLabel}>Current Brief</span>
              {!editing && (
                <button className={styles.briefEdit} onClick={handleEdit}>Edit</button>
              )}
            </div>

            {editing ? (
              <>
                <div className={styles.briefEditActions}>
                  <button className={styles.briefAiBtn} onClick={handleGenerateBrief} disabled={generating}>
                    {generating ? 'Writing…' : '✦ Write with AI'}
                  </button>
                </div>
                <textarea
                  className={styles.briefTextarea}
                  value={draft}
                  onChange={e => setDraft(e.target.value)}
                  rows={5}
                  autoFocus
                />
                <div className={styles.briefActions}>
                  <button className={styles.briefSave} onClick={handleSave} disabled={saving}>
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                  <button className={styles.briefCancel} onClick={handleCancel}>Cancel</button>
                </div>
              </>
            ) : (
              <p className={styles.briefText}>
                {task.concept_brief
                  ? task.concept_brief
                  : <span className={styles.briefMissing}>No brief yet — click Edit to add one</span>
                }
              </p>
            )}

            {/* Originality */}
            {checkingOriginality && <div className={styles.originalityChecking}>Checking originality…</div>}
            {originality && !checkingOriginality && (
              <div className={`${styles.originalityResult} ${originality.low_originality ? styles.originalityLow : styles.originalityHigh}`}>
                <div className={styles.originalityHeader}>
                  <span className={styles.originalityTitle}>
                    {originality.low_originality ? '⚠ Similar content exists' : '✓ Looks original'}
                  </span>
                  <span className={styles.originalityScore}>{Math.round(originality.originality_score * 100)}% original</span>
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
        </div>

        {/* ── Version history ── */}
        {versions.map((v, i) => (
          <div key={i} className={styles.historyItem}>
            <div className={styles.historyDot} />
            {i < versions.length - 1 && <div className={styles.historyLine} />}
            <div className={styles.historyBody}>
              <div className={styles.historyMeta}>
                <span className={`${styles.historySource} ${v.source === 'ai' ? styles.historySourceAi : ''}`}>
                  {v.source === 'ai' ? '✦ AI' : 'Manual'}
                </span>
                <span className={styles.historyDate}>{formatDate(v.created_at)}</span>
                <button className={styles.historyDeleteBtn} onClick={() => handleDeleteVersion(i)} title="Delete this version">
                  🗑
                </button>
              </div>
              <p className={styles.historyContent}>{v.content}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Writing tab ───────────────────────────────────────────────────────────────
function WritingTab({ script }: { script: Record<string, unknown> | null }) {
  const outline = script?.outline as Record<string, unknown> | undefined;

  if (!outline) return (
    <div className={styles.tabContent}>
      <p className={styles.empty}>No outline yet. Move to Writing to generate one.</p>
    </div>
  );

  return (
    <div className={styles.tabContent}>
      <div className={styles.sectionLabel}>Outline</div>
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
  );
}

// ── Script tab ────────────────────────────────────────────────────────────────
function ScriptTab({ script }: { script: Record<string, unknown> | null }) {
  const fullScript = script?.full_script as Record<string, unknown> | undefined;

  if (!fullScript) return (
    <div className={styles.tabContent}>
      <p className={styles.empty}>No script yet. Move to Generate Script to start generation.</p>
    </div>
  );

  return (
    <div className={styles.tabContent}>
      <div className={styles.sectionLabel}>Full Script</div>
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
  );
}

// ── Video tab ─────────────────────────────────────────────────────────────────
function VideoTab({ task }: { task: Task }) {
  if (!task.final_video_url) return (
    <div className={styles.tabContent}>
      <p className={styles.empty}>No video yet. Move to Generate Clips to start production.</p>
    </div>
  );

  return (
    <div className={styles.tabContent}>
      <video controls src={task.final_video_url} className={styles.videoPlayer} />
    </div>
  );
}

// ── Upload tab ────────────────────────────────────────────────────────────────
function UploadTab({ task }: { task: Task }) {
  if (!task.youtube_video_id) return (
    <div className={styles.tabContent}>
      <p className={styles.empty}>Not uploaded yet. Move to Prepare Metadata to begin the upload process.</p>
    </div>
  );

  return (
    <div className={styles.tabContent}>
      <div className={styles.sectionLabel}>YouTube</div>
      <a
        href={`https://youtube.com/watch?v=${task.youtube_video_id}`}
        target="_blank"
        rel="noreferrer"
        className={styles.ytLink}
      >
        ▶ View on YouTube
      </a>
      {task.total_cost_usd && (
        <div className={styles.costRow}>
          <span className={styles.costLabel}>Production cost</span>
          <span className={styles.costValue}>${task.total_cost_usd}</span>
        </div>
      )}
    </div>
  );
}

// ── Main modal ────────────────────────────────────────────────────────────────
interface Props {
  task: Task;
  onClose: () => void;
  onUpdated: (task: Task) => void;
  onDeleted?: (taskId: string) => void;
}

export function VideoModal({ task, onClose, onUpdated, onDeleted }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>(() => tabForStatus(task.status));

  // Title editing
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(task.title);
  const [savingTitle, setSavingTitle] = useState(false);

  // Delete
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteTask(task.id);
      onDeleted?.(task.id);
      onClose();
    } finally {
      setDeleting(false);
    }
  };

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
          <div className={styles.headerRight}>
            {confirmDelete ? (
              <div className={styles.deleteConfirm}>
                <span className={styles.deleteConfirmText}>Delete this video?</span>
                <button className={styles.deleteConfirmYes} onClick={handleDelete} disabled={deleting}>
                  {deleting ? 'Deleting…' : 'Yes, delete'}
                </button>
                <button className={styles.deleteConfirmNo} onClick={() => setConfirmDelete(false)}>Cancel</button>
              </div>
            ) : (
              <button className={styles.deleteBtn} onClick={() => setConfirmDelete(true)} title="Delete video">
                🗑
              </button>
            )}
            <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
          </div>
        </div>

        {/* ── Stage tabs ── */}
        <div className={styles.tabs}>
          {TABS.map(({ id, label, stages }) => {
            const isCurrent = stages.includes(task.status);
            const stageIdx = TABS.findIndex(t => t.id === id);
            const currentStageIdx = TABS.findIndex(t => t.stages.includes(task.status));
            const isDone = stageIdx < currentStageIdx;
            return (
              <button
                key={id}
                className={`${styles.tab} ${activeTab === id ? styles.tabActive : ''} ${isCurrent ? styles.tabCurrent : ''} ${isDone ? styles.tabDone : ''}`}
                onClick={() => setActiveTab(id)}
              >
                {isDone && <span className={styles.tabCheck}>✓</span>}
                {label}
              </button>
            );
          })}
        </div>

        {/* ── Tab content ── */}
        <div className={styles.body}>
          {activeTab === 'idea'    && <IdeaTab task={task} onUpdated={onUpdated} />}
          {activeTab === 'writing' && <WritingTab script={task.script} />}
          {activeTab === 'script'  && <ScriptTab script={task.script} />}
          {activeTab === 'video'   && <VideoTab task={task} />}
          {activeTab === 'upload'  && <UploadTab task={task} />}
        </div>
      </div>
    </div>
  );
}
