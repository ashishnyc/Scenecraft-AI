import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Talent from '../pages/Talent';
import type { Character } from '../api/characters';
import { ROLE_LABELS } from '../api/characters';

vi.mock('../api/characters', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/characters')>();
  return {
    ...original,
    fetchCharacters: vi.fn(),
    createCharacter: vi.fn(),
    deleteCharacter: vi.fn(),
  };
});

import { fetchCharacters, createCharacter, deleteCharacter } from '../api/characters';

const mockCharacter = (overrides: Partial<Character> = {}): Character => ({
  id: 'char-1',
  account_id: 'user-1',
  name: 'Dr. Elena Voss',
  role_type: 'lead',
  personality_prompt: null,
  backstory: null,
  age: 35,
  lora_model_url: null,
  voice_profile_id: null,
  ...overrides,
});

function renderTalent() {
  return render(<MemoryRouter><Talent /></MemoryRouter>);
}

describe('Talent page — empty state', () => {
  beforeEach(() => {
    vi.mocked(fetchCharacters).mockResolvedValue([]);
  });

  it('shows empty state when no characters', async () => {
    renderTalent();
    await waitFor(() => expect(screen.getByText(/no characters yet/i)).toBeInTheDocument());
  });

  it('has Create Character button', async () => {
    renderTalent();
    await waitFor(() => {
      const btns = screen.getAllByRole('button', { name: /create character/i });
      expect(btns.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe('Talent page — with characters', () => {
  const characters = [
    mockCharacter({ id: 'c1', name: 'Elena', role_type: 'lead' }),
    mockCharacter({ id: 'c2', name: 'Marcus', role_type: 'villain' }),
  ];

  beforeEach(() => {
    vi.mocked(fetchCharacters).mockResolvedValue(characters);
  });

  it('renders character names', async () => {
    renderTalent();
    await waitFor(() => {
      expect(screen.getByText('Elena')).toBeInTheDocument();
      expect(screen.getByText('Marcus')).toBeInTheDocument();
    });
  });

  it('renders role badges', async () => {
    renderTalent();
    await waitFor(() => {
      expect(screen.getByText(ROLE_LABELS['lead'])).toBeInTheDocument();
      expect(screen.getByText(ROLE_LABELS['villain'])).toBeInTheDocument();
    });
  });
});

describe('Create character flow', () => {
  beforeEach(() => {
    vi.mocked(fetchCharacters).mockResolvedValue([]);
    vi.mocked(createCharacter).mockResolvedValue(
      mockCharacter({ id: 'new-1', name: 'Aria', role_type: 'supporting' })
    );
  });

  it('opens modal on button click', async () => {
    renderTalent();
    await waitFor(() => screen.getAllByRole('button', { name: /create character/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /create character/i })[0]);
    expect(screen.getByText('Create Character')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/elena/i)).toBeInTheDocument();
  });

  it('adds character to list after creation', async () => {
    renderTalent();
    await waitFor(() => screen.getAllByRole('button', { name: /create character/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /create character/i })[0]);

    fireEvent.change(screen.getByPlaceholderText(/elena/i), { target: { value: 'Aria' } });
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => expect(screen.getByText('Aria')).toBeInTheDocument());
    expect(createCharacter).toHaveBeenCalledWith(expect.objectContaining({ name: 'Aria' }));
  });
});

describe('ROLE_LABELS', () => {
  it('has a label for every role type', () => {
    const roles = ['lead', 'supporting', 'recurring', 'narrator', 'villain'] as const;
    roles.forEach((r) => expect(ROLE_LABELS[r]).toBeTruthy());
  });
});
