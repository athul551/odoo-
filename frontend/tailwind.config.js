/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#1E1E1E',
          900: '#232326',
          800: '#252526',
          700: '#2D2D30',
          600: '#3A3A3D',
          500: '#454549',
        },
        paper: '#ECECEA',
        muted: '#A6A6A3',
        faint: '#7C7C78',
        accent: {
          DEFAULT: '#7AA2F7',
          hover: '#89ABF8',
          soft: 'rgba(122, 162, 247, 0.12)',
        },
        ok: '#7DC98F',
        warn: '#D9B36A',
        bad: '#E58B84',
        info: '#8FB8DE',
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'sans-serif',
        ],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      borderRadius: {
        panel: '10px',
      },
      transitionTimingFunction: {
        calm: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
      },
    },
  },
  plugins: [],
}
