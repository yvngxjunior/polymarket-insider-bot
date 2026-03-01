/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'brand': '#ff0055',
        'ink': '#0a0a0a',
        'paper': '#ffffff',
        'muted': '#888888',
      },
      fontFamily: {
        'display': ['Syne', 'ui-sans-serif', 'system-ui'],
        'body': ['Atkinson Hyperlegible', 'ui-sans-serif', 'system-ui'],
        'mono': ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        'display': ['96px', { lineHeight: '0.9', letterSpacing: '-0.02em' }],
        'hero': ['72px', { lineHeight: '0.95', letterSpacing: '-0.01em' }],
        'mega': ['144px', { lineHeight: '0.85', letterSpacing: '-0.03em' }],
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
        '30': '7.5rem',
        '40': '10rem',
      },
      borderRadius: {
        'none': '0',
      },
    },
  },
  plugins: [],
}
