// Runtime configuration sourced from environment variables.
// Every value has a safe default so the site builds and works before the
// real endpoints and IDs are wired in.

export const SITE = {
  name: 'Hirewright',
  url: 'https://hirewright.eu',
  legalEntity: 'NIVO TECH HUNGARY Kft.',
} as const;

// Forms POST here. When unset, the client falls back to a mock success state
// so the page is fully usable before the endpoint is live.
export const WEBHOOK_URL: string = import.meta.env.PUBLIC_WEBHOOK_URL ?? '';

// Meta Pixel id. Empty => pixel is not loaded at all.
export const META_PIXEL_ID: string = import.meta.env.PUBLIC_META_PIXEL_ID ?? '';

// Google Tag Manager container id, e.g. GTM-XXXXXX. Empty => GTM not loaded.
export const GTM_ID: string = import.meta.env.PUBLIC_GTM_ID ?? '';
