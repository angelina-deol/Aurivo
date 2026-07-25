interface ConfidenceGraphProps {
  prediction: "real" | "ai_generated" | string;
  confidence: number; // 0..1, the predicted class's probability
  fraudScore: number; // 0..100, probability the audio is AI-generated
}

const RADIUS = 54;
const STROKE = 14;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * A hand-built SVG donut rather than a charting library — this is a single
 * two-segment split (real % vs AI-generated %), which a full charting
 * dependency would be overkill for, and a custom arc keeps the report's
 * visual language (gold accent, warm cream, rounded) consistent with the
 * rest of the design system instead of a library's default look.
 */
export function ConfidenceGraph({ prediction, fraudScore }: ConfidenceGraphProps) {
  const aiPercent = Math.max(0, Math.min(100, fraudScore));
  const realPercent = 100 - aiPercent;
  const aiArcLength = (aiPercent / 100) * CIRCUMFERENCE;

  const isAiGenerated = prediction === "ai_generated";

  return (
    <div className="flex items-center gap-6">
      <svg width="140" height="140" viewBox="0 0 140 140" className="shrink-0">
        {/* Base ring: "real" portion */}
        <circle
          cx="70"
          cy="70"
          r={RADIUS}
          fill="none"
          stroke="#E5DFC8"
          strokeWidth={STROKE}
        />
        {/* AI-generated portion, drawn on top */}
        <circle
          cx="70"
          cy="70"
          r={RADIUS}
          fill="none"
          stroke={isAiGenerated ? "#C1432E" : "#E8B330"}
          strokeWidth={STROKE}
          strokeDasharray={`${aiArcLength} ${CIRCUMFERENCE - aiArcLength}`}
          strokeDashoffset={CIRCUMFERENCE / 4}
          strokeLinecap="round"
          transform="scale(-1, 1) translate(-140, 0)"
        />
        <text
          x="70"
          y="66"
          textAnchor="middle"
          className="font-display"
          fontSize="26"
          fontWeight="600"
          fill="#1C1B18"
        >
          {Math.round(aiPercent)}%
        </text>
        <text
          x="70"
          y="86"
          textAnchor="middle"
          fontSize="10"
          fill="#6F6A5C"
          className="font-mono"
        >
          fraud score
        </text>
      </svg>

      <dl className="space-y-2 font-mono text-sm">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-gold-500 inline-block" />
          <dt className="text-ink-muted">Real</dt>
          <dd className="text-ink font-medium">{Math.round(realPercent)}%</dd>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-risk-danger inline-block" />
          <dt className="text-ink-muted">AI Generated</dt>
          <dd className="text-ink font-medium">{Math.round(aiPercent)}%</dd>
        </div>
      </dl>
    </div>
  );
}
