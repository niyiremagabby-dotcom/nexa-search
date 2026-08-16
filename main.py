"""
Nexa Search - Backend API
Handles search requests server-side so the Brave Search API key
is never exposed to the browser. Includes simple in-memory caching
and rate limiting to protect your API quota.
"""

import os
import time
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TAVILY_ENDPOINT = "https://api.tavily.com/search"

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"

# ---- Config ----
CACHE_TTL_SECONDS = 300          # how long to cache identical queries
RATE_LIMIT_PER_MINUTE = 20       # requests allowed per IP per minute

app = FastAPI(title="Nexa Search API")

# Allow your frontend to call this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://nexa-search.netlify.app", "https://niyiremagabby-dotcom.github.io", "http://127.0.0.1:5500", "http://localhost:5500"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ---- Simple in-memory cache: {query: (timestamp, results)} ----
_cache: dict[str, tuple[float, dict]] = {}

# ---- Simple in-memory rate limiter: {ip: [timestamps]} ----
_rate_limit: dict[str, list[float]] = {}


def check_rate_limit(ip: str):
    now = time.time()
    window_start = now - 60
    timestamps = [t for t in _rate_limit.get(ip, []) if t > window_start]
    if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    timestamps.append(now)
    _rate_limit[ip] = timestamps


def get_cached(query: str) -> Optional[dict]:
    entry = _cache.get(query)
    if not entry:
        return None
    timestamp, results = entry
    if time.time() - timestamp > CACHE_TTL_SECONDS:
        del _cache[query]
        return None
    return results


def set_cache(query: str, results: dict):
    _cache[query] = (time.time(), results)


@app.get("/api/search")
async def search(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    type: str = Query("web", description="Result type: web, images, or news"),
):
    if type not in ("web", "images", "news", "videos"):
        raise HTTPException(status_code=400, detail="type must be 'web', 'images', 'news', or 'videos'")

    if type == "videos":
        if not YOUTUBE_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="Server is not configured with a YOUTUBE_API_KEY. See backend/.env.example.",
            )

        client_ip = request.client.host if request.client else "unknown"
        check_rate_limit(client_ip)

        query = q.strip()
        cache_key = f"videos:{query}"
        cached = get_cached(cache_key)
        if cached:
            return {"query": query, "type": "videos", "cached": True, "results": cached}

        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": 10,
            "videoEmbeddable": "true",
            "key": YOUTUBE_API_KEY,
        }

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(YOUTUBE_ENDPOINT, params=params)
            except httpx.RequestError as e:
                raise HTTPException(status_code=502, detail=f"Search provider unreachable: {e}")

        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Search provider error: {resp.text}",
            )

        data = resp.json()
        items = data.get("items", [])
        normalized = [
            {
                "video_id": item.get("id", {}).get("videoId"),
                "title": item.get("snippet", {}).get("title"),
                "channel": item.get("snippet", {}).get("channelTitle"),
                "description": item.get("snippet", {}).get("description"),
                "thumbnail": item.get("snippet", {}).get("thumbnails", {}).get("medium", {}).get("url"),
            }
            for item in items
            if item.get("id", {}).get("videoId")
        ]

        set_cache(cache_key, normalized)
        return {"query": query, "type": "videos", "cached": False, "results": normalized}

    if not TAVILY_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Server is not configured with a TAVILY_API_KEY. See backend/.env.example.",
        )

    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    query = q.strip()
    cache_key = f"{type}:{query}"
    cached = get_cached(cache_key)
    if cached:
        return {"query": query, "type": type, "cached": True, "results": cached}

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": 10,
    }

    if type == "news":
        payload["topic"] = "news"
    elif type == "images":
        payload["include_images"] = True
        payload["include_image_descriptions"] = True
        # Images-only requests don't need the full web results too,
        # but we keep max_results modest since images come as a side list.

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(TAVILY_ENDPOINT, json=payload)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Search provider unreachable: {e}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Search provider error: {resp.text}",
        )

    data = resp.json()

    if type == "images":
        # Tavily returns images as a separate list: [{"url": ..., "description": ...}, ...]
        image_results = data.get("images", [])
        normalized = [
            {
                "url": img.get("url") if isinstance(img, dict) else img,
                "description": img.get("description") if isinstance(img, dict) else None,
            }
            for img in image_results
        ]
    else:
        # Web and news both come back in the "results" list with the same shape.
        web_results = data.get("results", [])
        normalized = [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "description": r.get("content"),
                "published_date": r.get("published_date"),  # only populated for news
            }
            for r in web_results
        ]

    set_cache(cache_key, normalized)
    return {"query": query, "type": type, "cached": False, "results": normalized}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "tavily_configured": bool(TAVILY_API_KEY),
        "youtube_configured": bool(YOUTUBE_API_KEY),
    }
