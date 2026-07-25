/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm, cream-toned base — matches the reference UI rather than the
        // generic dark-mode SOC-dashboard look. Trust reads as warm here,
        // not cold.
        cream: {
          DEFAULT: "#FBF3E1",
          50: "#FFFDF8",
          100: "#FBF3E1",
          200: "#F5E8C8",
        },
        gold: {
          DEFAULT: "#E8B330",
          50: "#FCF0D4",
          100: "#F7DFA0",
          400: "#EFC252",
          500: "#E8B330",
          600: "#C99420",
          700: "#8F6A16",
        },
        ink: {
          DEFAULT: "#1C1B18",
          muted: "#6F6A5C",
          faint: "#A7A18C",
        },
        risk: {
          safe: "#3E8A57",
          caution: "#D98A2B",
          danger: "#C1432E",
        },
      },
      fontFamily: {
        // Display face: used sparingly for hero numbers/headlines (the "94%"
        // confidence score, screen titles).
        display: ["'Instrument Sans'", "ui-sans-serif", "system-ui", "sans-serif"],
        // Body: everything else.
        sans: ["'Inter'", "ui-sans-serif", "system-ui", "sans-serif"],
        // Data face: fraud scores, timestamps, waveform readouts — gives the
        // "forensic report" feel a hint of instrumentation without going
        // full terminal/hacker aesthetic.
        mono: ["'IBM Plex Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
        "4xl": "2rem",
      },
      boxShadow: {
        soft: "0 2px 8px rgba(28, 27, 24, 0.04), 0 8px 24px rgba(28, 27, 24, 0.06)",
        "soft-lg": "0 4px 16px rgba(28, 27, 24, 0.05), 0 16px 40px rgba(28, 27, 24, 0.08)",
      },
      keyframes: {
        wave: {
          "0%, 100%": { transform: "scaleY(0.4)" },
          "50%": { transform: "scaleY(1)" },
        },
      },
      animation: {
        wave: "wave 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
