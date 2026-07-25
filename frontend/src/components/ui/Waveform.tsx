import clsx from "clsx";

interface WaveformProps {
  bars?: number;
  animated?: boolean;
  className?: string;
}

/**
 * Simple animated bar waveform used on Home / Recording screens.
 * Real waveform data (from actual audio) replaces the randomized heights
 * once the recording/upload pipeline lands in Phase 2.
 */
export function Waveform({ bars = 32, animated = true, className }: WaveformProps) {
  const heights = Array.from({ length: bars }, (_, i) => 20 + ((i * 37) % 80));

  return (
    <div className={clsx("flex items-center gap-1 h-16", className)}>
      {heights.map((h, i) => (
        <div
          key={i}
          className={clsx(
            "w-1 rounded-full bg-gold-500 reduce-motion",
            animated && "animate-wave"
          )}
          style={{
            height: `${h}%`,
            animationDelay: `${i * 0.05}s`,
          }}
        />
      ))}
    </div>
  );
}
