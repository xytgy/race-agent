import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        panel: "rgba(255,255,255,0.75)",
        border: "rgba(15,23,42,0.12)"
      },
      boxShadow: {
        soft: "0 12px 30px rgba(15, 23, 42, 0.10)"
      }
    }
  },
  plugins: []
} satisfies Config;

