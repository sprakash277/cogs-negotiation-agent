/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["DM Sans", "system-ui", "sans-serif"],
      },
      colors: {
        orange: { DEFAULT: "#FF6F3C", light: "#FF8C5C" },
        teal: { DEFAULT: "#14323d", deep: "#080F14" },
        cyan: "#22D3EE",
        gold: "#F59E0B",
        purple: "#A78BFA",
        mint: "#64FFDA",
        rose: "#FB7185",
      },
    },
  },
  plugins: [],
};
