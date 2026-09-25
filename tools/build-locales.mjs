#!/usr/bin/env node
// index_legacy.html owns the shared layout and data-en/data-de/data-hu copy.
// Generate crawlable translated pages before assembling the deployable site.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parse, serialize } from 'parse5';

const root = new URL('../', import.meta.url);
const source = readFileSync(new URL('index_legacy.html', root), 'utf8');
const metadata = {
  de: {
    title: 'Industriepersonal & Fachkräftevermittlung in Europa | Hirewright',
    description: 'Hirewright vermittelt qualifizierte Industriearbeiter — Schweißer, Elektriker, Monteure, Maschinenbediener — nach Deutschland und Westeuropa. Über 1.500 Vermittlungen seit 2001. Volle operative Unterstützung, transparente Stundensätze.',
    social: 'Qualifizierte Industriearbeiter für Deutschland und Westeuropa — Schweißer, Elektriker, Monteure, Bediener. Über 1.500 Vermittlungen seit 2001.',
    locale: 'de_DE', alternates: ['en_GB', 'hu_HU'],
  },
  hu: {
    title: 'Ipari munkaerő-közvetítés és szakember-toborzás Európában | Hirewright',
    description: 'A Hirewright ipari szakembereket — hegesztőket, villanyszerelőket, szerelőket és gépkezelőket — közvetít Németországba és Nyugat-Európába. 2001 óta több mint 1500 közvetített munkavállaló. Teljes körű háttértámogatás, átlátható óradíjak.',
    social: 'Ipari szakemberek Németországban és Nyugat-Európában — hegesztők, villanyszerelők, szerelők, gépkezelők. 2001 óta több mint 1500 közvetített munkavállaló.',
    locale: 'hu_HU', alternates: ['en_GB', 'de_DE'],
    keywords: 'ipari munkaerő-közvetítés, szakember-toborzás, hegesztők, villanyszerelők, ipari munkaerő, európai munkaerő-közvetítés',
  },
};
const attr = (node, name) => node.attrs?.find(a => a.name === name)?.value;
function setAttr(node, name, value) {
  const existing = node.attrs.find(a => a.name === name);
  if (existing) existing.value = value;
  else node.attrs.push({ name, value });
}
function setText(node, value) {
  node.childNodes = [{ nodeName: '#text', value, parentNode: node }];
}
function walk(node, visit) {
  visit(node);
  for (const child of node.childNodes || []) walk(child, visit);
}

for (const [lang, meta] of Object.entries(metadata)) {
  const document = parse(source);
  let alternateIndex = 0;
  walk(document, node => {
    if (!node.tagName) return;
    const en = attr(node, 'data-en');
    if (en !== undefined) {
      const translated = attr(node, `data-${lang}`);
      if (!translated) throw new Error(`Missing ${lang} translation: ${en}`);
      if (['input', 'textarea'].includes(node.tagName)) setAttr(node, 'placeholder', translated);
      else if (!(node.childNodes || []).some(child => child.tagName)) setText(node, translated);
      else throw new Error(`Translation must be on a leaf element: ${en}`);
    }
    for (const name of ['alt', 'aria-label', 'title']) {
      const value = attr(node, `data-${name}-${lang}`);
      if (value) setAttr(node, name, value);
    }
    if (node.tagName === 'html') setAttr(node, 'lang', lang);
    if (node.tagName === 'title') setText(node, meta.title);
    if (node.tagName === 'meta') {
      const key = attr(node, 'name') || attr(node, 'property');
      const values = {
        description: meta.description, 'og:title': meta.title,
        'og:description': meta.social, 'og:url': `https://hirewright.eu/${lang}/`,
        'og:locale': meta.locale, 'twitter:title': meta.title,
        'twitter:description': meta.social,
        ...(meta.keywords ? { keywords: meta.keywords } : {}),
      };
      if (values[key]) setAttr(node, 'content', values[key]);
      if (key === 'og:locale:alternate') setAttr(node, 'content', meta.alternates[alternateIndex++]);
    }
    if (node.tagName === 'link' && attr(node, 'rel') === 'canonical') {
      setAttr(node, 'href', `https://hirewright.eu/${lang}/`);
    }
    if (node.tagName === 'option' && attr(node.parentNode, 'id') === 'lang-toggle') {
      node.attrs = node.attrs.filter(a => a.name !== 'selected');
      if (attr(node, 'value') === lang) setAttr(node, 'selected', '');
    }
    if (attr(node, 'id')?.startsWith('foot-')) {
      const active = attr(node, 'id') === `foot-${lang}`;
      setAttr(node, 'aria-pressed', String(active));
      if (active) setAttr(node, 'class', attr(node, 'class') + ' lang-active');
    }
    for (const name of ['src', 'href']) {
      const value = attr(node, name);
      if (value && !/^(?:[a-z][a-z\d+.-]*:|#|\/)/i.test(value)) setAttr(node, name, '/' + value);
    }
    if (node.tagName === 'script' && attr(node, 'type') === 'application/ld+json' && lang === 'hu') {
      const data = JSON.parse(node.childNodes[0].value);
      const [organization, , service] = data['@graph'];
      organization.slogan = 'Ipari szakmunka, ahogy kell.';
      organization.description = meta.description;
      organization.areaServed.forEach((area, i) => area.name = ['Németország', 'Ausztria', 'Svájc', 'Nyugat-Európa'][i]);
      service.serviceType = 'Ipari munkaerő-közvetítés és szakember-toborzás';
      service.areaServed.name = 'Közép- és Nyugat-Európa';
      service.hasOfferCatalog.name = 'Munkaerő-kategóriák';
      const names = ['Szakmunka — hegesztők, villanyszerelők, épületgépészeti technikusok, szerelők, gépi forgácsolók', 'Ipari specialisták — sprinklerrendszerek, kalibrálás, biztonsági rendszerek', 'Építőipar és befejező munkák — festők, csőszerelők, általános építőipar', 'Betanított gyártási munkák — összeszerelés, csomagolás, gépkezelés', 'Logisztika és raktározás — raktári dolgozók, targoncavezetők, gépjárművezetők', 'Takarítás és karbantartás — lakó-, üzleti és ipari ingatlanok'];
      service.hasOfferCatalog.itemListElement.forEach((offer, i) => {
        offer.itemOffered.name = names[i];
        offer.priceSpecification.unitText = 'óra';
      });
      setText(node, JSON.stringify(data, null, 2));
    }
  });
  const output = serialize(document).replace("const PAGE_LANG = 'en';", `const PAGE_LANG = '${lang}';`);
  const directory = new URL(`${lang}/`, root);
  mkdirSync(directory, { recursive: true });
  writeFileSync(new URL('index.html', directory), output);
  console.log(`Generated ${fileURLToPath(new URL('index.html', directory))}`);
}
