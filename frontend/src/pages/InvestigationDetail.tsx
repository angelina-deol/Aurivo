import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Waveform } from "@/components/ui/Waveform";
import { useAuthStore } from "@/hooks/useAuthStore";
import { investigationsApi, InvestigationResponse } from "@/services/api";

const POLL_INTERVAL_MS = 2500;

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
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    if (!id || !accessToken) return;

    let cancelled = false;

    async function fetchOnce() {
      try {
        const result = await investigationsApi.get(accessToken!, id!);
        if (cancelled) return;
        setInvestigation(result);
        setLoading(false);

        // Keep polling while analysis is in flight; a real AASIST forward
        // pass typically finishes in a few seconds, but this covers queueing
        // delay too if the worker is busy with other investigations.
        if (result.status === "processing" || result.status === "awaiting_analysis") {
          pollRef.current = window.setTimeout(fetchOnce, POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Could not load investigation");
        setLoading(false);
      }
    }

    fetchOnce();

    return () => {
      cancelled = true;
      if (pollRef.current) window.clearTimeout(pollRef.current);
    };
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

              {(investigation.status === "processing" ||
                investigation.status === "awaiting_analysis") && (
                <div className="text-center py-6">
                  <Waveform className="justify-center mb-4" />
                  <p className="text-ink-muted text-sm">
                    Running AASIST analysis on this recording…
                  </p>
                </div>
              )}

              {investigation.status === "failed" && (
                <div className="rounded-2xl bg-red-50 border border-risk-danger/20 p-4 text-sm text-risk-danger">
                  Analysis failed for this recording. This usually means the
                  inference worker isn't running, or the AASIST model/weights
                  aren't in place on it yet — check the worker's logs.
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
                  <p className="font-mono text-2xl text-gold-600 mb-1">
                    {investigation.confidence !== null
                      ? `${Math.round(investigation.confidence * 100)}%`
                      : "—"}
                  </p>
                  {investigation.fraud_score !== null && (
                    <p className="text-sm text-ink-muted">
                      Fraud score: {Math.round(investigation.fraud_score)} / 100
                    </p>
                  )}
                  {investigation.processing_time_seconds !== null && (
                    <p className="text-xs text-ink-faint mt-2">
                      Analyzed in {investigation.processing_time_seconds.toFixed(1)}s
                    </p>
                  )}
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
