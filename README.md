# FUCHIACCIONES

Daily market intelligence dashboard for the user's investment universe.

## V1
- Full instrument universe (stocks, ETFs, ETNs and other listed instruments supplied by the user)
- Daily recommendations, opportunities and alerts
- 30-day performance vs previous 30-day period
- 800-trading-day historical context and anomaly detection
- Market dashboard
- Company/news/report placeholders ready for data providers
- Daily GitHub Actions job at 09:00 UTC
- GitHub Pages static publication

## Data
V1 uses Yahoo Finance's publicly accessible chart endpoint for historical OHLCV where available. Yahoo Finance does not provide a supported public developer API, so the ingestion layer is deliberately isolated and rate-limited for future replacement with a licensed provider if needed.

## Deployment
Enable GitHub Pages with **GitHub Actions** as the source. The workflow builds `public/` and deploys it automatically.
