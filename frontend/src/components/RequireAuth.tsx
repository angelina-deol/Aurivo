import { Navigate } from "react-router-dom";

import { useAuthStore } from "@/hooks/useAuthStore";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken);

  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
