export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: { extend: {
    colors: { canvas: 'var(--canvas)', surface: 'var(--surface)', accent: 'var(--accent)', muted: 'var(--muted)' },
    fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'] },
    boxShadow: { cinema: '0 24px 80px #0009' },
  } },
  plugins: [],
};
