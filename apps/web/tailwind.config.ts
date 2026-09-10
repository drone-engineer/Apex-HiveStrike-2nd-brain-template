import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        hive: {
          bg: "#0b1220",
          panel: "#121a2b",
          line: "#243049",
          text: "#e8eefc",
          muted: "#9aa8c7",
          accent: "#f5a524",
          ok: "#3dd68c",
          warn: "#f5c542",
          crit: "#ff6b6b",
        },
      },
    },
  },
  plugins: [],
};

export default config;
