/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        portal: {
          header: "#1e293b",
          sidebar: "#f8fafc",
          accent: "#2563eb",
        },
      },
    },
  },
  plugins: [],
};
