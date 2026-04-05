import { renderHook, act } from '@testing-library/react';
import { AuthProvider, useAuth } from '../context/AuthContext';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
);

beforeEach(() => localStorage.clear());

test('starts unauthenticated when no token in storage', () => {
  const { result } = renderHook(() => useAuth(), { wrapper });
  expect(result.current.isAuthenticated).toBe(false);
  expect(result.current.accessToken).toBeNull();
});

test('login sets token and marks authenticated', () => {
  const { result } = renderHook(() => useAuth(), { wrapper });
  act(() => result.current.login('access-abc', 'refresh-xyz'));
  expect(result.current.isAuthenticated).toBe(true);
  expect(result.current.accessToken).toBe('access-abc');
  expect(localStorage.getItem('sc_access_token')).toBe('access-abc');
  expect(localStorage.getItem('sc_refresh_token')).toBe('refresh-xyz');
});

test('logout clears token and marks unauthenticated', () => {
  const { result } = renderHook(() => useAuth(), { wrapper });
  act(() => result.current.login('access-abc', 'refresh-xyz'));
  act(() => result.current.logout());
  expect(result.current.isAuthenticated).toBe(false);
  expect(result.current.accessToken).toBeNull();
  expect(localStorage.getItem('sc_access_token')).toBeNull();
});

test('restores session from localStorage on mount', () => {
  localStorage.setItem('sc_access_token', 'persisted-token');
  const { result } = renderHook(() => useAuth(), { wrapper });
  expect(result.current.isAuthenticated).toBe(true);
  expect(result.current.accessToken).toBe('persisted-token');
});
