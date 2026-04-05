/**
 * Talent Roster page (SA-63).
 * Browse characters, view profiles, drag-to-cast into projects.
 */
import { useState, useEffect, useCallback } from 'react';
import type { Character, Casting, CastingRole } from '../api/characters';
import { fetchCharacters, createCharacter, deleteCharacter, fetchCast, castCharacter, removeFromCast } from '../api/characters';
import { CharacterCard } from '../components/CharacterCard';
import { CharacterProfile } from '../components/CharacterProfile';
import { CreateCharacterModal } from '../components/CreateCharacterModal';
import { Toast } from '../components/Toast';
import { useWorkspace } from '../context/WorkspaceContext';
import { fetchProjects } from '../api/projects';
import styles from './Talent.module.css';

interface Project { id: string; title: string; }

export default function Talent() {
  const { workspaceId } = useWorkspace();
  const [characters, setCharacters] = useState<Character[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [castByProject, setCastByProject] = useState<Record<string, Casting[]>>({});
  const [selectedProject, setSelectedProject] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [profileChar, setProfileChar] = useState<Character | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [dragging, setDragging] = useState<Character | null>(null);
  const [castingRole, setCastingRole] = useState<CastingRole>('supporting');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [chars, projs] = await Promise.all([
        fetchCharacters(),
        workspaceId ? fetchProjects(workspaceId) : Promise.resolve([]),
      ]);
      setCharacters(chars);
      setProjects(projs as Project[]);
      if (projs.length > 0 && !selectedProject) {
        setSelectedProject((projs[0] as Project).id);
      }
    } catch {
      setToast({ message: 'Failed to load roster', type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [workspaceId, selectedProject]);

  useEffect(() => { load(); }, [load]);

  // Load cast for selected project
  useEffect(() => {
    if (!selectedProject) return;
    fetchCast(selectedProject)
      .then(cast => setCastByProject(prev => ({ ...prev, [selectedProject]: cast })))
      .catch(() => {});
  }, [selectedProject]);

  const handleCreate = async (data: Parameters<typeof createCharacter>[0]) => {
    const created = await createCharacter(data);
    setCharacters(prev => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
    setShowModal(false);
    setToast({ message: `${created.name} added to roster`, type: 'success' });
  };

  const handleDelete = async (id: string) => {
    const char = characters.find(c => c.id === id);
    await deleteCharacter(id);
    setCharacters(prev => prev.filter(c => c.id !== id));
    setToast({ message: `${char?.name ?? 'Character'} removed`, type: 'success' });
  };

  const handleProfileUpdate = (updated: Character) => {
    setCharacters(prev => prev.map(c => c.id === updated.id ? updated : c));
    setProfileChar(updated);
  };

  // Drag-to-cast
  const handleDragStart = (char: Character) => setDragging(char);
  const handleDragEnd = () => setDragging(null);

  const handleDropOnCast = async () => {
    if (!dragging || !selectedProject) return;
    const alreadyCast = (castByProject[selectedProject] ?? []).some(c => c.character_id === dragging.id);
    if (alreadyCast) {
      setToast({ message: `${dragging.name} is already cast`, type: 'error' });
      setDragging(null);
      return;
    }
    try {
      const casting = await castCharacter(selectedProject, { character_id: dragging.id, role: castingRole });
      setCastByProject(prev => ({
        ...prev,
        [selectedProject]: [...(prev[selectedProject] ?? []), casting],
      }));
      setToast({ message: `${dragging.name} cast as ${castingRole}`, type: 'success' });
    } catch {
      setToast({ message: 'Failed to cast character', type: 'error' });
    }
    setDragging(null);
  };

  const handleRemoveCasting = async (castingId: string, charName: string) => {
    if (!selectedProject) return;
    await removeFromCast(selectedProject, castingId);
    setCastByProject(prev => ({
      ...prev,
      [selectedProject]: (prev[selectedProject] ?? []).filter(c => c.id !== castingId),
    }));
    setToast({ message: `${charName} removed from cast`, type: 'success' });
  };

  const currentCast = castByProject[selectedProject] ?? [];

  return (
    <main className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>Talent Roster</h1>
        <div className={styles.actions}>
          <button className={styles.primaryBtn} onClick={() => setShowModal(true)}>
            + Create Character
          </button>
        </div>
      </div>

      <div className={styles.layout}>
        {/* Left: character grid */}
        <section className={styles.rosterSection}>
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
              {characters.map(c => (
                <div
                  key={c.id}
                  draggable
                  onDragStart={() => handleDragStart(c)}
                  onDragEnd={handleDragEnd}
                  className={styles.draggable}
                  title="Drag to cast panel to assign to project"
                >
                  <CharacterCard
                    character={c}
                    onDelete={handleDelete}
                    onClick={() => setProfileChar(c)}
                  />
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Right: casting panel */}
        <aside className={styles.castPanel}>
          <div className={styles.castHeader}>
            <h2 className={styles.castTitle}>Cast</h2>
            {projects.length > 0 && (
              <select
                className={styles.projectSelect}
                value={selectedProject}
                onChange={e => setSelectedProject(e.target.value)}
              >
                {projects.map(p => (
                  <option key={p.id} value={p.id}>{p.title}</option>
                ))}
              </select>
            )}
          </div>

          <div className={styles.roleSelect}>
            <label className={styles.roleLabel}>Drop role:</label>
            <select
              className={styles.projectSelect}
              value={castingRole}
              onChange={e => setCastingRole(e.target.value as CastingRole)}
            >
              {(['lead', 'supporting', 'recurring', 'guest', 'cameo'] as CastingRole[]).map(r => (
                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
              ))}
            </select>
          </div>

          <div
            className={`${styles.dropZone} ${dragging ? styles.dropActive : ''}`}
            onDragOver={e => e.preventDefault()}
            onDrop={handleDropOnCast}
          >
            {dragging ? (
              <p className={styles.dropHint}>Drop to cast as <strong>{castingRole}</strong></p>
            ) : (
              <p className={styles.dropHint}>Drag a character here to cast them</p>
            )}
          </div>

          {currentCast.length === 0 ? (
            <p className={styles.empty} style={{ padding: '1rem' }}>No characters cast yet.</p>
          ) : (
            <ul className={styles.castList}>
              {currentCast.map(casting => (
                <li key={casting.id} className={styles.castItem}>
                  <div className={styles.castAvatar}>
                    {casting.character.name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)}
                  </div>
                  <div className={styles.castInfo}>
                    <span className={styles.castName}>{casting.character.name}</span>
                    <span className={styles.castRole}>{casting.role}</span>
                  </div>
                  <button
                    className={styles.castRemove}
                    onClick={() => handleRemoveCasting(casting.id, casting.character.name)}
                    aria-label="Remove from cast"
                  >×</button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>

      {showModal && (
        <CreateCharacterModal
          onConfirm={handleCreate}
          onCancel={() => setShowModal(false)}
        />
      )}

      {profileChar && (
        <CharacterProfile
          character={profileChar}
          onClose={() => setProfileChar(null)}
          onUpdate={handleProfileUpdate}
        />
      )}

      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
    </main>
  );
}
