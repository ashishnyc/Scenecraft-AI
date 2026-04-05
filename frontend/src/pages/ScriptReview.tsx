import { useState, useEffect, useRef, useCallback } from 'react';
import { useProject } from '../context/ProjectContext';
import { fetchTasksForWorkspace, type Task } from '../api/tasks';
import { approveAudio, requestAudioChanges, type AudioStems } from '../api/audio';
import { useWorkspace } from '../context/WorkspaceContext';
import styles from './ScriptReview.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface SceneLine {
  lineIndex: number;
  sceneNumber: number;
  characterName: string;
  text: string;
  lineType: 'narration' | 'dialogue';
  startMs: number;
}

interface Scene {
  sceneNumber: number;
  lines: SceneLine[];
  startMs: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function buildScenesFromScript(
  fullScript: { scenes: Record<string, unknown>[] } | null,
  audioStems: AudioStems | null,
): Scene[] {
  if (!fullScript?.scenes) return [];

  const chapterTs = audioStems?.chapter_timestamps ?? {};
  const stemsByIndex = Object.fromEntries(
    (audioStems?.stems ?? []).map((s) => [s.line_index, s]),
  );

  let lineIndex = 0;
  const scenes: Scene[] = [];

  for (const rawScene of fullScript.scenes) {
    const sceneNumber = rawScene.scene_number as number;
    const startMs = chapterTs[sceneNumber] ?? 0;
    const lines: SceneLine[] = [];

    const narration = (rawScene.narration as string | undefined)?.trim();
    if (narration) {
      const stem = stemsByIndex[lineIndex];
      lines.push({
        lineIndex,
        sceneNumber,
        characterName: 'narrator',
        text: narration,
        lineType: 'narration',
        startMs: stem ? startMs : startMs,
      });
      lineIndex++;
    }

    for (const turn of (rawScene.dialogue as { character: string; line: string }[]) ?? []) {
      if (!turn.line?.trim()) continue;
      lines.push({
        lineIndex,
        sceneNumber,
        characterName: turn.character,
        text: turn.line,
        lineType: 'dialogue',
        startMs: 0, // refined below if stem data available
      });
      lineIndex++;
    }

    scenes.push({ sceneNumber, lines, startMs });
  }

  return scenes;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ScriptReview() {
  const { currentWorkspace } = useWorkspace();
  const { currentProject } = useProject();

  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [audioStems, setAudioStems] = useState<AudioStems | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  // Player state
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeed] = useState(1);

  // UI state
  const [activeScene, setActiveScene] = useState<number>(1);
  const [activeLineIndex, setActiveLineIndex] = useState<number>(-1);
  const [sceneNotes, setSceneNotes] = useState<Record<number, string>>({});

  // Load tasks for the current project
  useEffect(() => {
    if (!currentWorkspace) return;
    fetchTasksForWorkspace(currentWorkspace.id).then((all) => {
      const reviewable = all.filter(
        (t) =>
          t.status === 'audio_preview' || t.status === 'script_review',
      );
      setTasks(reviewable);
      if (reviewable.length > 0) setSelectedTask(reviewable[0]);
    }).catch(() => {});
  }, [currentWorkspace, currentProject]);

  // Parse script + audio stems when task changes
  useEffect(() => {
    if (!selectedTask?.script) {
      setScenes([]);
      setAudioStems(null);
      setPreviewUrl(null);
      return;
    }

    const script = selectedTask.script as Record<string, unknown>;
    const fullScript = script.full_script as { scenes: Record<string, unknown>[] } | null;
    const stems = script.audio_stems as AudioStems | null;

    setAudioStems(stems ?? null);
    setPreviewUrl(stems?.preview_url ? _resolvePreviewUrl(stems.preview_url) : null);
    setScenes(buildScenesFromScript(fullScript ?? null, stems ?? null));
    setActiveScene(1);
    setActiveLineIndex(-1);
  }, [selectedTask]);

  // Sync playback speed
  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = speed;
  }, [speed]);

  // Update active scene/line based on current audio time
  const onTimeUpdate = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const ms = audio.currentTime * 1000;
    setCurrentTime(audio.currentTime);

    const chapterTs = audioStems?.chapter_timestamps ?? {};
    // Find which scene we're in
    let bestScene = 1;
    for (const [sceneNum, startMs] of Object.entries(chapterTs)) {
      if (ms >= startMs) bestScene = Number(sceneNum);
    }
    setActiveScene(bestScene);
  }, [audioStems]);

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) { audio.pause(); setPlaying(false); }
    else { audio.play(); setPlaying(true); }
  };

  const seekToScene = (sceneNumber: number) => {
    const audio = audioRef.current;
    if (!audio || !audioStems) return;
    const ms = audioStems.chapter_timestamps[sceneNumber] ?? 0;
    audio.currentTime = ms / 1000;
    setActiveScene(sceneNumber);
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Number(e.target.value);
  };

  const handleApprove = async () => {
    if (!selectedTask) return;
    try {
      await approveAudio(selectedTask.id);
      setSelectedTask((t) => t ? { ...t, status: 'script_review' } : t);
    } catch {
      alert('Failed to approve. Please try again.');
    }
  };

  const handleRequestChanges = async () => {
    if (!selectedTask) return;
    const changedScenes = Object.keys(sceneNotes)
      .filter((k) => sceneNotes[Number(k)]?.trim())
      .map(Number);
    if (changedScenes.length === 0) {
      alert('Add notes to the scenes you want changed before requesting.');
      return;
    }
    try {
      await requestAudioChanges(selectedTask.id, sceneNotes, changedScenes);
      setSelectedTask((t) => t ? { ...t, status: 'audio_preview' } : t);
      setSceneNotes({});
    } catch {
      alert('Failed to submit changes. Please try again.');
    }
  };

  const currentSceneData = scenes.find((s) => s.sceneNumber === activeScene);

  if (!currentWorkspace) {
    return <div className={styles.empty}>Select a workspace to review scripts.</div>;
  }

  if (tasks.length === 0) {
    return (
      <div className={styles.empty}>
        No tasks awaiting audio review. Tasks enter this view when in{' '}
        <em>Audio Preview</em> or <em>Script Review</em> status.
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {/* Top bar */}
      <div className={styles.topBar}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
          {tasks.length > 1 && (
            <select
              value={selectedTask?.id ?? ''}
              onChange={(e) => setSelectedTask(tasks.find((t) => t.id === e.target.value) ?? null)}
              style={{
                background: 'var(--color-bg-tertiary)',
                color: 'var(--color-text-primary)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-sm)',
                padding: 'var(--space-1) var(--space-2)',
                fontSize: 'var(--text-sm)',
              }}
            >
              {tasks.map((t) => (
                <option key={t.id} value={t.id}>{t.title}</option>
              ))}
            </select>
          )}
          <span className={styles.taskTitle}>{selectedTask?.title ?? 'Script Review'}</span>
        </div>
        <div className={styles.topActions}>
          <button className={styles.btnChanges} onClick={handleRequestChanges}>
            Request Changes
          </button>
          <button className={styles.btnApprove} onClick={handleApprove}>
            Approve Audio
          </button>
        </div>
      </div>

      {/* Audio player */}
      <div className={styles.player}>
        {previewUrl && (
          <audio
            ref={audioRef}
            src={previewUrl}
            onTimeUpdate={onTimeUpdate}
            onLoadedMetadata={() => setDuration(audioRef.current?.duration ?? 0)}
            onEnded={() => setPlaying(false)}
          />
        )}
        <div className={styles.playerControls}>
          <button
            className={styles.btnPlay}
            onClick={togglePlay}
            disabled={!previewUrl}
            aria-label={playing ? 'Pause' : 'Play'}
          >
            {playing ? '⏸' : '▶'}
          </button>

          <div className={styles.progressWrap}>
            <input
              type="range"
              className={styles.progressBar}
              min={0}
              max={duration || 1}
              step={0.1}
              value={currentTime}
              onChange={handleSeek}
              disabled={!previewUrl}
            />
            <div className={styles.timeRow}>
              <span>{formatTime(currentTime)}</span>
              <span>{formatTime(duration)}</span>
            </div>
          </div>

          <div className={styles.speedGroup}>
            {([1, 1.5, 2] as const).map((s) => (
              <button
                key={s}
                className={`${styles.speedBtn} ${speed === s ? styles.speedBtnActive : ''}`}
                onClick={() => setSpeed(s)}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>

        {!previewUrl && (
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
            {selectedTask?.status === 'audio_preview'
              ? 'Audio is being generated…'
              : 'No audio preview available yet.'}
          </p>
        )}
      </div>

      {/* Scene list + script panel */}
      <div className={styles.body}>
        {/* Scene list */}
        <div className={styles.sceneList}>
          {scenes.map((scene) => (
            <div
              key={scene.sceneNumber}
              className={`${styles.sceneItem} ${scene.sceneNumber === activeScene ? styles.sceneItemActive : ''}`}
              onClick={() => seekToScene(scene.sceneNumber)}
            >
              <div className={styles.sceneNumber}>Scene {scene.sceneNumber}</div>
              {audioStems?.chapter_timestamps[scene.sceneNumber] !== undefined && (
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                  {formatTime((audioStems.chapter_timestamps[scene.sceneNumber] ?? 0) / 1000)}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Script panel */}
        <div className={styles.scriptPanel}>
          {currentSceneData ? (
            <>
              <div className={styles.sceneHeader}>Scene {currentSceneData.sceneNumber}</div>

              {currentSceneData.lines.map((line) => (
                <div
                  key={line.lineIndex}
                  className={`${styles.lineBlock} ${line.lineIndex === activeLineIndex ? styles.lineBlockActive : ''}`}
                >
                  <div
                    className={`${styles.lineCharacter} ${line.lineType === 'narration' ? styles.lineNarrator : ''}`}
                  >
                    {line.lineType === 'narration' ? 'Narration' : line.characterName}
                  </div>
                  <div className={styles.lineText}>{line.text}</div>
                </div>
              ))}

              {/* Notes for this scene */}
              <div className={styles.notesSection}>
                <div className={styles.notesLabel}>Notes for Scene {currentSceneData.sceneNumber}</div>
                <textarea
                  className={styles.notesInput}
                  placeholder="Describe what needs changing in this scene…"
                  value={sceneNotes[currentSceneData.sceneNumber] ?? ''}
                  onChange={(e) =>
                    setSceneNotes((prev) => ({
                      ...prev,
                      [currentSceneData.sceneNumber]: e.target.value,
                    }))
                  }
                />
              </div>
            </>
          ) : (
            <div className={styles.empty}>Select a scene to view the script.</div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Convert s3://bucket/key to a backend proxy URL the browser can fetch. */
function _resolvePreviewUrl(s3Url: string): string {
  // In production the backend exposes a signed-URL endpoint; for dev we proxy directly
  const key = s3Url.replace(/^s3:\/\/[^/]+\//, '');
  return `/api/audio/stream/${encodeURIComponent(key)}`;
}
