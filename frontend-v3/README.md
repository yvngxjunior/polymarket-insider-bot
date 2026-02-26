# PolyInsider Dashboard v3.0 🚀

> **Ultra-moderne, zero bloat, powered by Claude Sonnet 4.6**

## Stack

- **Next.js 15** - App Router
- **React 19** - Latest features
- **TypeScript 5.7** - Type safety
- **Tailwind CSS** - Utility-first styling
- **Zero UI libraries** - Custom components only

## Quick Start

```bash
cd frontend-v3
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Features

- ✅ **Dashboard** - Real-time metrics & charts
- ✅ **Settings** - Complete bot configuration
- ✅ **Positions** - Active trades monitoring
- ✅ **History** - Trade history with filters
- ✅ **Dark mode** - Beautiful dark theme
- ✅ **Mobile responsive** - Works on all devices

## Architecture

```
frontend-v3/
├── app/
│   ├── page.tsx           # Dashboard
│   ├── settings/          # Settings page
│   ├── positions/         # Positions page
│   ├── history/           # History page
│   └── layout.tsx         # Root layout
├── components/
│   ├── ui/                # Custom UI components
│   └── charts/            # Chart components
└── lib/
    ├── api.ts             # API client
    └── types.ts           # TypeScript types
```

## Backend API

Make sure backend is running on `http://localhost:8000`

```bash
cd ../backend
python run.py
```

---

**Built with ❤️ by Claude Sonnet 4.6**
