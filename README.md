# Nexa Search

A working search engine frontend + backend, powered by the Brave Search API.

## How it's structured

```
nexa-search/
├── backend/
│   ├── main.py            # FastAPI server — calls Brave Search, caches, rate-limits
│   ├── requirements.txt   # Python dependencies
│   └── .env.example       # Copy to .env and add your API key
└── frontend/
    └── index.html         # Your search UI, wired to call the backend
```

## Setup

### 1. Get a Brave Search API key
Sign up for free at https://api.search.brave.com/register
(Free tier: 2,000 queries/month at time of writing — check current limits on their site.)

### 2. Configure the backend
```bash
cd backend
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then open .env and paste in your real API key
```

### 3. Run the backend
```bash
uvicorn main:app --reload --port 8000
```
Leave this running. Check it's working by visiting:
http://127.0.0.1:8000/api/health

You should see `{"status":"ok","api_key_configured":true}`.

### 4. Run the frontend
Just open `frontend/index.html` in your browser (double-click it, or use
a simple local server like `python -m http.server` inside the `frontend/` folder).

Search something — it will call your backend, which calls Brave, and
real results will render in your existing UI.

## How it works

- **Your API key never touches the browser.** The frontend only talks to
  your own backend; the backend holds the key server-side.
- **Caching**: identical queries are cached for 5 minutes in memory, so
  repeated searches don't burn your API quota.
- **Rate limiting**: each IP is capped at 20 requests/minute to prevent
  abuse from burning through your quota.

## Deploying it for real (beyond localhost)

- **Backend**: deploy to Railway, Render, Fly.io, or a small VPS. Set
  `BRAVE_API_KEY` as an environment variable in that platform's dashboard
  (don't upload your `.env` file).
- **Frontend**: deploy `index.html` anywhere static (Vercel, Netlify,
  Cloudflare Pages, GitHub Pages). Update the `API_BASE` constant near
  the top of the `<script>` tag in `index.html` to point at your deployed
  backend's URL instead of `http://127.0.0.1:8000`.
- **CORS**: in `backend/main.py`, replace `allow_origins=["*"]` with your
  actual frontend domain once deployed, so random sites can't ride on
  your backend and quota.

## Next steps / ideas

- Add image and news result tabs (Brave's API supports separate endpoints)
- Add pagination ("load more results")
- Swap in Redis instead of in-memory caching if you deploy multiple backend instances
- Add an AI-generated summary at the top of results using the Claude API
