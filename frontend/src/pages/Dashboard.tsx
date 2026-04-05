import { useEffect, useState } from 'react';
import { useWorkspace } from '../context/WorkspaceContext';
import type { Pitch } from '../api/pitches';
import { fetchPitches } from '../api/pitches';

export default function Dashboard() {
  const { currentWorkspace } = useWorkspace();
  const [attentionItems, setAttentionItems] = useState<Pitch[]>([]);

  useEffect(() => {
    if (!currentWorkspace) return;
    fetchPitches(currentWorkspace.id)
      .then((pitches) =>
        setAttentionItems(
          pitches.filter((p) => p.status === 'low_originality' || p.status === 'pending').slice(0, 5),
        ),
      )
      .catch(() => {});
  }, [currentWorkspace]);

  return (
    <main style={{ padding: 'var(--space-8)' }}>
      <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--font-semibold)', marginBottom: 'var(--space-6)' }}>
        Dashboard
      </h1>

      {attentionItems.length > 0 && (
        <section style={{ marginBottom: 'var(--space-8)' }}>
          <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 'var(--font-semibold)', marginBottom: 'var(--space-3)' }}>
            Needs Your Attention
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {attentionItems.map((p) => (
              <div
                key={p.id}
                style={{
                  background: 'var(--color-surface-raised)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-md)',
                  padding: 'var(--space-3) var(--space-4)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 'var(--space-4)',
                }}
              >
                <div>
                  <div style={{ fontWeight: 'var(--font-semibold)', fontSize: 'var(--text-sm)' }}>
                    {p.title}
                  </div>
                  <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)', marginTop: '2px' }}>
                    {p.status === 'low_originality' ? 'Low originality — review before approving' : 'New AI pitch waiting for review'}
                  </div>
                </div>
                <span
                  style={{
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    padding: '2px 8px',
                    borderRadius: 999,
                    background: p.status === 'low_originality' ? '#3b1f1f' : '#1e2f3a',
                    color: p.status === 'low_originality' ? '#f87171' : '#60a5fa',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {p.status === 'low_originality' ? 'Low Originality' : 'Pending Review'}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      <p style={{ color: 'var(--color-text-secondary)' }}>Overview of your workspace activity.</p>
    </main>
  );
}
