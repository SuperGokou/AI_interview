/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0A0F1C',
        surface: '#121A2E',
        surface2: '#1A2438',
        border: '#243049',
        text: '#E8EEF9',
        muted: '#8593AD',
        cyan: '#2DD4EF',
        blue: '#3B82F6',
        purple: '#A78BFA',
        green: '#2BE5A4',
        yellow: '#FACC15',
        red: '#FB5070',
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
      boxShadow: {
        'glow-cyan': '0 0 24px rgba(45,212,239,0.45)',
        'glow-green': '0 0 24px rgba(43,229,164,0.45)',
      },
      borderRadius: { xl: '14px', '2xl': '18px', '3xl': '22px' },
    },
  },
  plugins: [],
};
