import { useRef, useState } from "react";

interface SpectrogramViewProps {
  imageUrl: string;
  durationSeconds: number;
  sampleRate: number;
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
 */
export function SpectrogramView({ imageUrl, durationSeconds, sampleRate }: SpectrogramViewProps) {
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
        {hover && (
          <div
            className="absolute pointer-events-none bg-ink text-cream text-xs font-mono rounded px-2 py-1"
            style={{ left: hover.x + 12, top: hover.y - 8 }}
          >
            {hover.time.toFixed(1)}s · {Math.round(hover.freq)} Hz
          </div>
        )}
      </div>

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
