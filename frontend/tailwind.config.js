/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        // calm dark operations surfaces
        base: '#1E1E1E',
        panel: '#252526',
        raised: '#2D2D30',
        sunken: '#232326',
        line: '#3A3A3D',
        // text
        primary: '#ECECEA',
        secondary: '#A6A6A3',
        muted: '#7C7C78',
        // single interactive accent — active states, focus, primary CTA
        accent: {
          DEFAULT: '#7AA2F7',
          hover: '#89ABF8',
        },
        // muted, small-area status colors
        ok: '#7DC98F',
        warn: '#D9B36A',
        bad: '#E58B84',
        info: '#8FB8DE',
      },
    },
  },
  plugins: [],
}
