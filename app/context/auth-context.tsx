import { createContext, ReactNode, useContext, useState } from 'react';

export interface AuthUser {
  user_id: number;
  nickname: string;
  login_id: string;
  pregnancy_week: number | null;
  pregnancy_day?: number | null;
  pregnancy_entered_at?: string | null;
  due_date: string | null;
  allergy_info: string | null;
}

interface AuthContextValue {
  user: AuthUser | null;
  login: (userData: AuthUser) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);

  const login = (userData: AuthUser) => setUser(userData);
  const logout = () => setUser(null);

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
