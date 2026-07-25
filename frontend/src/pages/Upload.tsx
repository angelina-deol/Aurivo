import { DragEvent, useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useAuthStore } from "@/hooks/useAuthStore";
import { investigationsApi } from "@/services/api";

const ACCEPTED_EXTENSIONS = [".wav", ".flac", ".mp3"];

interface PreviewMetadata {
  durationSeconds: number;
  sampleRate: number;
  channels: number;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function isAcceptedFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
}

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [metadata, setMetadata] = useState<PreviewMetadata | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const accessToken = useAuthStore((s) => s.accessToken);
  const navigate = useNavigate();

  const handleFile = useCallback(async (candidate: File) => {
    setError(null);
    setMetadata(null);

    if (!isAcceptedFile(candidate)) {
      setError(`Unsupported file type. Please use ${ACCEPTED_EXTENSIONS.join(", ")}.`);
      return;
    }

    setFile(candidate);

    // Client-side preview only — decodes a copy of the bytes to read
    // duration/sample rate/channels for display. The original File object
    // (not this decoded copy) is what actually gets uploaded, since the
    // backend re-derives its own metadata from the raw bytes anyway.
    try {
      const arrayBuffer = await candidate.arrayBuffer();
      const audioContext = new AudioContext();
      const decoded = await audioContext.decodeAudioData(arrayBuffer.slice(0));
      setMetadata({
        durationSeconds: decoded.duration,
        sampleRate: decoded.sampleRate,
        channels: decoded.numberOfChannels,
      });
      audioContext.close();
    } catch {
      // Preview is best-effort — if decoding fails client-side (e.g. an
      // unusual MP3 encoding some browsers can't decode), we still let the
      // upload proceed and let the backend be the source of truth.
      setMetadata(null);
    }
  }, []);

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) handleFile(dropped);
  }

  async function handleSubmit() {
    if (!file) return;
    if (!accessToken) {
      navigate("/login");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const investigation = await investigationsApi.analyze(accessToken, file);
      navigate(`/investigations/${investigation.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-cream flex items-center justify-center px-6">
      <Card className="w-full max-w-lg">
        <p className="font-mono text-xs uppercase tracking-widest text-ink-faint mb-2">
          Upload recording
        </p>
        <h1 className="font-display text-2xl font-semibold text-ink mb-6">
          Upload a recording
        </h1>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          className={`rounded-2xl border-2 border-dashed p-10 text-center transition-colors ${
            isDragging ? "border-gold-500 bg-gold-50" : "border-ink/15"
          }`}
        >
          <p className="text-ink-muted mb-4">
            Drag and drop a WAV, FLAC, or MP3 file here, or
          </p>
          <label className="inline-block">
            <input
              type="file"
              accept=".wav,.flac,.mp3,audio/wav,audio/flac,audio/mpeg"
              className="hidden"
              onChange={(e) => {
                const selected = e.target.files?.[0];
                if (selected) handleFile(selected);
              }}
            />
            <span className="cursor-pointer inline-block px-6 py-3 rounded-2xl bg-gold-500 text-ink font-medium hover:bg-gold-600 transition-colors">
              Choose file
            </span>
          </label>
        </div>

        {file && (
          <div className="mt-6 rounded-2xl bg-cream-100 p-5 space-y-1 font-mono text-sm">
            <p className="text-ink">{file.name}</p>
            <p className="text-ink-muted">{formatBytes(file.size)}</p>
            {metadata && (
              <>
                <p className="text-ink-muted">
                  Duration: {formatDuration(metadata.durationSeconds)}
                </p>
                <p className="text-ink-muted">Sample rate: {metadata.sampleRate} Hz</p>
                <p className="text-ink-muted">Channels: {metadata.channels}</p>
              </>
            )}
          </div>
        )}

        {error && <p className="text-sm text-risk-danger mt-4">{error}</p>}

        <Button
          variant="primary"
          size="lg"
          className="w-full mt-6"
          disabled={!file || submitting}
          onClick={handleSubmit}
        >
          {submitting ? "Uploading…" : "Analyze recording"}
        </Button>
      </Card>
    </div>
  );
}
