// All user-facing copy lives here so a German version can be added at
// src/content/copy.de.ts with the same shape and wired at /de without a refactor.
// Copy is locked. Do not rewrite, do not add em dashes, do not add exclamation marks.

export type RateCategory = {
  id: string; // used as the form role value and as an anchor target
  category: string;
  description: string;
  rate: string; // display string, e.g. "29"
  rateUnit: string; // "/hr"
};

export const copy = {
  lang: 'en',
  locale: 'en_GB',

  // Placeholders — do not invent real values. Fill before launch.
  contact: {
    email: '[EMAIL_PLACEHOLDER]',
    phone: '[PHONE_PLACEHOLDER]',
    address: '[OFFICE_ADDRESS_HU]',
  },

  meta: {
    title: 'Skilled Workers for German Industry | Hirewright Staffing',
    description:
      'Hirewright places skilled and semi-skilled crews from Hungary, Romania, Poland and Slovakia onto German industrial sites. Housing, transport and paperwork handled. Published hourly rates, precise quote in 24 hours.',
    ogAlt: 'Hirewright — skilled Central European crews placed in German industry since 2001.',
  },

  nav: {
    links: [
      { label: 'Track record', href: '#track-record' },
      { label: 'Rate card', href: '#rate-card' },
      { label: 'Why Hirewright', href: '#why' },
      { label: 'About', href: '#about' },
    ],
    cta: 'Request workers',
    skipToContent: 'Skip to content',
  },

  hero: {
    eyebrow: 'Industrial staffing since 2001',
    h1: 'Skilled workers for German industry, ready in days.',
    sub: 'We recruit skilled and semi-skilled crews from Hungary, Romania, Poland, and Slovakia, and place them on your line with housing, transport, and paperwork handled. You pay only for hours worked.',
    support:
      'Placing crews on Europe’s most demanding industrial projects since 2001. Over 1,500 workers deployed.',
    primaryCta: 'Request workers',
    secondaryCta: 'Get a price in 24 hours',
  },

  socialProof: {
    eyebrow: 'Trusted on projects with',
    items: ['BMW Group', 'Mercedes-Benz', 'NATO', 'Bremerhaven Shipyard', 'DPD'],
  },

  trackRecord: {
    label: 'Track record',
    stats: [
      { prefix: '+', value: 25, label: 'Years of experience' },
      { prefix: '+', value: 1500, label: 'Workers placed' },
      { prefix: '', value: 4, label: 'Countries in network' },
      { prefix: '+', value: 30, label: 'Active partners' },
    ],
  },

  rateCard: {
    label: 'Rate card / 2026 / EUR per hour',
    heading: 'Rate card',
    rows: [
      {
        id: 'skilled-trades',
        category: 'Skilled trades',
        description:
          'Welders (including certified), electricians, HVAC technicians, fitters, machinists',
        rate: '29',
        rateUnit: '/hr',
      },
      {
        id: 'industrial-specialists',
        category: 'Industrial specialists',
        description:
          'Sprinkler installation, calibration technicians, security system installers',
        rate: '29',
        rateUnit: '/hr',
      },
      {
        id: 'construction-and-finishing',
        category: 'Construction and finishing',
        description: 'Painters, pipefitters, general construction',
        rate: '25',
        rateUnit: '/hr',
      },
      {
        id: 'semi-skilled-production',
        category: 'Semi-skilled production',
        description: 'Assembly line workers, packagers, machine operators',
        rate: '20',
        rateUnit: '/hr',
      },
      {
        id: 'logistics-and-warehouse',
        category: 'Logistics and warehouse',
        description: 'Warehouse workers, forklift operators, drivers',
        rate: '20',
        rateUnit: '/hr',
      },
      {
        id: 'cleaning-and-maintenance',
        category: 'Cleaning and maintenance',
        description:
          'Residential and commercial cleaning crews, specialised industrial workers',
        rate: '19',
        rateUnit: '/hr',
      },
    ] as RateCategory[],
    finePrint:
      'Rates are indicative and depend on role, volume, and duration. Exact quote within 24 hours.',
  },

  ctaBand: {
    h2: 'Need skilled workers? Let’s talk.',
    sub: 'Tell us the roles, the headcount, and the timeline. You get an indicative price the same day and a precise quote within 24 hours.',
    button: 'Request workers',
  },

  why: {
    heading: 'Why Hirewright',
    points: [
      {
        claim: 'You pay only for hours worked.',
        support: 'No retainer, no upfront fee. The meter runs when the work does.',
      },
      {
        claim: 'Rates are published, not negotiated.',
        support:
          'What you see is what you pay. Procurement doesn’t have to fight for a number.',
      },
      {
        claim: 'A four-country network moves fast.',
        support:
          'Hungary, Romania, Poland, Slovakia. When one pipeline is tight, another fills the gap, so crews mobilise in days, not months.',
      },
      {
        claim: 'Full operational support is included.',
        support:
          'Housing, transport, paperwork, sick leave, integration. You manage the work. We handle everything around it.',
      },
      {
        claim: '25 years on the plant floor.',
        support:
          'Placements with BMW, Mercedes-Benz, NATO, and the Bremerhaven shipyard. We know what a German line demands.',
      },
    ],
  },

  about: {
    heading: 'The bridge between European industry and the people who build it.',
    body: 'Hirewright has connected Central European skilled labour with German industry since 2001. We recruit across four countries, place crews on the lines that need them, and stand behind the people we send. Two decades in, that model has put more than 1,500 workers onto Europe’s most demanding industrial projects.',
    valuesLabel: 'Values',
    values: [
      {
        claim: 'Fast.',
        support:
          'A four-country network keeps moving when others stall. Crews mobilise in days.',
      },
      {
        claim: 'Transparent.',
        support: 'Rates published, hours billed. No surprises on the invoice.',
      },
      {
        claim: 'Human.',
        support:
          'Housing, paperwork, and care for the people we place. Workers who are looked after stay, and stay good.',
      },
    ],
  },

  form: {
    label: 'Request workers',
    heading: 'Request workers',
    sub: 'Short form. You get an indicative price today and a precise quote within 24 hours.',
    fields: {
      company: { label: 'Company', required: true },
      contactName: { label: 'Contact name', required: true },
      email: { label: 'Work email', required: true },
      phone: { label: 'Phone', required: true },
      role: { label: 'Role or trade needed', required: false },
      headcount: { label: 'Headcount', required: false },
      location: { label: 'Site location', required: false },
      startDate: { label: 'Start date', required: false },
      notes: { label: 'Notes', required: false },
    },
    roleOtherLabel: 'Other',
    rolePlaceholder: 'Select a role',
    submit: 'Request workers',
    success:
      'We have your request. You get an indicative price today and a precise quote within 24 hours.',
    error:
      'Something went wrong sending your request. Please try again, or email us directly.',
    validation: {
      company: 'Enter your company name.',
      contactName: 'Enter a contact name.',
      email: 'Enter a valid work email, for example name@company.com.',
      phone: 'Enter a phone number we can reach you on.',
    },
  },

  quickQuote: {
    trigger: 'Get a price in 24 hours',
    heading: 'Get a price in 24 hours',
    sub: 'Three fields. We reply the same day with an indicative price.',
    fields: {
      email: { label: 'Work email' },
      roles: { label: 'Roles needed' },
      headcount: { label: 'Headcount' },
    },
    submit: 'Get a price in 24 hours',
    success:
      'We have your request. You get an indicative price today and a precise quote within 24 hours.',
    close: 'Close',
  },

  footer: {
    tagline: 'Built on the right people.',
    brandLine:
      'Skilled Central European crews, placed in German industry. Since 2001.',
    columns: {
      services: {
        heading: 'Services',
        items: [
          'Skilled trades',
          'Industrial specialists',
          'Construction and finishing',
          'Semi-skilled production',
          'Logistics and warehouse',
          'Cleaning and maintenance',
        ],
      },
      company: {
        heading: 'Company',
        items: [
          { label: 'Track record', href: '#track-record' },
          { label: 'Why Hirewright', href: '#why' },
          { label: 'About', href: '#about' },
          { label: 'Contact', href: '#request' },
        ],
      },
      contact: {
        heading: 'Get in touch',
      },
    },
    legal: {
      copyright: 'All rights reserved.',
      impressum: 'Impressum',
      privacy: 'Privacy',
    },
  },

  // Used for the FAQPage JSON-LD block. Answers are declarative, on-brand.
  faq: [
    {
      q: 'What does Hirewright cost?',
      a: 'Rates are published by category and billed per hour worked. Skilled trades and industrial specialists from 29 EUR per hour, construction and finishing from 25 EUR per hour, semi-skilled production and logistics from 20 EUR per hour, cleaning and maintenance from 19 EUR per hour. You get a precise quote within 24 hours.',
    },
    {
      q: 'Where do the workers come from?',
      a: 'We recruit skilled and semi-skilled crews across a four-country network: Hungary, Romania, Poland, and Slovakia. When one pipeline is tight, another fills the gap.',
    },
    {
      q: 'How fast can crews start?',
      a: 'Crews mobilise in days, not months. Tell us the roles, the headcount, and the timeline, and you get an indicative price the same day.',
    },
    {
      q: 'What is included beyond the workers?',
      a: 'Housing, transport, paperwork, sick leave, and integration are handled. You manage the work. We handle everything around it.',
    },
    {
      q: 'Do I pay a retainer or upfront fee?',
      a: 'No. You pay only for hours worked. No retainer, no upfront fee.',
    },
  ],
} as const;

export type Copy = typeof copy;
