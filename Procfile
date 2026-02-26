# Heroku Procfile - Two processes:
# 1. web: FastAPI API (public endpoint, /docs, /health)
# 2. bot: Main trading bot loop (background worker)

web: uvicorn api.main:app --host 0.0.0.0 --port $PORT
bot: python main.py
