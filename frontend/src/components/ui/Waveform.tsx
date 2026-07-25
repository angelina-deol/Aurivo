import clsx from "clsx";

interface WaveformProps {
  bars?: number;
  animated?: boolean;
  className?: string;
  /**
   * Live amplitude levels (0–1) from useAudioRecorder. When provided, bars
   * reflect actual mic input instead of the decorative idle animation —
   * used on the Recording screen.
   */
  levels?: number[];
}

/**
 * Bar waveform used on Home (decorative) and Recording (live) screens.
 */
export function Waveform({ bars = 32, animated = true, className, levels }: WaveformProps) {
  const heights = levels
    ? levels.map((l) => Math.max(8, Math.min(100, l * 100)))
    : Array.from({ length: bars }, (_, i) => 20 + ((i * 37) % 80));

  return (
    <div className={clsx("flex items-center gap-1 h-16", className)}>
      {heights.map((h, i) => (
        <div
          key={i}
          className={clsx(
            "w-1 rounded-full bg-gold-500 reduce-motion",
            !levels && animated && "animate-wave"
          )}
          style={{
            height: `${h}%`,
            transition: levels ? "height 60ms linear" : undefined,
            animationDelay: !levels ? `${i * 0.05}s` : undefined,
          }}
        />
      ))}
    </div>
  );
}
