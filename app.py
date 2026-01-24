"""
Auto Arabic Vibe - Stremio Addon
Python Flask server with Android TV Compatibility Mode
33 Subtitle Sources with Arabic Translation
With Configuration Page and Dynamic Routing

FIXES APPLIED:
1. Added /configure route alias
2. Test subtitle always returned first
3. Better ID parsing (strips :season:episode)
4. Enhanced logging throughout
5. Fallback to English on translation failure
6. Robust error handling
"""

import os
import json
import re
import base64
import traceback
from flask import Flask, Response, request, jsonify, make_response, render_template
from flask_cors import CORS

# Import with error handling
try:
    from sources import source_manager
    SOURCES_AVAILABLE = True
except Exception as e:
    print(f"[STARTUP ERROR] Failed to import sources: {e}")
    SOURCES_AVAILABLE = False
    source_manager = None

try:
    from translator import translate_srt_content, batch_translate_srt
    TRANSLATOR_AVAILABLE = True
except Exception as e:
    print(f"[STARTUP ERROR] Failed to import translator: {e}")
    TRANSLATOR_AVAILABLE = False

app = Flask(__name__)

# Enable CORS for all routes with explicit settings (required for Stremio)
CORS(app, 
     resources={r"/*": {"origins": "*"}},
     allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin"],
     methods=["GET", "POST", "OPTIONS", "HEAD"],
     supports_credentials=False,
     expose_headers=["Content-Type", "Content-Length", "Content-Disposition"])

# Load base manifest
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), 'manifest.json')
try:
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        BASE_MANIFEST = json.load(f)
except Exception as e:
    print(f"[STARTUP ERROR] Failed to load manifest: {e}")
    BASE_MANIFEST = {
        "id": "org.stremio.auto-arabic-vibe",
        "version": "1.0.0",
        "name": "Auto Arabic Vibe",
        "description": "Auto translate subtitles",
        "resources": ["subtitles"],
        "types": ["movie", "series"],
        "catalogs": [],
        "idPrefixes": ["tt"],
        "behaviorHints": {
            "configurable": True, 
            "configurationRequired": False,
            "configurationLocation": "https://auto-arabic-vibe.fly.dev/configure"
        }
    }

# Cache for translated subtitles (in-memory, stateless per restart)
subtitle_cache = {}

# Language names mapping
LANGUAGE_NAMES = {
    'ar': ('Arabic', 'العربية', 'ara'),
    'tr': ('Turkish', 'Türkçe', 'tur'),
    'fa': ('Persian', 'فارسی', 'per'),
    'ur': ('Urdu', 'اردو', 'urd'),
    'hi': ('Hindi', 'हिन्दी', 'hin'),
    'bn': ('Bengali', 'বাংলা', 'ben'),
    'id': ('Indonesian', 'Indonesia', 'ind'),
    'ms': ('Malay', 'Melayu', 'may'),
    'th': ('Thai', 'ไทย', 'tha'),
    'vi': ('Vietnamese', 'Tiếng Việt', 'vie'),
    'fr': ('French', 'Français', 'fre'),
    'es': ('Spanish', 'Español', 'spa'),
    'de': ('German', 'Deutsch', 'ger'),
    'it': ('Italian', 'Italiano', 'ita'),
    'pt': ('Portuguese', 'Português', 'por'),
    'ru': ('Russian', 'Русский', 'rus'),
    'ja': ('Japanese', '日本語', 'jpn'),
    'ko': ('Korean', '한국어', 'kor'),
    'zh-CN': ('Chinese', '中文', 'chi'),
}


def parse_video_id(content_id: str) -> tuple:
    """
    Parse Stremio video ID to extract IMDB ID, season, and episode
    
    Input formats:
    - tt12345
    - tt12345:1:1
    - tt12345:1:1.json
    
    Returns:
        (imdb_id, season, episode)
    """
    # Remove .json suffix if present
    clean_id = content_id.replace('.json', '').strip()
    
    # Split by colon
    parts = clean_id.split(':')
    
    imdb_id = parts[0] if parts else clean_id
    season = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    episode = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    
    print(f"[ID Parser] Input: '{content_id}' -> IMDB: '{imdb_id}', Season: {season}, Episode: {episode}")
    
    return imdb_id, season, episode


def decode_config(config_b64: str) -> dict:
    """
    Decode Base64 config string to dictionary
    """
    default_config = {'lang': 'ar', 'android': True}
    
    if not config_b64:
        return default_config
    
    try:
        config_json = base64.b64decode(config_b64).decode('utf-8')
        config = json.loads(config_json)
        return {
            'lang': config.get('lang', 'ar'),
            'android': config.get('android', True)
        }
    except Exception as e:
        print(f"[Config] Decode error: {e}")
        return default_config


def get_manifest_for_config(config: dict) -> dict:
    """
    Generate manifest with config-specific settings
    """
    manifest = BASE_MANIFEST.copy()
    
    # Update behavior hints to show it's configurable
    manifest['behaviorHints'] = {
        'configurable': True,
        'configurationRequired': False,
        'configurationLocation': "https://auto-arabic-vibe.fly.dev/configure"
    }
    
    # Update name based on language
    lang_code = config.get('lang', 'ar')
    if lang_code in LANGUAGE_NAMES:
        lang_name, lang_native, _ = LANGUAGE_NAMES[lang_code]
        manifest['name'] = f"Auto Translate - {lang_native}"
        manifest['description'] = f"Translates English subtitles to {lang_name} on-the-fly. {'Android TV compatible.' if config.get('android') else ''}"
    
    return manifest


def validate_srt(content: str) -> str:
    """
    Validate and fix SRT format for Android compatibility
    """
    if not content:
        return ""
    
    # Normalize line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    
    # Split into blocks
    blocks = re.split(r'\n\s*\n', content.strip())
    valid_blocks = []
    
    for i, block in enumerate(blocks):
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        
        try:
            index = lines[0].strip()
            if not index.isdigit():
                index = str(len(valid_blocks) + 1)
            
            timestamp = lines[1].strip()
            if '-->' not in timestamp:
                continue
            
            text = '\n'.join(lines[2:]).strip()
            if not text:
                continue
            
            valid_blocks.append(f"{len(valid_blocks) + 1}\n{timestamp}\n{text}")
        
        except Exception:
            continue
    
    return '\n\n'.join(valid_blocks) + '\n'


def create_subtitle_response(content: str, format_type: str = 'srt', android_mode: bool = True) -> Response:
    """
    Create response with Android TV Compatibility Mode
    """
    if android_mode:
        validated_content = validate_srt(content)
        encoded_content = validated_content.encode('utf-8-sig')
    else:
        validated_content = content
        encoded_content = validated_content.encode('utf-8')
    
    if format_type == 'vtt':
        mime_type = 'text/vtt; charset=utf-8'
    elif android_mode:
        mime_type = 'application/x-subrip; charset=utf-8'
    else:
        mime_type = 'text/plain; charset=utf-8'
    
    response = Response(
        encoded_content,
        status=200,
        mimetype=mime_type
    )
    
    response.headers['Content-Type'] = mime_type
    response.headers['Content-Disposition'] = 'inline; filename="subtitle.srt"'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    
    if android_mode:
        response.headers['X-Content-Type-Options'] = 'nosniff'
    
    return response


def get_test_subtitle() -> dict:
    """
    Return a test subtitle to verify addon connectivity
    """
    return {
        "id": "test-connection-ok",
        "url": "data:application/x-subrip;base64,MQowMDowMDowMSwwMDAgLS0+IDAwOjAwOjA1LDAwMApbVGVzdF0gQXV0by1BcmFiaWMgQ29ubmVjdGlvbiBPSy4KQ29ubmVjdGVkIFN1Y2Nlc3NmdWxseSEKCg==",
        "lang": "ara",
        "name": "✅ [Test] Auto-Arabic Connection OK"
    }


# ============== ROUTES ==============

@app.route('/')
def index():
    """Configuration page - modern HTML landing page"""
    print("[Route] / - Serving config page")
    return render_template('index.html')


@app.route('/configure')
def configure():
    """Alias for configuration page (for Stremio TV Configure button)"""
    print("[Route] /configure - Serving config page")
    return render_template('index.html')


@app.route('/manifest.json')
def manifest_default():
    """Default manifest (Arabic, Android mode on)"""
    print("[Route] /manifest.json - Serving default manifest")
    config = {'lang': 'ar', 'android': True}
    manifest = get_manifest_for_config(config)
    response = jsonify(manifest)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@app.route('/<config_b64>/manifest.json')
def manifest_with_config(config_b64: str):
    """Dynamic manifest with user config"""
    config = decode_config(config_b64)
    print(f"[Route] /{config_b64}/manifest.json - Config: {config}")
    manifest = get_manifest_for_config(config)
    response = jsonify(manifest)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@app.route('/subtitles/<content_type>/<content_id>.json')
def subtitles_handler(content_type: str, content_id: str):
    """Default subtitle handler (Arabic, Android mode on)"""
    print(f"[Route] /subtitles/{content_type}/{content_id}.json")
    return subtitles_with_config('', content_type, content_id)


@app.route('/<config_b64>/subtitles/<content_type>/<content_id>.json')
def subtitles_with_config(config_b64: str, content_type: str, content_id: str):
    """
    Config-aware subtitle handler
    Returns list of available subtitles including a TEST subtitle
    """
    config = decode_config(config_b64) if config_b64 else {'lang': 'ar', 'android': True}
    lang_code = config.get('lang', 'ar')
    
    # LOGGING: Request received
    print(f"=" * 60)
    print(f"[Subtitle Request] Type: {content_type}, ID: {content_id}, Lang: {lang_code}")
    
    try:
        # Parse content ID properly
        imdb_id, season, episode = parse_video_id(content_id)
        
        # Generate subtitle URL
        base_url = request.host_url.rstrip('/')
        
        if config_b64:
            subtitle_url = f"{base_url}/{config_b64}/subtitle/{content_type}/{content_id}/translated.srt"
        else:
            subtitle_url = f"{base_url}/subtitle/{content_type}/{content_id}/arabic.srt"
        
        # Get language info
        lang_name = 'Arabic'
        lang_flag = '🇸🇦'
        lang_iso = 'ara'
        
        if lang_code in LANGUAGE_NAMES:
            lang_name, lang_native, lang_iso = LANGUAGE_NAMES[lang_code]
            flag_map = {
                'ar': '🇸🇦', 'tr': '🇹🇷', 'fa': '🇮🇷', 'ur': '🇵🇰', 'hi': '🇮🇳',
                'bn': '🇧🇩', 'id': '🇮🇩', 'ms': '🇲🇾', 'th': '🇹🇭', 'vi': '🇻🇳',
                'fr': '🇫🇷', 'es': '🇪🇸', 'de': '🇩🇪', 'it': '🇮🇹', 'pt': '🇵🇹',
                'ru': '🇷🇺', 'ja': '🇯🇵', 'ko': '🇰🇷', 'zh-CN': '🇨🇳'
            }
            lang_flag = flag_map.get(lang_code, '🌍')
        
        # Build subtitles list - TEST SUBTITLE FIRST
        subtitles = [
            get_test_subtitle(),  # Always include test subtitle
            {
                "id": f"auto-{lang_code}-{imdb_id}",
                "url": subtitle_url,
                "lang": lang_iso,
                "name": f"{lang_flag} {lang_name} (Auto-Translated)"
            }
        ]
        
        # LOGGING: Found subtitles
        print(f"[Subtitle Response] Found {len(subtitles)} subtitles")
        print(f"=" * 60)
        
        response = jsonify({"subtitles": subtitles})
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    
    except Exception as e:
        print(f"[ERROR] Subtitle handler: {e}")
        traceback.print_exc()
        
        # Return test subtitle even on error
        response = jsonify({"subtitles": [get_test_subtitle()]})
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response


@app.route('/subtitle/<content_type>/<content_id>/arabic.srt')
def serve_translated_subtitle(content_type: str, content_id: str):
    """Default subtitle streaming (Arabic, Android mode on)"""
    print(f"[Route] /subtitle/{content_type}/{content_id}/arabic.srt")
    return serve_translated_with_config('', content_type, content_id)


@app.route('/<config_b64>/subtitle/<content_type>/<content_id>/translated.srt')
def serve_translated_with_config(config_b64: str, content_type: str, content_id: str):
    """
    Config-aware subtitle streaming
    Returns actual subtitle content with fallback to English
    """
    config = decode_config(config_b64) if config_b64 else {'lang': 'ar', 'android': True}
    lang_code = config.get('lang', 'ar')
    android_mode = config.get('android', True)
    
    print(f"=" * 60)
    print(f"[Translate Request] Type: {content_type}, ID: {content_id}")
    print(f"[Translate Request] Lang: {lang_code}, Android: {android_mode}")
    
    try:
        # Parse content ID
        imdb_id, season, episode = parse_video_id(content_id)
        
        cache_key = f"{imdb_id}:{lang_code}:{season}:{episode}"
        
        # Check cache first
        if cache_key in subtitle_cache:
            print(f"[Cache Hit] {cache_key}")
            return create_subtitle_response(subtitle_cache[cache_key], android_mode=android_mode)
        
        # Check if sources are available
        if not SOURCES_AVAILABLE or source_manager is None:
            print(f"[ERROR] Sources not available!")
            error_srt = f"1\n00:00:01,000 --> 00:00:05,000\nSubtitle sources not available.\nPlease check server logs.\n\n"
            return create_subtitle_response(error_srt, android_mode=android_mode)
        
        # Fetch English subtitle from 33 sources
        print(f"[Fetching] Searching sources for {imdb_id}...")
        
        english_srt = None
        try:
            english_srt = source_manager.get_first_subtitle(imdb_id, content_type, season, episode)
        except Exception as e:
            print(f"[ERROR] Source manager failed: {e}")
            traceback.print_exc()
        
        if not english_srt:
            print(f"[Warning] No English subtitles found for {imdb_id}")
            error_srt = f"1\n00:00:01,000 --> 00:00:05,000\nNo English subtitles found for translation.\nIMDB: {imdb_id}\n\n"
            return create_subtitle_response(error_srt, android_mode=android_mode)
        
        print(f"[Found] English subtitle: {len(english_srt)} characters")
        
        # Try to translate
        translated_srt = None
        
        if TRANSLATOR_AVAILABLE:
            try:
                lang_name = LANGUAGE_NAMES.get(lang_code, ('Unknown', '', 'und'))[0]
                print(f"[Translating] To {lang_name}...")
                translated_srt = translate_srt_content(english_srt, lang_code)
                
                if translated_srt:
                    print(f"[Success] Translation complete: {len(translated_srt)} characters")
            except Exception as e:
                print(f"[ERROR] Translation failed: {e}")
                traceback.print_exc()
        else:
            print(f"[Warning] Translator not available")
        
        # FALLBACK: Return English if translation failed
        if not translated_srt:
            print(f"[Fallback] Returning English subtitle as fallback")
            translated_srt = english_srt
        
        # Cache the result
        subtitle_cache[cache_key] = translated_srt
        print(f"[Cached] {cache_key}")
        print(f"=" * 60)
        
        return create_subtitle_response(translated_srt, android_mode=android_mode)
    
    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")
        traceback.print_exc()
        error_srt = f"1\n00:00:01,000 --> 00:00:05,000\nError: {str(e)}\n\n"
        return create_subtitle_response(error_srt, android_mode=android_mode)


@app.route('/health')
def health():
    """Health check endpoint with diagnostics"""
    print("[Route] /health")
    return jsonify({
        "status": "healthy",
        "addon": "Auto Arabic Vibe",
        "version": "1.1.0",
        "sources_available": SOURCES_AVAILABLE,
        "translator_available": TRANSLATOR_AVAILABLE,
        "cache_size": len(subtitle_cache)
    })


# Handle OPTIONS preflight requests
@app.route('/', methods=['OPTIONS'])
@app.route('/configure', methods=['OPTIONS'])
@app.route('/manifest.json', methods=['OPTIONS'])
@app.route('/subtitles/<path:path>', methods=['OPTIONS'])
@app.route('/subtitle/<path:path>', methods=['OPTIONS'])
@app.route('/<config>/manifest.json', methods=['OPTIONS'])
@app.route('/<config>/subtitles/<path:path>', methods=['OPTIONS'])
@app.route('/<config>/subtitle/<path:path>', methods=['OPTIONS'])
def options_handler(config=None, path=None):
    """Handle CORS preflight requests"""
    response = make_response()
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, HEAD'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Accept, Origin'
    response.headers['Access-Control-Max-Age'] = '86400'
    return response


# Add CORS headers to ALL responses
@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Accept, Origin'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, HEAD'
    response.headers['Access-Control-Expose-Headers'] = 'Content-Type, Content-Length, Content-Disposition'
    return response


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🇸🇦  Auto Arabic Vibe - Stremio Addon v1.1.0               ║
║                                                              ║
║   Server running at: http://localhost:{port}                    ║
║   Manifest URL: http://localhost:{port}/manifest.json           ║
║   Config Page: http://localhost:{port}/configure                ║
║                                                              ║
║   ✅ Sources Available: {str(SOURCES_AVAILABLE):5}                          ║
║   ✅ Translator Available: {str(TRANSLATOR_AVAILABLE):5}                       ║
║   ✅ Android TV Compatibility Mode ENABLED                   ║
║   ✅ Test Subtitle ENABLED                                   ║
║   ✅ Fallback to English ENABLED                             ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=port, debug=False)
