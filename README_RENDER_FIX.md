# GruZExpert — Render fix

## Deploy

1. Upload the contents of this folder to the root of the GitHub repository's `main` branch (do not upload the ZIP as a single file).
2. In Render, keep the Static Site at `https://gruzexpert.onrender.com` and the Web Service at `https://gruzexpert-api-0hdd.onrender.com`.
3. Web Service Build Command: `pip install -r requirements.txt`
4. Web Service Start Command: `python server.py`
5. Web Service environment variables:
   - `GRUZEXPERT_ADMIN_KEY` — set this to a new strong private admin key.
   - `TELEGRAM_BOT_TOKEN` — your bot token (secret).
   - `TELEGRAM_CHAT_ID` — target chat ID.
   - `DATABASE_URL` — Render PostgreSQL **Internal Database URL**, with database and Web Service in the same region.
6. Redeploy the Web Service and Static Site after committing the files. `config.js` points the frontend at the API service.
7. Open `https://gruzexpert.onrender.com/admin.html` and enter the exact value of `GRUZEXPERT_ADMIN_KEY`.

The API uses PostgreSQL for orders and reviews when `DATABASE_URL` is set. JSON is only used for local development/fallback and is not durable on Render. Existing JSON records are not automatically imported into PostgreSQL; import any needed old records separately before deleting them.

Never put the admin key, Telegram bot token, or database URL in `config.js` or any frontend file.
