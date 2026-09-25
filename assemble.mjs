// Assemble the deployable output directory.
//
//   output/            -> served at https://hirewright.eu/
//     index.html       = legacy homepage (index_legacy.html)
//     <legacy assets>  = images, logos, favicons, robots, sitemap, /de, /hu
//     lander/          = the Astro build (built with base: '/lander')
//
// The Astro build in dist/ references everything under /lander/..., so the
// whole dist/ is dropped into output/lander/. The legacy static site keeps
// owning the site root.

import { existsSync, rmSync, mkdirSync, cpSync, copyFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = process.cwd();
const OUT = join(ROOT, 'output');
const DIST = join(ROOT, 'dist');

if (!existsSync(DIST)) {
  console.error('assemble: dist/ not found — run `astro build` first.');
  process.exit(1);
}

// Fresh output.
rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

// 1) Astro build -> output/lander/
cpSync(DIST, join(OUT, 'lander'), { recursive: true });

// 2) Legacy homepage -> output/index.html
copyFileSync(join(ROOT, 'index_legacy.html'), join(OUT, 'index.html'));

// 3) Legacy root assets referenced by the homepage + its translated pages.
const files = [
  '01_primary_lockup.png',
  '02_primary_lockup_reversed copy.png',
  '03_monogram_navy.png',
  'Skilled trades.jpg',
  'cleaner.jpg',
  'construction.jpg',
  'industrial-specialist.jpg',
  'logistics.jpg',
  'operators.jpg',
  'apple-touch-icon.png',
  'favicon-32.png',
  'og-image.jpg',
  'robots.txt',
  'sitemap.xml',
];
const dirs = ['case_study_logos', 'de', 'hu'];

let copied = 0;
for (const f of files) {
  const src = join(ROOT, f);
  if (existsSync(src)) {
    copyFileSync(src, join(OUT, f));
    copied++;
  } else {
    console.warn('assemble: missing legacy asset (skipped):', f);
  }
}
for (const d of dirs) {
  const src = join(ROOT, d);
  if (existsSync(src)) {
    cpSync(src, join(OUT, d), { recursive: true });
    copied++;
  } else {
    console.warn('assemble: missing legacy dir (skipped):', d);
  }
}

console.log(`assemble: output/ ready — legacy at /, Astro at /lander/ (${copied} legacy items).`);
