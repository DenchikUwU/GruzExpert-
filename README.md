# GruZExpert

Responsive static frontend for GruZExpert with a Python API for orders, reviews, administrator access and Telegram notifications.

## Render architecture
- Deploy the frontend as a Render Static Site (Publish Directory `.`).
- Deploy `server.py` as a separate Render Web Service (`pip install -r requirements.txt`, `python server.py`).
- Create a Render PostgreSQL database and set its Internal Database URL as `DATABASE_URL` on the Web Service.
- Set `GRUZEXPERT_ADMIN_KEY`, `ALLOWED_ORIGINS`, and optionally `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in the Web Service Environment.
- Set `apiBaseUrl` in `config.js` to the API Web Service URL and push that change to GitHub.
- Detailed steps are in `render-deploy-guide.txt`.

## Local run
Install requirements with `pip install -r requirements.txt`, set `GRUZEXPERT_ADMIN_KEY` in your shell, and run `python server.py`. Without `DATABASE_URL`, local JSON storage is used under `data/`; on Render this fallback is not durable unless a persistent disk is configured.
