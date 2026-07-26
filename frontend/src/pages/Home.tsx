import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Waveform } from "@/components/ui/Waveform";
import { useAuthStore } from "@/hooks/useAuthStore";
import { investigationsApi, InvestigationResponse } from "@/services/api";

export default function Home() {
  const navigate = useNavigate();
  const accessToken = useAuthStore((s) => s.accessToken);
  const [recent, setRecent] = useState<InvestigationResponse[]>([]);

  useEffect(() => {
    if (!accessToken) return;
    investigationsApi
      .list(accessToken, { limit: 5, offset: 0 })
      .then((res) => setRecent(res.items))
      .catch(() => setRecent([]));
  }, [accessToken]);

  return (
    <div className="min-h-screen bg-cream px-6 py-12 md:px-16">
      <header className="max-w-3xl mx-auto text-center">
        <p className="font-mono text-xs uppercase tracking-widest text-ink-faint mb-4">
          Aurivo · Voice Intelligence
        </p>
        <h1 className="font-display text-4xl md:text-5xl font-semibold text-ink mb-6">
          Say anything to Aurivo.
        </h1>
        <p className="text-ink-muted text-lg mb-10">
          Upload or record audio to check it for AI-generated speech, cloned
          voices, and manipulated recordings — with a full explainable report.
        </p>

        <Card className="max-w-xl mx-auto mb-10">
          <Waveform className="justify-center mb-6" />
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Button variant="primary" size="lg" onClick={() => navigate("/upload")}>
              Upload Recording
            </Button>
            <Button variant="secondary" size="lg" onClick={() => navigate("/record")}>
              Record Live Audio
            </Button>
          </div>
        </Card>
      </header>

      <section className="max-w-3xl mx-auto mt-16">
        <CardHeader className="mb-6">
          <CardTitle>Recent investigations</CardTitle>
        </CardHeader>

        {!accessToken && (
          <Card className="text-center text-ink-muted">
            <Link to="/login" className="text-gold-600 font-medium">
              Sign in
            </Link>{" "}
            to see your investigation history.
          </Card>
        )}

        {accessToken && recent.length === 0 && (
          <Card className="text-center text-ink-muted">
            No investigations yet. Upload or record your first recording to
            get started.
          </Card>
        )}

        {accessToken && recent.length > 0 && (
          <div className="space-y-3">
            {recent.map((inv) => (
              <Link key={inv.id} to={`/investigations/${inv.id}`}>
                <Card className="flex items-center justify-between hover:shadow-soft-lg transition-shadow">
                  <span className="font-medium text-ink">{inv.filename}</span>
                  <span className="font-mono text-xs uppercase tracking-widest text-ink-faint">
                    {inv.status.replace("_", " ")}
                  </span>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
