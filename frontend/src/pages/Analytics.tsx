/**
 * Analytics Dashboard — SA-46
 *
 * Displays:
 *   - Workspace summary: total views, likes, cost, published count
 *   - Per-video performance cards sorted by views
 *   - Retention/growth curve chart for a selected video (recharts)
 */
import { useState, useEffect } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Legend,
} from 'recharts';
import { useWorkspace } from '../context/WorkspaceContext';
import {
  getWorkspaceAnalyticsSummary,
  getTaskAnalytics,
  pollAnalyticsNow,
  type WorkspaceAnalyticsSummary,
  type TaskAnalytics,
  type VideoSummary,
} from '../api/video';

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{
      background: '#1a1a1f', border: '1px solid #2a2a30', borderRadius: 8,
      padding: '16px 20px', flex: 1, minWidth: 140,
    }}>
      <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: '#fff' }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function VideoRow({
  video,
  selected,
  onSelect,
}: {
  video: VideoSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 14px', borderRadius: 6, cursor: 'pointer',
        background: selected ? '#1e3a5f' : '#111117',
        border: `1px solid ${selected ? '#2563eb' : '#2a2a30'}`,
        marginBottom: 6, transition: 'all 0.15s',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, color: '#e0e0e0', fontWeight: 500,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {video.title}
        </div>
        {video.youtube_video_id && (
          <div style={{ fontSize: 11, color: '#6b7280' }}>yt:{video.youtube_video_id}</div>
        )}
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div style={{ fontSize: 13, color: '#60a5fa', fontWeight: 600 }}>{formatNumber(video.views)}</div>
        <div style={{ fontSize: 11, color: '#9ca3af' }}>{formatNumber(video.likes)} likes</div>
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function Analytics() {
  const { selectedWorkspace } = useWorkspace();

  const [summary, setSummary] = useState<WorkspaceAnalyticsSummary | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [taskAnalytics, setTaskAnalytics] = useState<TaskAnalytics | null>(null);
  const [polling, setPolling] = useState(false);
  const [loadingChart, setLoadingChart] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedWorkspace) return;
    setError(null);
    getWorkspaceAnalyticsSummary(selectedWorkspace.id)
      .then(setSummary)
      .catch(() => setError('Failed to load analytics'));
  }, [selectedWorkspace]);

  useEffect(() => {
    if (!selectedTaskId) return;
    setLoadingChart(true);
    setTaskAnalytics(null);
    getTaskAnalytics(selectedTaskId)
      .then(setTaskAnalytics)
      .catch(() => setError('Failed to load video analytics'))
      .finally(() => setLoadingChart(false));
  }, [selectedTaskId]);

  async function handlePollNow() {
    if (!selectedTaskId) return;
    setPolling(true);
    try {
      await pollAnalyticsNow(selectedTaskId);
      const fresh = await getTaskAnalytics(selectedTaskId);
      setTaskAnalytics(fresh);
    } catch {
      setError('Poll failed');
    } finally {
      setPolling(false);
    }
  }

  const retentionData = (taskAnalytics?.retention_curve ?? []).map((p) => ({
    ...p,
    date: formatDate(p.date),
  }));

  return (
    <main style={{ padding: 24, background: '#0f0f11', minHeight: '100vh', color: '#e0e0e0', fontFamily: 'system-ui, sans-serif' }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 20, color: '#fff' }}>Analytics</h1>

      {error && <div style={{ color: '#f87171', marginBottom: 12, fontSize: 13 }}>{error}</div>}

      {!selectedWorkspace ? (
        <p style={{ color: '#6b7280' }}>Select a workspace to view analytics.</p>
      ) : !summary ? (
        <p style={{ color: '#6b7280' }}>Loading…</p>
      ) : (
        <>
          {/* Summary cards */}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 24 }}>
            <StatCard label="Published Videos" value={String(summary.published_count)} />
            <StatCard label="Total Views" value={formatNumber(summary.total_views)} />
            <StatCard label="Total Likes" value={formatNumber(summary.total_likes)} />
            <StatCard label="Total Cost" value={`$${summary.total_cost_usd.toFixed(2)}`} sub="across all videos" />
          </div>

          <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
            {/* Video list */}
            <div style={{ width: 320, flexShrink: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#9ca3af', marginBottom: 10 }}>
                Videos ({summary.videos.length})
              </div>
              {summary.videos.length === 0 ? (
                <p style={{ color: '#6b7280', fontSize: 13 }}>No published videos yet.</p>
              ) : (
                summary.videos.map((v) => (
                  <VideoRow
                    key={v.task_id}
                    video={v}
                    selected={selectedTaskId === v.task_id}
                    onSelect={() => setSelectedTaskId(v.task_id)}
                  />
                ))
              )}
            </div>

            {/* Chart panel */}
            <div style={{ flex: 1 }}>
              {!selectedTaskId ? (
                <div style={{ color: '#6b7280', fontSize: 14, padding: '40px 0' }}>
                  Select a video to view its performance chart.
                </div>
              ) : loadingChart ? (
                <div style={{ color: '#6b7280', fontSize: 14 }}>Loading chart…</div>
              ) : taskAnalytics ? (
                <>
                  {/* Latest stats */}
                  <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
                    <StatCard label="Views" value={formatNumber(taskAnalytics.latest.views ?? 0)} />
                    <StatCard label="Likes" value={formatNumber(taskAnalytics.latest.likes ?? 0)} />
                    <StatCard label="Comments" value={formatNumber(taskAnalytics.latest.comments ?? 0)} />
                    <StatCard label="Production Cost" value={`$${taskAnalytics.total_cost_usd}`} />
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <span style={{ fontSize: 14, fontWeight: 600 }}>View Growth Over Time</span>
                    <button
                      onClick={handlePollNow}
                      disabled={polling}
                      style={{
                        background: '#2563eb', color: '#fff', border: 'none',
                        borderRadius: 6, padding: '6px 14px', fontSize: 12, cursor: 'pointer',
                        opacity: polling ? 0.6 : 1,
                      }}
                    >
                      {polling ? 'Polling…' : 'Refresh Now'}
                    </button>
                  </div>

                  {retentionData.length === 0 ? (
                    <p style={{ color: '#6b7280', fontSize: 13 }}>
                      No history yet. Click "Refresh Now" to fetch the latest data.
                    </p>
                  ) : (
                    <>
                      {/* Views line chart */}
                      <div style={{ background: '#1a1a1f', borderRadius: 8, padding: 16, marginBottom: 16, border: '1px solid #2a2a30' }}>
                        <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8 }}>Cumulative Views</div>
                        <ResponsiveContainer width="100%" height={200}>
                          <LineChart data={retentionData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a30" />
                            <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                            <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={formatNumber} />
                            <Tooltip
                              contentStyle={{ background: '#1a1a1f', border: '1px solid #2a2a30', borderRadius: 6 }}
                              labelStyle={{ color: '#e0e0e0' }}
                            />
                            <Line type="monotone" dataKey="views" stroke="#3b82f6" strokeWidth={2} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>

                      {/* Daily growth bar chart */}
                      <div style={{ background: '#1a1a1f', borderRadius: 8, padding: 16, border: '1px solid #2a2a30' }}>
                        <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8 }}>Daily View Growth %</div>
                        <ResponsiveContainer width="100%" height={160}>
                          <BarChart data={retentionData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a30" />
                            <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                            <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} unit="%" />
                            <Tooltip
                              contentStyle={{ background: '#1a1a1f', border: '1px solid #2a2a30', borderRadius: 6 }}
                            />
                            <Bar dataKey="view_growth_pct" fill="#10b981" name="Growth %" />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </>
                  )}
                </>
              ) : null}
            </div>
          </div>
        </>
      )}
    </main>
  );
}
