// @ts-check
import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

// https://astro.build/config
export default defineConfig({
  site: 'https://hirewright.eu',
  output: 'static',
  base: '/lander',
  integrations: [
    tailwind({
      // We own the base layer inside src/styles/global.css (imported in BaseLayout),
      // so the integration should not inject its own base stylesheet.
      applyBaseStyles: false,
    }),
  ],
  build: {
    // Inline small stylesheets to avoid extra render-blocking requests.
    inlineStylesheets: 'auto',
  },
  compressHTML: true,
});
