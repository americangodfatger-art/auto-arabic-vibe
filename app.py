"""
Auto Arabic Vibe - Stremio Addon
Robust Python Flask server with Android TV Compatibility
"""

import os
import json
import re
import base64
import traceback
from flask import Flask, Response, request, jsonify, make_response, render_template
from flask_cors import CORS

# --- ROBUST IMPORTS ---
try:
    from sources import source_manager
    SOURCES_AVAILABLE = True
except Exception as e:
    print(f"[CRITICAL] Failed to import sources: {e}")
    SOURCES_AVAILABLE = False
    source_manager = None

try:
    from translator import translate_srt_content, batch_translate_srt
    TRANSLATOR_AVAILABLE = True
except Exception as e:
    print(f"[CRITICAL] Failed to import translator: {e}")
    TRANSLATOR_AVAILABLE = False

# Simple in-memory cache for translated subtitles
subtitle_cache = {}


app = Flask(__name__)

# --- GLOBAL CORS ---
CORS(app, resources={r"/*": {"origins": "*"}})


# --- CONSTANTS ---
MANIFEST_ID = "org.stremio.auto-arabic-vibe"
MANIFEST_NAME = "Auto Arabic Vibe"
MANIFEST_VERSION = "1.5.0"

# Language code mapping (2-letter to 3-letter ISO 639-2)
LANG_MAP = {
    'ar': 'ara', 'en': 'eng', 'tr': 'tur', 'fa': 'per', 'ur': 'urd',
    'hi': 'hin', 'bn': 'ben', 'id': 'ind', 'ms': 'msa', 'th': 'tha',
    'vi': 'vie', 'fr': 'fre', 'es': 'spa', 'de': 'ger', 'it': 'ita',
    'pt': 'por', 'ru': 'rus', 'ja': 'jpn', 'ko': 'kor', 'zh-CN': 'chi'
}

# --- HELPER FUNCTIONS ---

def decode_config(config_b64: str) -> dict:
    """Safely decode config - handles URL-safe base64 from install link and path encoding"""
    try:
        if not config_b64 or not config_b64.strip():
            return {'lang': 'ar', 'android': True}
        s = config_b64.strip()
        # Restore URL-safe base64 to standard: - -> +, _ -> /
        s = s.replace('-', '+').replace('_', '/').replace(' ', '+')
        pad = 4 - (len(s) % 4)
        if pad != 4:
            s += '=' * pad
        json_str = base64.b64decode(s).decode('utf-8')
        return json.loads(json_str)
    except Exception:
        return {'lang': 'ar', 'android': True}


def get_base_url():
    """Determine robust base URL with HTTPS support"""
    scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
    host = request.headers.get('Host', request.host)
    base = f"{scheme}://{host}"
    # Force HTTPS for cloud deployments
    if 'railway' in base or 'fly.dev' in base or 'render' in base or 'koyeb' in base:
        base = base.replace('http://', 'https://')
    return base


def get_manifest(config: dict = None) -> dict:
    """Generate Manifest - Stremio addon protocol v3"""
    if config is None:
        config = {'lang': 'ar', 'android': True}
    
    lang = config.get('lang', 'ar')
    lang_name = {
        'ar': 'Arabic', 'tr': 'Turkish', 'fa': 'Persian', 'ur': 'Urdu',
        'hi': 'Hindi', 'bn': 'Bengali', 'id': 'Indonesian', 'ms': 'Malay',
        'th': 'Thai', 'vi': 'Vietnamese', 'fr': 'French', 'es': 'Spanish',
        'de': 'German', 'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian',
        'ja': 'Japanese', 'ko': 'Korean', 'zh-CN': 'Chinese'
    }.get(lang, lang.upper())
    
    import time
    timestamp = int(time.time())
    
    return {
        "id": MANIFEST_ID,
        "version": MANIFEST_VERSION,
        "name": f"{MANIFEST_NAME} ({lang_name})",
        "description": f"Auto-translate English subtitles to {lang_name} (Build: {timestamp}). Works on Android TV and all Stremio clients.",
        "logo": "https://i.imgur.com/QJmP3GF.png",
        "background": "https://i.imgur.com/Ke5D6l3.jpg",
        "resources": [
            {"name": "subtitles", "types": ["movie", "series"], "idPrefixes": ["tt"]}
        ],
        "types": ["movie", "series"],
        "catalogs": [],
        "idPrefixes": ["tt"],
        "behaviorHints": {
            "configurable": True,
            "configurationRequired": False,
            "configurationLocation": f"{get_base_url()}/configure"
        }
    }


def srt_to_vtt(srt_content: str) -> str:
    """Convert SRT content to WebVTT (for clients that prefer VTT)."""
    if not srt_content or not srt_content.strip():
        return "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nNo content.\n\n"
    lines = srt_content.replace('\r\n', '\n').strip().split('\n')
    out = ['WEBVTT', '']
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r'^\d+$', line.strip()) and i + 2 < len(lines):
            # timestamp line: 00:00:01,000 --> 00:00:05,000 -> 00:00:01.000 --> 00:00:05.000
            ts = lines[i + 1].strip().replace(',', '.')
            out.append(ts)
            i += 2
            text = []
            while i < len(lines) and lines[i].strip():
                text.append(lines[i])
                i += 1
            out.append('\n'.join(text))
            out.append('')
        i += 1
    return '\n'.join(out).strip() + '\n\n'


def create_response(content: str, is_error: bool = False) -> Response:
    """
    Create a Robust Response for Android TV
    """
    if not content:
        content = "1\n00:00:01,000 --> 00:00:05,000\nNo content available.\n\n"

    # Add error prefix if needed
    if is_error and "Error" not in content:
        content = "1\n00:00:01,000 --> 00:00:05,000\n[Error] Content unavailable.\n\n" + content

    # Normalize newlines
    content = content.replace('\r\n', '\n').strip() + '\n\n'

    # UTF-8 BOM for Arabic support
    encoded = content.encode('utf-8-sig')

    response = Response(encoded, status=200, mimetype='application/x-subrip')
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Content-Disposition'] = 'inline; filename="subtitle.srt"'
    return response


def create_vtt_response(content: str, is_error: bool = False) -> Response:
    """Create WebVTT response for clients that prefer VTT."""
    vtt = srt_to_vtt(content) if content else "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nNo content.\n\n"
    if is_error:
        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\n[Error] " + (content or "Unavailable") + "\n\n"
    encoded = vtt.encode('utf-8-sig')
    r = Response(encoded, status=200, mimetype='text/vtt')
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Content-Disposition'] = 'inline; filename="subtitle.vtt"'
    return r


# --- ROUTES ---

@app.route('/')
@app.route('/configure')
@app.route('/<config>/configure')
def configure_page(config=None):
    """Configuration page - must be accessed from a browser"""
    print(f"[INFO] /configure called, config={config}")
    return render_template('index.html')


@app.route('/manifest.json', methods=['GET', 'OPTIONS'])
def manifest_base():
    """Base Manifest - default Arabic translation"""
    if request.method == 'OPTIONS':
        return _cors_preflight()
    print("[INFO] /manifest.json called (default)")
    resp = jsonify(get_manifest())
    return _add_no_cache_cors(resp)


@app.route('/<config>/manifest.json', methods=['GET', 'OPTIONS'])
def manifest_dynamic(config):
    """Dynamic Manifest with configuration"""
    if request.method == 'OPTIONS':
        return _cors_preflight()
    print(f"[INFO] /manifest.json called with config={config}")
    cfg = decode_config(config)
    resp = jsonify(get_manifest(cfg))
    return _add_no_cache_cors(resp)


def _cors_preflight():
    r = make_response('', 204)
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    r.headers['Access-Control-Max-Age'] = '86400'
    return r


def _add_no_cache_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Content-Type'] = 'application/json; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/subtitles/<content_type>/<id>.json', methods=['GET', 'OPTIONS'])
def subtitles_base(content_type, id):
    """Base Subtitles - default Arabic"""
    if request.method == 'OPTIONS':
        return _cors_preflight()
    return subtitles_handler("", content_type, id)


@app.route('/<config>/subtitles/<content_type>/<id>.json', methods=['GET', 'OPTIONS'])
def subtitles_dynamic(config, content_type, id):
    """Dynamic Subtitles with configuration"""
    if request.method == 'OPTIONS':
        return _cors_preflight()
    return subtitles_handler(config, content_type, id)


def subtitles_handler(config, content_type, id):
    """
    CRITICAL: Subtitle Handler for Stremio
    Returns list of available subtitles - only real subtitles (no status entry)
    """
    # Support videoId from extraArgs (e.g. Android TV / some clients)
    video_id = request.args.get('videoId') or request.args.get('id') or id
    if isinstance(video_id, str) and video_id:
        id = video_id
    print(f"[INFO] /subtitles called: type={content_type}, id={id}, config={config}")
    
    response_subs = []

    try:
        # Decode config
        cfg = decode_config(config)
        lang = cfg.get('lang', 'ar')
        lang_iso3 = LANG_MAP.get(lang, 'ara')
        
        # Parse IMDB ID - format: tt1234567 or tt1234567:1:2 (for series)
        parts = str(id).split(':')
        real_id = parts[0]  # tt1234567
        season = int(parts[1]) if len(parts) >= 2 else None
        episode = int(parts[2]) if len(parts) >= 3 else None

        print(f"[INFO] Looking for subtitles: {real_id} S{season}E{episode} -> {lang}")

        # Validate IMDB ID format
        if not real_id.startswith('tt'):
            print(f"[WARN] Invalid IMDB ID format: {real_id}")
            return make_subtitle_response([])

        # Build the subtitle URL - use base URL for proper HTTPS
        base_url = get_base_url()
        if config:
            subtitle_url = f"{base_url}/{config}/stream/{content_type}/{id}/sub.srt"
        else:
            subtitle_url = f"{base_url}/stream/{content_type}/{id}/sub.srt"

        # Fetch English subtitles from sources
        english_srt = None
        if SOURCES_AVAILABLE and source_manager:
            try:
                english_srt = source_manager.get_first_subtitle(real_id, content_type, season, episode)
            except Exception as e:
                print(f"[ERROR] Source search failed: {e}")
        else:
            print("[WARN] Sources unavailable")

        if not english_srt:
            print(f"[INFO] No English subtitles found for {real_id}")
            # Return empty - no subtitle available
            return make_subtitle_response([])

        print(f"[INFO] Found English subtitle ({len(english_srt)} chars)")

        # Language display names with flags
        lang_names = {
            'ar': 'Arabic',
            'tr': 'Turkish', 
            'fa': 'Persian',
            'ur': 'Urdu',
            'hi': 'Hindi',
            'fr': 'French',
            'es': 'Spanish',
            'de': 'German',
            'ru': 'Russian',
        }
        lang_name = lang_names.get(lang, lang.upper())

        # Create subtitle entry - Stremio protocol (id, url, lang required)
        response_subs.append({
            "id": f"aav-{lang}-{real_id}",
            "url": subtitle_url,
            "lang": lang_iso3,
            "name": f"Auto Arabic Vibe ({lang_name})"
        })

        print(f"[INFO] Returning {len(response_subs)} subtitle(s)")
        return make_subtitle_response(response_subs)

    except Exception as e:
        print(f"[ERROR] Subtitle handler failed: {e}")
        traceback.print_exc()
        return make_subtitle_response([])


def make_subtitle_response(subtitles):
    """Create proper JSON response for Stremio subtitle protocol"""
    resp = jsonify({"subtitles": subtitles})
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Content-Type'] = 'application/json; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/stream/<content_type>/<id>/sub.srt')
def stream_subtitle_base(content_type, id):
    """Stream subtitle - default Arabic"""
    return stream_subtitle_handler(None, content_type, id, fmt='srt')


@app.route('/<config>/stream/<content_type>/<id>/sub.srt')
def stream_subtitle_config(config, content_type, id):
    """Stream subtitle with config"""
    return stream_subtitle_handler(config, content_type, id, fmt='srt')


@app.route('/stream/<content_type>/<id>/sub.vtt')
def stream_subtitle_vtt_base(content_type, id):
    """Stream subtitle as WebVTT"""
    return stream_subtitle_handler(None, content_type, id, fmt='vtt')


@app.route('/<config>/stream/<content_type>/<id>/sub.vtt')
def stream_subtitle_vtt_config(config, content_type, id):
    """Stream subtitle as WebVTT with config"""
    return stream_subtitle_handler(config, content_type, id, fmt='vtt')


def stream_subtitle_handler(config, content_type, id, fmt='srt'):
    """
    CRITICAL: Stream the translated subtitle file (SRT or WebVTT)
    """
    print(f"[INFO] /stream called for {content_type} {id} fmt={fmt}")
    try:
        cfg = decode_config(config)
        lang = cfg.get('lang', 'ar')
        
        parts = id.split(':')
        real_id = parts[0]
        season = int(parts[1]) if len(parts) >= 2 else None
        episode = int(parts[2]) if len(parts) >= 3 else None

        def respond(srt_content: str, is_err: bool = False):
            if fmt == 'vtt':
                return create_vtt_response(srt_content, is_error=is_err)
            return create_response(srt_content, is_error=is_err)

        # Check cache first
        cache_key = f"{real_id}:{season}:{episode}:{lang}"
        if cache_key in subtitle_cache:
            print(f"[INFO] Cache hit for {cache_key}")
            return respond(subtitle_cache[cache_key])

        # Get English subtitle
        if not SOURCES_AVAILABLE or not source_manager:
            return respond("Subtitle sources unavailable", is_err=True)

        english_srt = source_manager.get_first_subtitle(real_id, content_type, season, episode)

        if not english_srt:
            return respond("No English subtitles found", is_err=True)

        print(f"[INFO] Got English subtitle ({len(english_srt)} chars), translating to {lang}")

        # Translate to target language using batch translation (faster)
        if TRANSLATOR_AVAILABLE:
            try:
                translated = batch_translate_srt(english_srt, lang)
                if translated and len(translated) > 50:
                    print(f"[INFO] Translation successful ({len(translated)} chars)")
                    # Cache the result (limit cache size)
                    if len(subtitle_cache) > 100:
                        subtitle_cache.clear()
                    subtitle_cache[cache_key] = translated
                    return respond(translated)
            except Exception as e:
                print(f"[ERROR] Translation failed: {e}")
                traceback.print_exc()

        # Fallback to English if translation fails
        print("[WARN] Returning English subtitle as fallback")
        return respond(english_srt)

    except Exception as e:
        print(f"[ERROR] Stream handler failed: {e}")
        traceback.print_exc()
        return create_response(f"Error: {e}", is_error=True) if fmt == 'srt' else create_vtt_response(f"Error: {e}", is_error=True)

@app.route('/health/status.srt')
def status_subtitle_stream():
    """Returns a hardcoded 'Active' subtitle file"""
    content = "1\n00:00:01,000 --> 00:00:10,000\n✅ Addon Status: Active\n\n"
    return create_response(content)


# --- HEALTH CHECK ---
@app.route('/health')
def health_check():
    """Health check endpoint"""
    status = {
        "status": "ok",
        "version": MANIFEST_VERSION,
        "sources": SOURCES_AVAILABLE,
        "translator": TRANSLATOR_AVAILABLE
    }
    return jsonify(status)


@app.route('/test/<imdb_id>')
def test_subtitle(imdb_id):
    """Debug endpoint to test subtitle fetching"""
    result = {
        "imdb_id": imdb_id,
        "sources_available": SOURCES_AVAILABLE,
        "translator_available": TRANSLATOR_AVAILABLE,
        "subtitle_found": False,
        "subtitle_length": 0,
        "error": None
    }
    
    try:
        if SOURCES_AVAILABLE and source_manager:
            srt = source_manager.get_first_subtitle(imdb_id, "movie", None, None)
            if srt:
                result["subtitle_found"] = True
                result["subtitle_length"] = len(srt)
                result["preview"] = srt[:500] if len(srt) > 500 else srt
        else:
            result["error"] = "Sources not available"
    except Exception as e:
        result["error"] = str(e)
    
    return jsonify(result)


# --- BOOTSTRAP ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    print(f"[INFO] Starting Auto Arabic Vibe on port {port}")
    print(f"[INFO] Sources available: {SOURCES_AVAILABLE}")
    print(f"[INFO] Translator available: {TRANSLATOR_AVAILABLE}")
    app.run(host="0.0.0.0", port=port)
