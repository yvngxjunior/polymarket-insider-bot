# PolyInsider Dashboard

**Premium React Dashboard** for PolyInsider Bot - Real-time portfolio tracking & trade analytics.

---

## 🎨 Design Features

### **Glassmorphism UI**
- White transparent cards with backdrop blur
- Subtle shadows & borders
- Smooth animations & transitions
- Gradient accent colors

### **Responsive Layout**
- Collapsible sidebar (desktop/mobile)
- Auto-refresh every 30s
- Real-time API status
- Touch-friendly mobile design

---

## 🚀 Quick Start

### **Prerequisites**

- Node.js 18+ (LTS recommended)
- API running on `localhost:8000`

### **Installation**

```bash
# Navigate to frontend folder
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev

# Open browser
# http://localhost:3000
```

**Expected output:**
```
VITE v5.1.0  ready in 450 ms

➜  Local:   http://localhost:3000/
➜  Network: http://192.168.1.x:3000/
```

---

## 📊 Pages

### **1. Dashboard** (`/`)

**Portfolio Overview:**
- Total Capital (card)
- Daily P&L (card)
- Drawdown % (card)
- Open Positions count (card)

**Active Positions Table:**
- Market question
- Entry / Current price
- Unrealized P&L
- TP/SL status badges
- Position age (relative time)

---

### **2. Positions** (`/positions`)

**Full Positions Table:**
- All open trades
- Capital deployed summary
- Sortable columns
- Live price updates (30s)

---

### **3. Trade History** (`/trades`)

**Paginated Trade Log:**
- Executed / Skipped / Failed filter
- 25 trades per page
- Realized P&L column
- TX hash links (Polygonscan)
- Relative timestamps

**Filters:**
- All trades
- Executed only
- Skipped only
- Failed only

---

### **4. Wallets** (`/wallets`)

**Insider Leaderboard:**
- Wallet score (0-100)
- Win rate %
- Total profit USD
- Consecutive losses
- Active/Inactive toggle
- Card grid layout

**Stats per wallet:**
- Score progress bar
- Win rate
- Total trades
- Last activity timestamp

---

### **5. Settings** (`/settings`)

_Coming soon:_
- Bot configuration
- Risk parameters
- Notification settings

---

## 🛠️ Tech Stack

| Technology | Purpose |
|------------|----------|
| **React 18** | UI framework |
| **TypeScript** | Type safety |
| **Vite** | Build tool (fast dev) |
| **Tailwind CSS** | Styling (utility-first) |
| **React Query** | Data fetching + caching |
| **React Router** | Navigation |
| **Heroicons** | Icon library |
| **date-fns** | Date formatting |
| **Recharts** | Charts (future) |

---

## 💡 Component Architecture

```
src/
├── components/
│   ├── Layout.tsx           # Main layout wrapper
│   ├── Sidebar.tsx          # Collapsible navigation
│   ├── Header.tsx           # Portfolio summary + health
│   ├── StatCard.tsx         # Glassmorphism stat card
│   ├── PortfolioOverview.tsx # 4 stat cards grid
│   └── PositionsTable.tsx   # Positions table component
│
├── pages/
│   ├── Dashboard.tsx        # Home page
│   ├── Positions.tsx        # Full positions view
│   ├── TradeHistory.tsx     # Paginated trades
│   ├── Wallets.tsx          # Insider leaderboard
│   └── Settings.tsx         # Config (placeholder)
│
├── services/
│   └── api.ts               # Axios API client
│
├── hooks/
│   └── useApi.ts            # React Query hooks
│
├── types/
│   └── index.ts             # TypeScript interfaces
│
├── App.tsx                  # React Router setup
├── main.tsx                 # React Query provider
└── index.css                # Tailwind + global styles
```

---

## 🎨 Styling Guidelines

### **Glassmorphism Cards**

```tsx
<div className="glass-card glass-card-hover">
  {/* Content */}
</div>
```

**CSS (defined in `index.css`):**
```css
.glass-card {
  @apply bg-white/70 backdrop-blur-md border border-white/30 shadow-glass rounded-2xl p-6;
}

.glass-card-hover {
  @apply hover:shadow-glass-hover hover:-translate-y-0.5 transition-all duration-300;
}
```

### **Color Classes**

```tsx
{/* Profit/Loss text */}
<span className="profit-text">+$12.30</span>
<span className="loss-text">-$8.50</span>

{/* Badges */}
<span className="badge badge-success">TP1✓</span>
<span className="badge badge-warning">Pending</span>
<span className="badge badge-error">Failed</span>
```

### **Stat Values (Monospace)**

```tsx
<div className="stat-value">$523.45</div>
{/* Font: Roboto Mono, 32px, bold */}
```

---

## 🔌 API Integration

### **Base URL**

```typescript
// vite.config.ts - Proxy to FastAPI
server: {
  port: 3000,
  proxy: {
    '/api': 'http://localhost:8000',
    '/health': 'http://localhost:8000',
  },
}
```

### **React Query Hooks**

```typescript
import { usePortfolio, usePositions, useTrades } from '@/hooks/useApi'

function MyComponent() {
  const { data: portfolio, isLoading } = usePortfolio()
  // Auto-refreshes every 30s
}
```

### **API Endpoints Used**

| Hook | Endpoint | Refresh Interval |
|------|----------|------------------|
| `useHealth()` | `GET /health` | 10s |
| `usePortfolio()` | `GET /api/portfolio` | 30s |
| `usePositions()` | `GET /api/positions` | 30s |
| `useTrades()` | `GET /api/trades` | 30s |
| `useWallets()` | `GET /api/wallets` | 30s |

---

## 📦 Build for Production

```bash
# Build optimized bundle
npm run build

# Output: dist/ folder

# Preview production build
npm run preview
```

**Deploy `dist/` folder to:**
- Vercel (recommended)
- Netlify
- GitHub Pages
- S3 + CloudFront

---

## ⚙️ Environment Variables

Create `.env` in `frontend/` folder:

```env
# API URL (optional, defaults to http://localhost:8000)
VITE_API_URL=http://localhost:8000
```

---

## 🐛 Troubleshooting

### **Error: "Failed to fetch"**

**Cause:** API not running on `localhost:8000`

**Fix:**
```bash
# Terminal 1: Start API
cd ..
uvicorn api.main:app --reload --port 8000

# Terminal 2: Start frontend
cd frontend
npm run dev
```

---

### **Error: "Cannot find module '@heroicons/react'"**

**Cause:** Dependencies not installed

**Fix:**
```bash
npm install
```

---

### **Port 3000 already in use**

**Fix:** Change port in `vite.config.ts`
```typescript
server: {
  port: 3001, // Or any free port
}
```

---

## 📱 Mobile Responsive

**Breakpoints:**
- Mobile: `< 768px` (single column, hamburger menu)
- Tablet: `768px - 1024px` (2 columns, icons-only sidebar)
- Desktop: `> 1024px` (full layout, sidebar with labels)

**Touch-friendly:**
- Larger tap targets (min 44px)
- Swipe-friendly tables (horizontal scroll)
- Bottom navigation on mobile (future)

---

## 🚀 Future Enhancements (Phase 3)

- [ ] **WebSocket** real-time updates (no polling)
- [ ] **Performance charts** (P&L over time with Recharts)
- [ ] **Dark mode** toggle
- [ ] **CSV export** (trades, positions)
- [ ] **Push notifications** (browser API)
- [ ] **Mobile app** (React Native)

---

## 📝 License

Same as parent project (PolyInsider Bot).

---

**Ready for Production!** 🎉
