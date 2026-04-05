import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

interface AuthState {
  accessToken: string | null;
  isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
  login: (accessToken: string, refreshToken: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = 'sc_access_token';
const REFRESH_KEY = 'sc_refresh_token';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(
    () => localStorage.getItem(TOKEN_KEY)
  );

  const login = useCallback((token: string, refreshToken: string) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(REFRESH_KEY, refreshToken);
    setAccessToken(token);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    setAccessToken(null);
  }, []);

  return (
    <AuthContext.Provider value={{ accessToken, isAuthenticated: !!accessToken, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
