# F.R.E.D Frontend (UI)

This is the Vue + Vite frontend for F.R.E.D.

## Important Startup Order
Start the **backend first**, then run the frontend.

- Backend entry point from repo root: `start-backend.bat`
- Frontend runs from: `UI/`

If the backend is not running first, frontend API calls may fail.

## Prerequisites
- Node.js: `20.19+` or `22.12+`
- npm (comes with Node.js)

## Install Dependencies
From the `UI` directory:

```bash
npm ci
```

Use `npm ci` to install exact versions from `package-lock.json`.

## Run Frontend (Development)
From the `UI` directory:

```bash
npm run dev
```

Vite will print the local URL (usually `https://localhost:5173`).

## Developer Settings Password
The sidebar developer settings (local camera toggle, Gemini toggle, and MQ calibration button) can be password-protected.

Set a Vite env variable before running the frontend:

```bash
export VITE_DEV_SETTINGS_PASSWORD="your-strong-password"
npm run dev
```

If this variable is not set, the frontend falls back to `fred-dev`.

## Build for Production
```bash
npm run build
```

## Preview Production Build
```bash
npm run preview
```

## Recommended Workflow
1. From repo root, start backend:
   - `start-backend.bat`
2. In a second terminal, go to `UI/` and run:
   - `npm ci` (first time only)
   - `npm run dev`
