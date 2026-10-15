GruzExpert Static API URL fix

This patch changes only app.js and admin.html so the static site calls the existing Python API service at https://gruzexpert-api-0hdd.onrender.com. It does not replace server.py and does not change Telegram notification logic.

IMPORTANT: cross-origin API requests require CORS support in the deployed Web Service. If CORS is not already enabled, browser requests from https://gruzexpert.onrender.com will be blocked. Add CORS response headers for origin https://gruzexpert.onrender.com, methods GET, POST, DELETE, OPTIONS, and headers Content-Type, X-Admin-Key; implement OPTIONS responses (204). Do not replace the deployed server.py with a different version.

Apply only app.js and admin.html to the Static Site GitHub repository. Keep a copy of both original files first. Test a real order after deployment; it should arrive in Telegram. Admin login should list orders stored by the same API service.
