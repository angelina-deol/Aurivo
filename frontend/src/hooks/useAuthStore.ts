import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  setTokens: (access: string, refresh: string) => void;
  clearTokens: () => void;
}

// Persisted to localStorage so refreshing the page doesn't silently log
// you out — important once there's a profile icon meant to reflect login
// state at a glance. (A future hardening pass would move to httpOnly
// cookies; localStorage is vulnerable to XSS reading the token. Acceptable
// for this stage, worth revisiting before production.)
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      setTokens: (access, refresh) => set({ accessToken: access, refreshToken: refresh }),
      clearTokens: () => set({ accessToken: null, refreshToken: null }),
    }),
    { name: "aurivo-auth" }
  )
);
