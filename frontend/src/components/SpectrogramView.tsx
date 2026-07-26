import { useRef, useState } from "react";

import { AttentionRegion } from "@/services/api";

interface SpectrogramViewProps {
  imageUrl: string;
  durationSeconds: number;
  sampleRate: number;
  attentionRegions?: AttentionRegion[] | null;
}

/**
 * Displays the backend-generated spectrogram PNG. "Zoom" is literal image
 * scaling (CSS transform) rather than re-fetching at different
 * resolutions — the backend renders one fixed-resolution image per
 * investigation, which is enough detail for report-viewing purposes.
 * Hover readout is approximate: it maps cursor position to time (using the
 * known clip duration) and frequency (using the Nyquist frequency, sr/2,
 * since that's the full range scipy.signal.spectrogram covers) rather than
 * requiring the backend to embed exact axis metadata.
 *
 * attentionRegions (Phase 6) draws translucent vertical bands over the
 * time ranges AASIST's internal attention weighted most heavily — see
 * ml/inference/aasist_wrapper.py for exactly what this does and doesn't
 * mean (it's the model's first-stage temporal attention, not a full
 * attribution of the final verdict).
 */
export function SpectrogramView({
  imageUrl,
  durationSeconds,
  sampleRate,
  attentionRegions,
}: SpectrogramViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [hover, setHover] = useState<{ time: number; freq: number; x: number; y: number } | null>(
    null
  );

  const nyquist = sampleRate / 2;

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const xFraction = (e.clientX - rect.left) / rect.width;
    const yFraction = (e.clientY - rect.top) / rect.height;
    setHover({
      time: xFraction * durationSeconds,
      freq: (1 - yFraction) * nyquist, // image y=0 is top (high freq), matplotlib plots freq increasing upward
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  }

  return (
    <div>
      <div
        ref={containerRef}
        className="relative overflow-auto rounded-xl border border-ink/5"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHover(null)}
      >
        <img
          src={imageUrl}
          alt="Spectrogram"
          style={{ width: `${100 * zoom}%`, display: "block" }}
          draggable={false}
        />

        {attentionRegions?.map((region, i) => {
          if (durationSeconds <= 0) return null;
          const leftPct = (region.start / durationSeconds) * 100;
          const widthPct = ((region.end - region.start) / durationSeconds) * 100;
          return (
            <div
              key={i}
              className="absolute top-0 bottom-0 pointer-events-none"
              style={{
                left: `${leftPct}%`,
                width: `${Math.max(widthPct, 0.5)}%`,
                backgroundColor: "rgba(232, 179, 48, 0.35)",
                opacity: 0.4 + region.salience * 0.6,
              }}
            />
          );
        })}

        {hover && (
          <div
            className="absolute pointer-events-none bg-ink text-cream text-xs font-mono rounded px-2 py-1"
            style={{ left: hover.x + 12, top: hover.y - 8 }}
          >
            {hover.time.toFixed(1)}s · {Math.round(hover.freq)} Hz
          </div>
        )}
      </div>

      {attentionRegions && attentionRegions.length > 0 && (
        <p className="text-xs text-ink-faint mt-2">
          Gold bands show where the model's attention was most concentrated — see the report
          notes for what this does and doesn't mean.
        </p>
      )}

      <div className="flex items-center justify-end gap-1 mt-2">
        <button
          onClick={() => setZoom((z) => Math.max(1, z - 0.5))}
          disabled={zoom <= 1}
          className="w-7 h-7 rounded-full border border-ink/10 text-ink-muted text-sm disabled:opacity-30"
          aria-label="Zoom out"
        >
          −
        </button>
        <button
          onClick={() => setZoom((z) => Math.min(3, z + 0.5))}
          disabled={zoom >= 3}
          className="w-7 h-7 rounded-full border border-ink/10 text-ink-muted text-sm disabled:opacity-30"
          aria-label="Zoom in"
        >
          +
        </button>
      </div>
    </div>
  );
}
