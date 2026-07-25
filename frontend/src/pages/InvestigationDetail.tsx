import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { useAuthStore } from "@/hooks/useAuthStore";
import { investigationsApi, InvestigationResponse } from "@/services/api";

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function InvestigationDetail() {
  const { id } = useParams<{ id: string }>();
  const accessToken = useAuthStore((s) => s.accessToken);

  const [investigation, setInvestigation] = useState<InvestigationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id || !accessToken) return;
    investigationsApi
      .get(accessToken, id)
      .then(setInvestigation)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load investigation"))
      .finally(() => setLoading(false));
  }, [id, accessToken]);

  return (
    <div className="min-h-screen bg-cream px-6 py-12 md:px-16">
      <div className="max-w-2xl mx-auto">
        {loading && <p className="text-ink-muted">Loading…</p>}
        {error && <p className="text-risk-danger">{error}</p>}

        {investigation && (
          <>
            <Card className="mb-6">
              <CardHeader>
                <CardTitle>{investigation.filename}</CardTitle>
              </CardHeader>

              {investigation.status === "awaiting_analysis" && (
                <div className="rounded-2xl bg-gold-50 border border-gold-100 p-4 text-sm text-ink-muted">
                  Upload received. Fraud/deepfake analysis isn't running yet —
                  the AASIST inference pipeline comes online in Phase 3. This
                  file and its metadata are safely stored in the meantime.
                </div>
              )}

              {investigation.status === "complete" && (
                <div className="text-center py-6">
                  <p className="font-mono text-xs uppercase tracking-widest text-ink-faint mb-2">
                    Voice authenticity
                  </p>
                  <p className="font-display text-4xl font-semibold text-ink mb-1">
                    {investigation.prediction === "ai_generated" ? "AI Generated" : "Real"}
                  </p>
                  <p className="font-mono text-2xl text-gold-600">
                    {investigation.confidence !== null
                      ? `${Math.round(investigation.confidence * 100)}%`
                      : "—"}
                  </p>
                </div>
              )}
            </Card>

            {investigation.audio_metadata && (
              <Card>
                <CardHeader>
                  <CardTitle>Audio metadata</CardTitle>
                </CardHeader>
                <dl className="grid grid-cols-2 gap-4 font-mono text-sm">
                  <div>
                    <dt className="text-ink-faint">Duration</dt>
                    <dd className="text-ink">
                      {formatDuration(investigation.audio_metadata.duration_seconds)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-ink-faint">Sample rate</dt>
                    <dd className="text-ink">{investigation.audio_metadata.sample_rate} Hz</dd>
                  </div>
                  <div>
                    <dt className="text-ink-faint">Channels</dt>
                    <dd className="text-ink">{investigation.audio_metadata.channels}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-faint">File size</dt>
                    <dd className="text-ink">
                      {(investigation.audio_metadata.file_size_bytes / 1024 / 1024).toFixed(2)} MB
                    </dd>
                  </div>
                </dl>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}
