/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        panel: {
          950: "#f8f9fb",
          900: "#f1f3f6",
          850: "#eaedf1",
          800: "#e2e6eb",
          700: "#d1d6de",
          600: "#bbc2cc",
        },
        signal: {
          copper: "#c87a1a",
          copperdim: "#a5650e",
          live: "#16a37a",
          dark: "#dc3545",
          unknown: "#8693a1",
          cyan: "#0e8fa0",
        },
      },
      fontFamily: {
        mono: ["'IBM Plex Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
        sans: ["'IBM Plex Sans'", "system-ui", "sans-serif"],
      },
      animation: {
        'fade-in': 'tab-fade-in 0.25s ease-out',
        'slide-in': 'drawer-slide-in 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        'pulse-slow': 'subtle-pulse 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
