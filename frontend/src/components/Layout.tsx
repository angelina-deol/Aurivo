import { Link, Outlet } from "react-router-dom";

import { ProfileIcon } from "@/components/ProfileIcon";

export function Layout() {
  return (
    <div className="min-h-screen bg-cream">
      <header className="flex items-center justify-between px-6 py-4 md:px-16">
        <Link to="/" className="font-display text-lg font-semibold text-ink">
          Aurivo
        </Link>
        <ProfileIcon />
      </header>
      <Outlet />
    </div>
  );
}
