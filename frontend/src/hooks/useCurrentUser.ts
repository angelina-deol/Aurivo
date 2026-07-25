import { useEffect, useState } from "react";

import { useAuthStore } from "@/hooks/useAuthStore";
import { authApi, UserResponse } from "@/services/api";

export function useCurrentUser() {
  const accessToken = useAuthStore((s) => s.accessToken);
  const clearTokens = useAuthStore((s) => s.clearTokens);
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(!!accessToken);

  useEffect(() => {
    if (!accessToken) {
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    authApi
      .me(accessToken)
      .then(setUser)
      .catch(() => {
        // Token expired/invalid — clear it so the UI falls back to signed-out state.
        clearTokens();
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [accessToken, clearTokens]);

  return { user, loading, isAuthenticated: !!accessToken };
}
