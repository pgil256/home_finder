/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./templates/DataProcessor/**/*.html",
    "./templates/DocumentProcessor/**/*.html",
    "./templates/WebScraper/**/*.html",
    "./templates/KeywordSelection/**/*.html",
    "./templates/Pages/**/*.html",
    "./static/js/**/*.js",
  ],
  media: false,
  theme: {
    extend: {},
  },
  variants: {
    extend: {},
  },
  plugins: [],
};
