/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,ts,md,mdx}'],
  theme: {
    // Brand tokens are locked. Do not invent new colors.
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      navy: '#0A2540', // primary surface, ~70% of the page
      ink: '#0D0D0D', // text, anchor
      paper: '#FAFAFA', // background
      amber: '#F59E0B', // functional accent only. Under 5% of pixel area
      slate: '#6E6E73', // secondary text, captions
      white: '#FFFFFF',
      black: '#000000',
    },
    extend: {
      fontFamily: {
        // Display: industrial signage register, uppercase, heavy, tight tracking
        display: ['"Archivo Condensed"', 'Arial Narrow', 'sans-serif'],
        // Body
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        // Data: spec-sheet numbers
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      letterSpacing: {
        caps: '0.14em', // small-caps labels above rules
        display: '-0.01em', // tight tracking on the display face
      },
      borderRadius: {
        // Zero to minimal radius. No rounded pills.
        none: '0',
        DEFAULT: '0',
        sm: '2px',
      },
      maxWidth: {
        shell: '1200px',
      },
      fontSize: {
        // Fluid display scale for hero + section headers
        'display-xl': ['clamp(2.5rem, 6vw, 5.25rem)', { lineHeight: '0.95', letterSpacing: '-0.01em' }],
        'display-lg': ['clamp(2rem, 4.5vw, 3.5rem)', { lineHeight: '1.0', letterSpacing: '-0.01em' }],
        'display-md': ['clamp(1.5rem, 3vw, 2.25rem)', { lineHeight: '1.05', letterSpacing: '-0.005em' }],
        'stat': ['clamp(2.5rem, 6vw, 4rem)', { lineHeight: '0.9' }],
        'label': ['0.6875rem', { lineHeight: '1', letterSpacing: '0.14em' }],
      },
    },
  },
  plugins: [],
};
