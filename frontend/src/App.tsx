import { Route, Routes } from "react-router-dom";

import { Layout } from "@/components/Layout";
import { RequireAuth } from "@/components/RequireAuth";
import Home from "@/pages/Home";
import InvestigationDetail from "@/pages/InvestigationDetail";
import Login from "@/pages/Login";
import OAuthCallback from "@/pages/OAuthCallback";
import Record from "@/pages/Record";
import Register from "@/pages/Register";
import Upload from "@/pages/Upload";

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
