/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        panel: {
          950: "#0c0e10",
          900: "#14171a",
          850: "#191d20",
          800: "#20252a",
          700: "#2b3138",
          600: "#3a424b",
        },
        signal: {
          copper: "#e8a33d",
          copperdim: "#8a651f",
          live: "#4fd1a5",
          dark: "#e85d4c",
          unknown: "#6b7684",
          cyan: "#5ec3d6",
        },
      },
      fontFamily: {
        mono: ["'IBM Plex Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
        sans: ["'IBM Plex Sans'", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
