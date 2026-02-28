# PolyInsider Dashboard 📊

Modern React dashboard for real-time monitoring of the PolyInsider Bot with Trailing Stop-Loss visualization.

## ✨ Features

- **Real-time Stats** - Portfolio, PnL, active positions
- **Trailing SL Visualization** - Interactive charts showing entry/peak prices
- **Wallet Discovery Tracking** - Monitor auto-discovered top traders
- **Live Updates** - WebSocket connection for instant trade notifications
- **Responsive Design** - Works on desktop, tablet, and mobile

## 🚀 Quick Start

### Prerequisites

- Node.js 18+ installed
- PolyInsider Bot API running on `http://localhost:8001`

### Installation

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The dashboard will be available at **http://localhost:3000**

## 🔧 Configuration

Create a `.env` file in the `frontend/` directory:

```env
VITE_API_URL=http://localhost:8001
```

## 📦 Production Build

```bash
# Build for production
npm run build

# Preview production build
npm run preview
```

Production files will be in `frontend/dist/`

## 🎨 Tech Stack

- **React 18** - UI framework
- **Vite** - Fast build tool
- **Tailwind CSS** - Styling
- **Recharts** - Charts and visualizations
- **Lucide React** - Icon library
- **Axios** - API client

## 📊 Dashboard Sections

### 1. Stats Cards
- Total Capital
- Total PnL
- Trailing SL Active Positions
- Auto-Discovered Wallets

### 2. Trailing SL Chart
- Visual representation of entry vs peak prices
- Activation threshold line (+15%)
- Real-time updates every 5 seconds

### 3. Active Positions Table
- Position ID
- Entry/Peak prices
- Current gain %
- Trailing status (Active/Watching)

### 4. Top Wallets Table
- Tracked wallet addresses
- Score visualization
- Win rate %
- Total trades count

## 🔄 API Endpoints Used

```
GET /api/features/status          - Overall features status
GET /api/portfolio                - Portfolio summary
GET /api/features/trailing-sl/status - Trailing SL positions
GET /api/wallets                  - Tracked wallets list
```

## 🎯 Roadmap

- [ ] WebSocket real-time trade stream
- [ ] Historical performance charts
- [ ] Manual wallet discovery trigger
- [ ] Trailing SL config editor
- [ ] Dark/Light theme toggle
- [ ] Export data to CSV

## 🐛 Troubleshooting

**API connection error?**
- Make sure the bot API is running: `uvicorn api.main:app --port 8001`
- Check CORS settings in `api/main.py`

**Chart not showing?**
- Verify you have active positions with Trailing SL enabled
- Check browser console for errors

**Styling issues?**
- Clear browser cache
- Rebuild Tailwind: `npm run dev`

## 📝 License

Same as parent project.
