import { create } from "zustand";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  setTokens: (access: string, refresh: string) => void;
  clearTokens: () => void;
}

// In-memory only for now — swapped for httpOnly cookies or secure storage
// once the auth flow is hardened past this Phase 1 skeleton.
export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  refreshToken: null,
  setTokens: (access, refresh) => set({ accessToken: access, refreshToken: refresh }),
  clearTokens: () => set({ accessToken: null, refreshToken: null }),
}));
