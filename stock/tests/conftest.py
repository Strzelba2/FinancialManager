from __future__ import annotations

import os


# Unit tests should not depend on developer-local .env files being present in CI.
os.environ.setdefault("ST_BASE_URL", "https://quotes.example")
os.environ.setdefault("ST_BASE_URL_ALT", "https://quotes-alt.example/markets/stocks")
