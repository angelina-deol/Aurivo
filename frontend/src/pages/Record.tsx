import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Waveform } from "@/components/ui/Waveform";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { useAuthStore } from "@/hooks/useAuthStore";
import { investigationsApi } from "@/services/api";

function formatTimer(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export default function Record() {
  const { status, elapsedSeconds, levels, error, start, pause, resume, stop, cancel } =
    useAudioRecorder();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const accessToken = useAuthStore((s) => s.accessToken);
  const navigate = useNavigate();

  async function handleStop() {
    const wavBlob = stop();
    if (!accessToken) {
      navigate("/login");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const file = new File([wavBlob], `recording-${Date.now()}.wav`, { type: "audio/wav" });
      const investigation = await investigationsApi.analyze(accessToken, file);
      navigate(`/investigations/${investigation.id}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-cream flex items-center justify-center px-6">
      <Card className="w-full max-w-lg text-center">
        <p className="font-mono text-xs uppercase tracking-widest text-ink-faint mb-2">
          Record live audio
        </p>
        <h1 className="font-display text-2xl font-semibold text-ink mb-8">
          {status === "recording" ? "Listening…" : status === "paused" ? "Paused" : "Ready?"}
        </h1>

        <Waveform levels={status !== "idle" ? levels : undefined} className="justify-center mb-6" />

        <p className="font-mono text-3xl text-ink mb-8">{formatTimer(elapsedSeconds)}</p>

        {(error || submitError) && (
          <p className="text-sm text-risk-danger mb-4">{error ?? submitError}</p>
        )}

        <div className="flex flex-wrap gap-3 justify-center">
          {status === "idle" && (
            <Button variant="primary" size="lg" onClick={start}>
              Start recording
            </Button>
          )}

          {status === "recording" && (
            <>
              <Button variant="secondary" onClick={pause}>
                Pause
              </Button>
              <Button variant="primary" onClick={handleStop} disabled={submitting}>
                {submitting ? "Uploading…" : "Stop & analyze"}
              </Button>
              <Button variant="ghost" onClick={cancel}>
                Cancel
              </Button>
            </>
          )}

          {status === "paused" && (
            <>
              <Button variant="secondary" onClick={resume}>
                Resume
              </Button>
              <Button variant="primary" onClick={handleStop} disabled={submitting}>
                {submitting ? "Uploading…" : "Stop & analyze"}
              </Button>
              <Button variant="ghost" onClick={cancel}>
                Cancel
              </Button>
            </>
          )}

          {status === "error" && (
            <Button variant="primary" onClick={start}>
              Try again
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
