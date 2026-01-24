# Auto Arabic Vibe - Stremio Addon 🇸🇦

Automatically translates English subtitles to Arabic on-the-fly. **Optimized for Android TV compatibility.**

## Features

- ✅ **Android TV Compatible** - Uses Compatibility Mode (direct stream, strict MIME types)
- ✅ **OpenSubtitles v3** - High-quality English subtitle fetching
- ✅ **Auto Translation** - English → Arabic using googletrans
- ✅ **UTF-8 Encoding** - Perfect Arabic character rendering
- ✅ **Stateless** - No database required

## Quick Start

```bash
cd auto-arabic-vibe
pip install -r requirements.txt
python app.py
```

Server runs at `http://localhost:5000`

## Install in Stremio

1. Open Stremio
2. Go to **Addons** → Search bar
3. Enter: `http://localhost:5000/manifest.json`
4. Click **Install**

## Android TV Compatibility Mode

This addon implements the "Subtito" compatibility fix:

| Feature | Implementation |
|---------|---------------|
| MIME Type | `application/x-subrip` (strict) |
| Streaming | Direct content (no 302 redirects) |
| Encoding | `UTF-8` with BOM for Arabic |
| CORS | `Access-Control-Allow-Origin: *` |

## Environment Variables

```bash
# Optional: OpenSubtitles API key for better results
export OPENSUBTITLES_API_KEY=your_key

# Port (default: 5000)  
export PORT=5000
```

## Deploy to Cloud

### Railway
```bash
railway init
railway up
```

### Render
Use the Dockerfile or connect GitHub repo.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/manifest.json` | Addon manifest |
| `/subtitles/{type}/{id}.json` | Subtitle search |
| `/subtitle/{type}/{id}/arabic.srt` | Direct SRT stream |
| `/health` | Health check |
