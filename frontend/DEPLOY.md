# 🚀 Déploiement du Dashboard PolyInsider

## Option 1 : Vercel (Recommandé - Gratuit)

### 1. Préparer le déploiement

```bash
# Pull les derniers changements
git pull origin feature/trailing-sl-discovery

# Va dans le dossier frontend
cd frontend

# Installe les deps (si pas déjà fait)
npm install
```

### 2. Deploy sur Vercel

**Option A : Via CLI**

```bash
# Installe Vercel CLI
npm install -g vercel

# Login
vercel login

# Deploy
vercel --prod
```

**Option B : Via GitHub (plus simple)**

1. Va sur [vercel.com](https://vercel.com)
2. Connecte ton compte GitHub
3. Click "Import Project"
4. Sélectionne `polymarket-insider-bot`
5. Configure :
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
6. Ajoute les variables d'environnement :
   ```
   VITE_API_URL=https://your-api-url.com
   VITE_WS_URL=wss://your-api-url.com
   ```
7. Click "Deploy"

### 3. Configure l'API Backend

**Tu as 2 options :**

#### Option A : API sur le même serveur (VPS/Dedicated)

```bash
# Sur ton serveur, installe nginx
sudo apt install nginx

# Config nginx pour reverse proxy
sudo nano /etc/nginx/sites-available/polyinsider-api
```

Ajoute :

```nginx
server {
    listen 80;
    server_name api.polyinsider.com;

    location / {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /ws {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }
}
```

Active :

```bash
sudo ln -s /etc/nginx/sites-available/polyinsider-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

SSL avec Certbot :

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d api.polyinsider.com
```

#### Option B : API sur Railway/Render (Gratuit tier)

**Railway.app :**

1. Va sur [railway.app](https://railway.app)
2. "New Project" > "Deploy from GitHub"
3. Sélectionne ton repo
4. Configure :
   - **Start Command**: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
   - Ajoute toutes tes variables d'env du `.env`
5. Deploy

**Render.com :**

1. Va sur [render.com](https://render.com)
2. "New" > "Web Service"
3. Connect GitHub
4. Configure :
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
5. Ajoute les env vars

### 4. Update l'URL de l'API dans Vercel

Une fois l'API déployée :

1. Va dans Vercel Dashboard > Settings > Environment Variables
2. Update :
   ```
   VITE_API_URL=https://ton-api.railway.app (ou ton domaine)
   VITE_WS_URL=wss://ton-api.railway.app
   ```
3. Redeploy le frontend

---

## Option 2 : Netlify (Alternative gratuite)

### 1. Deploy via CLI

```bash
# Installe Netlify CLI
npm install -g netlify-cli

# Login
netlify login

# Build
npm run build

# Deploy
netlify deploy --prod --dir=dist
```

### 2. Ou via GitHub

1. Va sur [netlify.com](https://netlify.com)
2. "Import from Git"
3. Sélectionne ton repo
4. Configure :
   - **Base directory**: `frontend`
   - **Build command**: `npm run build`
   - **Publish directory**: `frontend/dist`
5. Ajoute les env vars
6. Deploy

---

## 🔧 Troubleshooting

### Dashboard ne se connecte pas à l'API

- Vérifie que `VITE_API_URL` est correct dans Vercel
- Vérifie les CORS dans `api/main.py` (ajoute ton domaine Vercel)
- Check les logs de l'API

### WebSocket ne se connecte pas

- Vérifie que `VITE_WS_URL` utilise `wss://` (pas `ws://`)
- Check que nginx forward bien les WebSockets
- Vérifie les logs du navigateur (F12 > Console)

### Build échoue sur Vercel

- Check que `package.json` est bien dans `frontend/`
- Vérifie que Root Directory = `frontend`
- Check les logs de build

---

## 📊 Résultat final

✅ Dashboard : `https://polyinsider.vercel.app`  
✅ API : `https://api.polyinsider.com` (ou Railway/Render)  
✅ WebSocket : `wss://api.polyinsider.com/ws/trades`  
✅ Auto-deploy sur git push

---

## 💰 Coûts

- **Vercel** : Gratuit (100GB bandwidth/mois)
- **Netlify** : Gratuit (100GB bandwidth/mois)
- **Railway** : Gratuit ($5 credit/mois)
- **Render** : Gratuit (750h/mois)
- **VPS** : $5-10/mois (Digital Ocean, Hetzner)

**Total pour setup gratuit : $0/mois** 🎉
