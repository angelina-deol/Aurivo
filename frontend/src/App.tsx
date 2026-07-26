import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";

import { Layout } from "@/components/Layout";
import { RequireAuth } from "@/components/RequireAuth";
import History from "@/pages/History";
import Home from "@/pages/Home";
import InvestigationDetail from "@/pages/InvestigationDetail";
import Login from "@/pages/Login";
import OAuthCallback from "@/pages/OAuthCallback";
import Record from "@/pages/Record";
import Register from "@/pages/Register";
import Upload from "@/pages/Upload";

// Recharts (and its d3 dependencies) only matter on this one page — code-split
// it out rather than shipping charting code to every route.
const Dashboard = lazy(() => import("@/pages/Dashboard"));

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/oauth/callback" element={<OAuthCallback />} />
        <Route
          path="/record"
          element={
            <RequireAuth>
              <Record />
            </RequireAuth>
          }
        />
        <Route
          path="/upload"
          element={
            <RequireAuth>
              <Upload />
            </RequireAuth>
          }
        />
        <Route
          path="/history"
          element={
            <RequireAuth>
              <History />
            </RequireAuth>
          }
        />
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <Suspense fallback={<div className="min-h-screen bg-cream px-6 py-12 md:px-16 text-ink-muted">Loading…</div>}>
                <Dashboard />
              </Suspense>
            </RequireAuth>
          }
        />
        <Route
          path="/investigations/:id"
          element={
            <RequireAuth>
              <InvestigationDetail />
            </RequireAuth>
          }
        />
      </Route>
    </Routes>
  );
}
