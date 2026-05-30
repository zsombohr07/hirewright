#!/usr/bin/env node
/**
 * build-de.js — generates the German page (../de/index.html) from ../index.html.
 *
 * index.html is the single source of truth (English). Every translatable element
 * carries a `data-de` German counterpart (the same pairs the in-browser language
 * toggle uses). This script bakes the German text in as the default, rewrites the
 * <head> for German + the /de/ canonical, makes relative asset paths root-absolute
 * (because the page now lives one directory deep), and flips PAGE_LANG to 'de'.
 *
 * Run after any edit to index.html:   node tools/build-de.js
 */
const fs = require('fs');
const path = require('path');
const cheerio = require('cheerio');

const ROOT = path.join(__dirname, '..');
const SRC = path.join(ROOT, 'index.html');
const OUT_DIR = path.join(ROOT, 'de');
const OUT = path.join(OUT_DIR, 'index.html');

const DE = {
  title: 'Industriepersonal & Fachkräftevermittlung in Europa | Hirewright',
  description: 'Hirewright vermittelt qualifizierte Industriearbeiter — Schweißer, Elektriker, Monteure, Maschinenbediener — nach Deutschland und Westeuropa. Über 1.500 Vermittlungen seit 2001. Volle operative Unterstützung, transparente Stundensätze.',
  ogDescription: 'Qualifizierte Industriearbeiter für Deutschland und Westeuropa — Schweißer, Elektriker, Monteure, Bediener. Über 1.500 Vermittlungen seit 2001.',
};

const html = fs.readFileSync(SRC, 'utf8');
const $ = cheerio.load(html, { decodeEntities: false });

// 1. Swap visible text/placeholders/options to German (mirrors setLang() in the browser).
$('[data-de]').each((_, el) => {
  const $el = $(el);
  const de = $el.attr('data-de');
  if (de == null) return;
  const tag = (el.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea') {
    $el.attr('placeholder', de);
  } else if (tag === 'option') {
    $el.text(de);
  } else if ($el.children().length === 0) {
    $el.text(de);
  }
});

// 2. <head> — language, title, description, canonical and social tags.
$('html').attr('lang', 'de');
$('title').text(DE.title);
$('meta[name="description"]').attr('content', DE.description);
$('link[rel="canonical"]').attr('href', 'https://hirewright.eu/de/');
$('meta[property="og:title"]').attr('content', DE.title);
$('meta[property="og:description"]').attr('content', DE.ogDescription);
$('meta[property="og:url"]').attr('content', 'https://hirewright.eu/de/');
$('meta[property="og:locale"]').attr('content', 'de_DE');
$('meta[property="og:locale:alternate"]').attr('content', 'en_GB');
$('meta[name="twitter:title"]').attr('content', DE.title);
$('meta[name="twitter:description"]').attr('content', DE.ogDescription);

// 3. Make relative asset paths root-absolute (page now lives at /de/).
const needsRoot = (u) => u && !/^(https?:|data:|mailto:|tel:|#|\/)/i.test(u);
$('img[src]').each((_, el) => {
  const src = $(el).attr('src');
  if (needsRoot(src)) $(el).attr('src', '/' + src);
});
$('link[rel="icon"], link[rel="apple-touch-icon"]').each((_, el) => {
  const href = $(el).attr('href');
  if (needsRoot(href)) $(el).attr('href', '/' + href);
});

// 4. Flip the runtime language constant so the toggle/nav behaves as the DE page.
let out = $.html();
out = out.replace(/const PAGE_LANG = 'en';/, "const PAGE_LANG = 'de';");

fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(OUT, out, 'utf8');
console.log('Generated', path.relative(ROOT, OUT));
