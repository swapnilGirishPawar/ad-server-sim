/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 900: '#0c111b', 950: '#070a10' },
        panel: { DEFAULT: '#10161f', raised: '#161d2b' },
        line: { DEFAULT: '#212a3a', soft: 'rgba(255,255,255,0.06)' },
      },
      boxShadow: {
        card: '0 1px 0 rgba(255,255,255,0.02) inset',
        glow: '0 0 0 3px rgba(99,102,241,0.35)',
        button: '0 6px 16px -8px rgba(99,102,241,0.7)',
      },
    },
  },
  plugins: [],
}
