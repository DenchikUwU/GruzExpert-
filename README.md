# GruZExpert

Responsive website for cargo transport and moving services. Lithuanian is the default language; Russian and English are built in. Orders and reviews are saved locally as JSON files.

## Start locally

```sh
cp .env.example .env
# Enter the real settings in .env, then:
python3 server.py
```

Open `http://localhost:8000`. Orders are stored in `data/orders.json`; reviews in `data/reviews.json`. The protected order-management page is `/admin.html`.

## Send an email for every order

Email and SMS are sent only after the private `.env` settings have been completed. Copy `.env.example` to `.env`, add the real recipient email, company phone, SMTP details and Twilio details. The website never exposes these credentials to visitors.

```sh
cp .env.example .env
# Edit .env, then run:
python3 server.py
```

## Before publishing

1. Add the real phone and public email in `config.js`.
2. Fill in `.env` with a long `GRUZEXPERT_ADMIN_KEY`. The recipient e-mail and company phone are prefilled for GruZExpert; change them only if needed.
3. Add SMTP settings to receive an e-mail for each order, and Twilio settings to receive the order by SMS and automatically confirm it to the customer.
4. Configure HTTPS in the hosting provider's environment settings.
