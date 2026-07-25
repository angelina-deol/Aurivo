import { useEffect, useRef, useState } from "react";

interface WaveformPlayerProps {
  audioUrl: string;
  durationSeconds: number;
}

const BASE_BAR_COUNT = 200;

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Decodes the real audio file once (via Web Audio API's decodeAudioData)
 * and renders actual peak data on a canvas — not a decorative animation.
 * Playback uses a plain <audio> element so seeking/scrubbing is free;
 * the canvas is just the visual, click/drag on it seeks the <audio>.
 */
export function WaveformPlayer({ audioUrl, durationSeconds }: WaveformPlayerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [peaks, setPeaks] = useState<number[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [zoom, setZoom] = useState(1); // 1 = fit width, >1 = zoomed in (scrollable)

  // Decode once per audioUrl.
  useEffect(() => {
    let cancelled = false;
    setPeaks(null);
    setError(null);

    (async () => {
      try {
        const response = await fetch(audioUrl);
        const arrayBuffer = await response.arrayBuffer();
        const audioContext = new AudioContext();
        const decoded = await audioContext.decodeAudioData(arrayBuffer);
        if (cancelled) return;

        // Downmix to mono peaks: for each of BASE_BAR_COUNT buckets, take
        // the max absolute sample — a standard peak-waveform reduction,
        // cheap enough to do on the main thread for typical clip lengths
        // (seconds to a few minutes).
        const channelCount = decoded.numberOfChannels;
        const length = decoded.length;
        const samplesPerBar = Math.max(1, Math.floor(length / BASE_BAR_COUNT));
        const nextPeaks: number[] = [];

        for (let bar = 0; bar < BASE_BAR_COUNT; bar++) {
          const start = bar * samplesPerBar;
          const end = Math.min(start + samplesPerBar, length);
          let peak = 0;
          for (let ch = 0; ch < channelCount; ch++) {
            const data = decoded.getChannelData(ch);
            for (let i = start; i < end; i++) {
              const v = Math.abs(data[i]);
              if (v > peak) peak = v;
            }
          }
          nextPeaks.push(peak);
        }

        setPeaks(nextPeaks);
        audioContext.close();
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not decode audio");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [audioUrl]);

  // Draw peaks + playback position whenever either changes.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !peaks) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const barWidth = width / peaks.length;
    const progress = durationSeconds > 0 ? currentTime / durationSeconds : 0;
    const playedBars = Math.floor(progress * peaks.length);

    peaks.forEach((peak, i) => {
      const barHeight = Math.max(2, peak * height * 0.9);
      const x = i * barWidth;
      const y = (height - barHeight) / 2;
      ctx.fillStyle = i <= playedBars ? "#E8B330" : "#E5DFC8";
      ctx.fillRect(x, y, Math.max(1, barWidth - 1), barHeight);
    });
  }, [peaks, currentTime, durationSeconds]);

  function handleSeek(e: React.MouseEvent<HTMLCanvasElement>) {
    const audio = audioRef.current;
    const canvas = canvasRef.current;
    if (!audio || !canvas || !durationSeconds) return;
    const rect = canvas.getBoundingClientRect();
    const fraction = (e.clientX - rect.left) / rect.width;
    audio.currentTime = fraction * durationSeconds;
  }

  function togglePlay() {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
    } else {
      audio.play();
    }
  }

  return (
    <div>
      <audio
        ref={audioRef}
        src={audioUrl}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
        onEnded={() => setIsPlaying(false)}
      />

      {error && <p className="text-sm text-risk-danger">{error}</p>}

      {!peaks && !error && (
        <div className="h-24 flex items-center justify-center text-ink-faint text-sm">
          Decoding waveform…
        </div>
      )}

      {peaks && (
        <div ref={containerRef} className="overflow-x-auto">
          <canvas
            ref={canvasRef}
            width={800 * zoom}
            height={96}
            onClick={handleSeek}
            className="w-full cursor-pointer rounded-xl"
            style={{ width: `${100 * zoom}%`, height: "96px" }}
          />
        </div>
      )}

      <div className="flex items-center justify-between mt-3">
        <button
          onClick={togglePlay}
          disabled={!peaks}
          className="w-10 h-10 rounded-full bg-gold-500 text-ink flex items-center justify-center disabled:opacity-40 shrink-0"
          aria-label={isPlaying ? "Pause" : "Play"}
        >
          {isPlaying ? (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
              <rect x="2" y="1" width="4" height="12" />
              <rect x="8" y="1" width="4" height="12" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
              <path d="M2 1 L13 7 L2 13 Z" />
            </svg>
          )}
        </button>

        <p className="font-mono text-xs text-ink-faint">
          {formatTime(currentTime)} / {formatTime(durationSeconds)}
        </p>

        <div className="flex items-center gap-1">
          <button
            onClick={() => setZoom((z) => Math.max(1, z - 0.5))}
            disabled={zoom <= 1}
            className="w-7 h-7 rounded-full border border-ink/10 text-ink-muted text-sm disabled:opacity-30"
            aria-label="Zoom out"
          >
            −
          </button>
          <button
            onClick={() => setZoom((z) => Math.min(4, z + 0.5))}
            disabled={zoom >= 4}
            className="w-7 h-7 rounded-full border border-ink/10 text-ink-muted text-sm disabled:opacity-30"
            aria-label="Zoom in"
          >
            +
          </button>
        </div>
      </div>
    </div>
  );
}
