import type { Character } from '../api/characters';
import { ROLE_LABELS } from '../api/characters';
import styles from './CharacterCard.module.css';

interface Props {
  character: Character;
  onDelete?: (id: string) => void;
}

function initials(name: string) {
  return name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

export function CharacterCard({ character, onDelete }: Props) {
  return (
    <div className={styles.card}>
      <div className={styles.avatar}>{initials(character.name)}</div>
      <div className={styles.info}>
        <p className={styles.name}>{character.name}</p>
        <span className={`${styles.badge} ${styles[`role_${character.role_type}`]}`}>
          {ROLE_LABELS[character.role_type]}
        </span>
        {character.age != null && (
          <span className={styles.meta}>Age {character.age}</span>
        )}
      </div>
      {onDelete && (
        <button
          className={styles.deleteBtn}
          onClick={() => onDelete(character.id)}
          aria-label={`Delete ${character.name}`}
          title="Delete"
        >
          ×
        </button>
      )}
    </div>
  );
}
