import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { ConfidenceGraph } from "@/components/ConfidenceGraph";
import { SpectrogramView } from "@/components/SpectrogramView";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Waveform } from "@/components/ui/Waveform";
import { WaveformPlayer } from "@/components/WaveformPlayer";
import { useAuthStore } from "@/hooks/useAuthStore";
import { investigationsApi, InvestigationResponse } from "@/services/api";

const POLL_INTERVAL_MS = 2500;
// A real AASIST forward pass takes seconds, not minutes. If it's still
// "processing" after this long, something is actually stuck (crashed
// worker, hung task) rather than just slow — surface that honestly instead
// of polling in silence forever. This is an early UI hint only, shown
// while still polling; the backend's own authoritative cutoff (currently
// 360s, in backend/api/routes/investigations.py's
// STALE_PROCESSING_THRESHOLD_SECONDS) is what actually marks an
// investigation failed if the worker crashed mid-task — this just warns
// sooner than that, so the person isn't staring at silence the whole time.
const STUCK_THRESHOLD_MS = 60_000;

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
  const [seemsStuck, setSeemsStuck] = useState(false);
  const pollRef = useRef<number | null>(null);

  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [spectrogramUrl, setSpectrogramUrl] = useState<string | null>(null);
  const [mediaError, setMediaError] = useState<string | null>(null);

  useEffect(() => {
    if (!id || !accessToken) return;

    let cancelled = false;
    const startedPollingAt = Date.now();

    async function fetchOnce() {
      try {
        const result = await investigationsApi.get(accessToken!, id!);
        if (cancelled) return;
        setInvestigation(result);
        setLoading(false);

        const stillInFlight = result.status === "processing" || result.status === "awaiting_analysis";

        if (stillInFlight) {
          setSeemsStuck(Date.now() - startedPollingAt > STUCK_THRESHOLD_MS);
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

  // Fetch audio + spectrogram blobs once the investigation has settled
  // (any terminal-ish state with stored audio) — not while still
  // "processing", since the file is already there from upload but there's
  // no point re-fetching before the page needs it.
  useEffect(() => {
    if (!id || !accessToken || !investigation?.audio_metadata) return;
    const createdUrls: string[] = [];

    investigationsApi
      .audioBlobUrl(accessToken, id)
      .then((url) => {
        createdUrls.push(url);
        setAudioUrl(url);
      })
      .catch((err) => setMediaError(err instanceof Error ? err.message : "Could not load audio"));

    if (investigation.audio_metadata.has_spectrogram) {
      investigationsApi
        .spectrogramBlobUrl(accessToken, id)
        .then((url) => {
          if (url) {
            createdUrls.push(url);
            setSpectrogramUrl(url);
          }
        })
        .catch(() => {
          /* spectrogram is a nice-to-have; a failure here isn't worth surfacing as an error */
        });
    }

    return () => {
      createdUrls.forEach((url) => URL.revokeObjectURL(url));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, accessToken, investigation?.audio_metadata?.has_spectrogram]);

  return (
    <div className="min-h-screen bg-cream px-6 py-12 md:px-16">
      <div className="max-w-2xl mx-auto space-y-6">
        {loading && <p className="text-ink-muted">Loading…</p>}
        {error && <p className="text-risk-danger">{error}</p>}

        {investigation && (
          <>
            <Card>
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
                  {seemsStuck && (
                    <div className="mt-4 rounded-2xl bg-gold-50 border border-gold-100 p-4 text-sm text-ink-muted text-left">
                      This is taking much longer than a real analysis
                      normally does (a forward pass is usually seconds, not
                      minutes). It's likely stuck rather than just slow —
                      check the worker's logs for an error, or confirm a
                      worker is actually running (
                      <code className="font-mono text-xs">
                        docker compose ps
                      </code>
                      ).
                    </div>
                  )}
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
                <div className="py-4">
                  <p className="text-center font-mono text-xs uppercase tracking-widest text-ink-faint mb-1">
                    Voice authenticity
                  </p>
                  <p className="text-center font-display text-3xl font-semibold text-ink mb-6">
                    {investigation.prediction === "ai_generated" ? "AI Generated" : "Real"}
                  </p>

                  {investigation.confidence !== null && investigation.fraud_score !== null && (
                    <div className="flex justify-center mb-4">
                      <ConfidenceGraph
                        prediction={investigation.prediction ?? "real"}
                        confidence={investigation.confidence}
                        fraudScore={investigation.fraud_score}
                      />
                    </div>
                  )}

                  {investigation.processing_time_seconds !== null && (
                    <p className="text-center text-xs text-ink-faint mb-4">
                      Analyzed in {investigation.processing_time_seconds.toFixed(1)}s
                    </p>
                  )}

                  {investigation.ai_explanation && (
                    <div className="rounded-2xl bg-cream-100 p-4 mt-2">
                      <p className="font-mono text-xs uppercase tracking-widest text-ink-faint mb-2">
                        AI explanation
                      </p>
                      <p className="text-sm text-ink-muted leading-relaxed">
                        {investigation.ai_explanation}
                      </p>
                    </div>
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

            {mediaError && <p className="text-sm text-risk-danger">{mediaError}</p>}

            {audioUrl && investigation.audio_metadata && (
              <Card>
                <CardHeader>
                  <CardTitle>Waveform</CardTitle>
                </CardHeader>
                <WaveformPlayer
                  audioUrl={audioUrl}
                  durationSeconds={investigation.audio_metadata.duration_seconds}
                />
              </Card>
            )}

            {spectrogramUrl && investigation.audio_metadata && (
              <Card>
                <CardHeader>
                  <CardTitle>Spectrogram</CardTitle>
                </CardHeader>
                <SpectrogramView
                  imageUrl={spectrogramUrl}
                  durationSeconds={investigation.audio_metadata.duration_seconds}
                  sampleRate={investigation.audio_metadata.sample_rate}
                  attentionRegions={investigation.attention_regions}
                />
                {investigation.attention_regions && investigation.attention_regions.length > 0 && (
                  <p className="text-xs text-ink-faint mt-3 leading-relaxed">
                    The highlighted regions reflect the model's first-stage internal attention,
                    not a complete explanation of the final verdict — treat this as a hint about
                    where the model focused, not proof of what's there.
                  </p>
                )}
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}
