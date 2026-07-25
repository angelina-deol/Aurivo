import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuthStore } from "@/hooks/useAuthStore";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { authApi } from "@/services/api";

function initialsFor(name: string | null, email: string): string {
  if (name && name.trim()) {
    const parts = name.trim().split(/\s+/);
    return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
  }
  return email[0]?.toUpperCase() ?? "?";
}

export function ProfileIcon() {
  const { user, loading, isAuthenticated } = useCurrentUser();
  const accessToken = useAuthStore((s) => s.accessToken);
  const clearTokens = useAuthStore((s) => s.clearTokens);
  const [menuOpen, setMenuOpen] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);
  const navigate = useNavigate();

  if (!isAuthenticated) {
    return (
      <Link
        to="/login"
        className="text-sm font-medium text-ink-muted hover:text-ink transition-colors"
      >
        Sign in
      </Link>
    );
  }

  if (loading || !user) {
    return <div className="w-9 h-9 rounded-full bg-cream-200 animate-pulse" />;
  }

  async function handleLogout() {
    if (accessToken) {
      await authApi.logout(accessToken).catch(() => {});
    }
    clearTokens();
    setMenuOpen(false);
    navigate("/");
  }

  return (
    <div className="relative">
      <button
        onClick={() => setMenuOpen((o) => !o)}
        className="w-9 h-9 rounded-full overflow-hidden border border-ink/10 shadow-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        aria-label="Account menu"
      >
        {user.avatar_url && !imgFailed ? (
          <img
            src={user.avatar_url}
            alt=""
            className="w-full h-full object-cover"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gold-500 text-ink font-display font-semibold text-sm">
            {initialsFor(user.full_name, user.email)}
          </div>
        )}
      </button>

      {menuOpen && (
        <>
          {/* Click-away layer */}
          <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
          <div className="absolute right-0 mt-2 w-56 rounded-2xl bg-white shadow-soft-lg border border-ink/5 py-2 z-20">
            <div className="px-4 py-2 border-b border-ink/5">
              <p className="text-sm font-medium text-ink truncate">
                {user.full_name ?? user.email}
              </p>
              <p className="text-xs text-ink-faint truncate">{user.email}</p>
            </div>
            <button
              onClick={handleLogout}
              className="w-full text-left px-4 py-2 text-sm text-ink-muted hover:bg-cream-100 transition-colors"
            >
              Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}
