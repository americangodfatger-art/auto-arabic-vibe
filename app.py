"""
Auto Arabic Vibe - Stremio Addon (FAIL-SAFE EDITION)
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
    from translator import translate_srt_content
    TRANSLATOR_AVAILABLE = True
except Exception as e:
    print(f"[CRITICAL] Failed to import translator: {e}")
    TRANSLATOR_AVAILABLE = False


app = Flask(__name__)

# --- GLOBAL CORS ---
CORS(app, resources={r"/*": {"origins": "*"}})


# --- CONSTANTS ---
MANIFEST_ID = "org.stremio.auto-arabic-vibe"
MANIFEST_NAME = "Auto Arabic Vibe"
# --- CONSTANTS ---
MANIFEST_ID = "org.stremio.auto-arabic-vibe"
MANIFEST_NAME = "Auto Arabic Vibe"

# --- HELPER FUNCTIONS ---

def decode_config(config_b64: str) -> dict:
    """Safely decode config"""
    try:
        if not config_b64:
            return {'lang': 'ar', 'android': True}
        
        json_str = base64.b64decode(config_b64).decode('utf-8')
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


def get_manifest(config: dict = None, config_url: str = None) -> dict:
    """Generate Manifest"""
    if config is None:
        config = {'lang': 'ar', 'android': True}
    
    # Default to dynamic if not provided (fallback)
    if not config_url:
        config_url = f"{get_base_url()}/configure"
        
    return {
        "id": MANIFEST_ID,
        "version": "1.3.0",
        "name": MANIFEST_NAME,
        "description": "Auto Arabic Vibe - DEBUG BUILD",
        "logo": "https://i.imgur.com/QJmP3GF.png",
        "background": "https://i.imgur.com/Ke5D6l3.jpg",
        "resources": ["subtitles"],
        "types": ["movie", "series"],
        "catalogs": [],
        "idPrefixes": ["tt"],
        "behaviorHints": {
            "configurable": True,
            "configurationRequired": False,
            "configurationLocation": config_url
        }
    }


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


# --- ROUTES ---

@app.route('/')
@app.route('/configure')
def configure_page():
    print("[DEBUG] /configure called")
    return render_template('index.html')


@app.route('/manifest.json')
def manifest_base():
    """Base Manifest"""
    print("[DEBUG] /manifest.json called")
    config_url = f"{get_base_url()}/configure"
    return jsonify(get_manifest(config_url=config_url))


@app.route('/<config>/manifest.json')
def manifest_dynamic(config):
    """Dynamic Manifest"""
    print(f"[DEBUG] /manifest.json called with config={config}")
    cfg = decode_config(config)
    config_url = f"{get_base_url()}/configure"
    return jsonify(get_manifest(cfg, config_url=config_url))


@app.route('/subtitles/<type>/<id>.json')
def subtitles_base(type, id):
    """Base Subtitles"""
    return subtitles_dynamic("", type, id)


@app.route('/<config>/subtitles/<type>/<id>.json')
def subtitles_dynamic(config, type, id):
    """
    CRITICAL: Subtitle Handler (DEBUG Mode)
    """
    print(f"[DEBUG] /subtitles called with type={type}, id={id}, config={config}")

    # FORCE VISIBILITY TEST SUBTITLE
    test_sub = {
        "id": "debug_visible",
        "url": "https://raw.githubusercontent.com/MZaFaRM/subtitles/master/test.srt",
        "lang": "ara",
        "langISO": "ara",  # Stremio legacy
        "name": "[DEBUG] Addon Active (Test)" # Visible text
    }
    
    # Minimal response format
    response_subs = [test_sub]

    try:
        # Decode config
        cfg = decode_config(config)
        lang = cfg.get('lang', 'ar')
        
        # Parse ID safely
        real_id = id.split(':')[0]
        season = None
        episode = None
        
        parts = id.split(':')
        if len(parts) >= 2: season = int(parts[1])
        if len(parts) >= 3: episode = int(parts[2])

        print(f"[DEBUG] Processing subtitles for {real_id} S{season}E{episode} -> {lang}")

        # Fetch English Subtitle
        if SOURCES_AVAILABLE and source_manager:
            english_srt = source_manager.get_first_subtitle(real_id, type, season, episode)
        else:
            english_srt = None
            print("[DEBUG] Sources unavailable")

        if not english_srt:
            print("[DEBUG] No english subtitles found")
            # Only return test sub if no english found
            return jsonify({"subtitles": response_subs})

        # Generate URL for translation
        host = request.host_url.rstrip('/')
        subtitle_url = f"{host}/{config}/stream/{type}/{id}/sub.srt" if config else f"{host}/stream/{type}/{id}/sub.srt"

        response_subs.append({
            "id": f"auto_{lang}_{real_id}",
            "url": subtitle_url,
            "lang": "ara",
            "name": f"🇸🇦 Arabic (Auto-Translate)"
        })

        return jsonify({"subtitles": response_subs})

    except Exception as e:
        print(f"[ERROR] Subtitle Logic Failed: {e}")
        traceback.print_exc()
        # ALWAYS RETURN TEST SUB
        return jsonify({"subtitles": response_subs})


@app.route('/stream/<type>/<id>/sub.srt')
@app.route('/<config>/stream/<type>/<id>/sub.srt')
def stream_subtitle(type, id, config=None):
    """
    CRITICAL: Stream the content.
    """
    print(f"[DEBUG] /stream called for {type} {id}")
    try:
        cfg = decode_config(config)
        lang = cfg.get('lang', 'ar')
        
        real_id = id.split(':')[0]
        season = None
        episode = None
        parts = id.split(':')
        if len(parts) >= 2: season = int(parts[1])
        if len(parts) >= 3: episode = int(parts[2])

        # Gets English
        if not SOURCES_AVAILABLE or not source_manager:
             return create_response("Sources Unavailable", is_error=True)

        english_srt = source_manager.get_first_subtitle(real_id, type, season, episode)

        if not english_srt:
            return create_response("No subtitles found to translate.", is_error=True)

        # Try Translation
        if TRANSLATOR_AVAILABLE:
            try:
                translated = translate_srt_content(english_srt, lang)
                if translated:
                    return create_response(translated)
            except Exception as e:
                print(f"[TRANS ERROR] {e}")

        # Fallback to English
        return create_response(english_srt)

    except Exception as e:
        print(f"[STREAM ERROR] {e}")
        traceback.print_exc()
        return create_response(f"Critical Error: {e}", is_error=True)

# --- BOOTSTRAP ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
