import { useState, useEffect, useCallback } from 'react';
import type { Character } from '../api/characters';
import { fetchCharacters, createCharacter, deleteCharacter } from '../api/characters';
import { CharacterCard } from '../components/CharacterCard';
import { CreateCharacterModal } from '../components/CreateCharacterModal';
import { Toast } from '../components/Toast';
import styles from './Talent.module.css';

export default function Talent() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchCharacters();
      setCharacters(data);
    } catch {
      setToast({ message: 'Failed to load characters', type: 'error' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async (data: Parameters<typeof createCharacter>[0]) => {
    const created = await createCharacter(data);
    setCharacters((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
    setShowModal(false);
    setToast({ message: `${created.name} added to roster`, type: 'success' });
  };

  const handleDelete = async (id: string) => {
    const char = characters.find((c) => c.id === id);
    await deleteCharacter(id);
    setCharacters((prev) => prev.filter((c) => c.id !== id));
    setToast({ message: `${char?.name ?? 'Character'} removed`, type: 'success' });
  };

  return (
    <main className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>Talent Roster</h1>
        <div className={styles.actions}>
          <button className={styles.secondaryBtn} disabled title="Coming soon">
            Import from Series
          </button>
          <button className={styles.primaryBtn} onClick={() => setShowModal(true)}>
            + Create Character
          </button>
        </div>
      </div>

      {loading ? (
        <p className={styles.empty}>Loading…</p>
      ) : characters.length === 0 ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>🎭</div>
          <p className={styles.emptyTitle}>No characters yet</p>
          <p className={styles.emptySubtitle}>Create your first character to start building your talent roster.</p>
          <button className={styles.primaryBtn} onClick={() => setShowModal(true)}>
            + Create Character
          </button>
        </div>
      ) : (
        <div className={styles.grid}>
          {characters.map((c) => (
            <CharacterCard key={c.id} character={c} onDelete={handleDelete} />
          ))}
        </div>
      )}

      {showModal && (
        <CreateCharacterModal
          onConfirm={handleCreate}
          onCancel={() => setShowModal(false)}
        />
      )}

      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
    </main>
  );
}
