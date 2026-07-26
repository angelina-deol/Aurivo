import { Link, Outlet } from "react-router-dom";

import { ProfileIcon } from "@/components/ProfileIcon";
import { useAuthStore } from "@/hooks/useAuthStore";

export function Layout() {
  const isAuthenticated = !!useAuthStore((s) => s.accessToken);

  return (
    <div className="min-h-screen bg-cream">
      <header className="flex items-center justify-between px-6 py-4 md:px-16">
        <div className="flex items-center gap-8">
          <Link to="/" className="font-display text-lg font-semibold text-ink">
            Aurivo
          </Link>
          {isAuthenticated && (
            <nav className="hidden sm:flex items-center gap-6 text-sm font-medium text-ink-muted">
              <Link to="/dashboard" className="hover:text-ink transition-colors">
                Dashboard
              </Link>
              <Link to="/history" className="hover:text-ink transition-colors">
                History
              </Link>
            </nav>
          )}
        </div>
        <ProfileIcon />
      </header>
      <Outlet />
    </div>
  );
}
