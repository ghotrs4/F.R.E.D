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

Vite will print the local URL (usually `http://localhost:5173`).

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
