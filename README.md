# GruZExpert

Responsive website for cargo transport and moving services. Lithuanian is the default language; Russian and English are built in.

## Start locally

```sh
GRUZEXPERT_ADMIN_KEY='choose-a-long-private-key' python3 server.py
```

Open `http://localhost:8000`. Orders are stored in `data/orders.json`. The protected order-management page is `/admin.html`.

## Send an email for every order

Email delivery is optional; saving an order never depends on it. Configure the following environment variables at deployment:

```sh
GRUZEXPERT_ADMIN_KEY='choose-a-long-private-key'
ORDER_RECIPIENT='your-email@example.com'
SMTP_HOST='smtp.example.com'
SMTP_PORT='465'
SMTP_USER='your-smtp-login'
SMTP_PASSWORD='your-smtp-password'
SMTP_FROM='orders@example.com'
python3 server.py
```

## Before publishing

1. Replace the temporary hero and map background images in `config.js` with the company's licensed photos.
2. Replace the temporary phone number and email in `config.js` with the business contacts.
3. Set a long `GRUZEXPERT_ADMIN_KEY` on the hosting server. Do not put this secret in the website files.
4. Configure HTTPS and SMTP in the hosting provider's environment settings.
