# RedHand Showcase

This directory contains the promotional RedHand website. It is a Vite/React
single-page site with bilingual copy, desktop report imagery, and one-screen
scroll sections for the demo, method, detector taxonomy, adapters, report, and
evidence boundaries.

## Local Development

```bash
npm ci
npm run dev
```

Open the local URL printed by Vite.

## Production Build

```bash
npm run build
npm run preview
```

The Vite config uses a relative `base`, so the build can be hosted from a
GitHub Pages project path such as `https://<user>.github.io/redhand/`.

## GitHub Pages

The repository workflow at `.github/workflows/showcase-pages.yml` builds this
site and deploys `showcase/dist` with GitHub Pages. In the GitHub repository
settings, configure Pages to deploy from GitHub Actions.
