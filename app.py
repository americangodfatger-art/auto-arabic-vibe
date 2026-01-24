"""
Auto Arabic Vibe - Stremio Addon
Python Flask server with Android TV Compatibility Mode
33 Subtitle Sources with Arabic Translation
With Configuration Page and Dynamic Routing
"""

import os
import json
import re
import base64
from flask import Flask, Response, request, jsonify, make_response, render_template
from flask_cors import CORS

from sources import source_manager
from translator import translate_srt_content, batch_translate_srt

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
with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
    BASE_MANIFEST = json.load(f)

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


def decode_config(config_b64: str) -> dict:
    """
    Decode Base64 config string to dictionary
    
    Args:
        config_b64: Base64 encoded config JSON
    
    Returns:
        Config dictionary with defaults
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
        'configurationRequired': False
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
    Ensures proper structure with blank lines between blocks
    
    Args:
        content: Raw SRT content
    
    Returns:
        Fixed SRT content
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
        
        # Validate block structure
        try:
            # First line should be a number (index)
            index = lines[0].strip()
            if not index.isdigit():
                # Try to fix by adding index
                index = str(len(valid_blocks) + 1)
            
            # Second line should be timestamp
            timestamp = lines[1].strip()
            if '-->' not in timestamp:
                continue  # Invalid block, skip
            
            # Text lines
            text = '\n'.join(lines[2:]).strip()
            if not text:
                continue  # Empty text, skip
            
            # Rebuild valid block
            valid_blocks.append(f"{len(valid_blocks) + 1}\n{timestamp}\n{text}")
        
        except Exception:
            continue
    
    # Join with exactly one blank line between blocks
    return '\n\n'.join(valid_blocks) + '\n'


def create_subtitle_response(content: str, format_type: str = 'srt', android_mode: bool = True) -> Response:
    """
    Create response with optional Android TV Compatibility Mode
    
    When android_mode is True:
    1. Strict MIME Type: application/x-subrip for SRT
    2. Direct Stream: Return actual content, not redirect
    3. Encoding: Force UTF-8 with BOM for Arabic/RTL characters
    4. CORS headers for Stremio
    
    Args:
        content: Subtitle content
        format_type: 'srt' or 'vtt'
        android_mode: Enable Android TV compatibility (strict MIME, UTF-8 BOM)
    
    Returns:
        Flask Response with proper headers
    """
    # Validate SRT format if android mode
    if android_mode:
        validated_content = validate_srt(content)
        # Encode as UTF-8 with BOM for better Arabic/RTL support
        encoded_content = validated_content.encode('utf-8-sig')
    else:
        validated_content = content
        encoded_content = validated_content.encode('utf-8')
    
    # Set MIME type based on format and mode
    if format_type == 'vtt':
        mime_type = 'text/vtt; charset=utf-8'
    elif android_mode:
        # CRITICAL: Use application/x-subrip for Android TV compatibility
        mime_type = 'application/x-subrip; charset=utf-8'
    else:
        mime_type = 'text/plain; charset=utf-8'
    
    response = Response(
        encoded_content,
        status=200,
        mimetype=mime_type
    )
    
    # Set headers
    response.headers['Content-Type'] = mime_type
    response.headers['Content-Disposition'] = 'inline; filename="subtitle.srt"'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    
    if android_mode:
        response.headers['X-Content-Type-Options'] = 'nosniff'
    
    return response


@app.route('/')
def index():
    """Configuration page - modern HTML landing page"""
    return render_template('index.html')


@app.route('/manifest.json')
def manifest_default():
    """Default manifest (Arabic, Android mode on)"""
    config = {'lang': 'ar', 'android': True}
    manifest = get_manifest_for_config(config)
    response = jsonify(manifest)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@app.route('/<config_b64>/manifest.json')
def manifest_with_config(config_b64: str):
    """Dynamic manifest with user config"""
    config = decode_config(config_b64)
    print(f"[Manifest] Config: {config}")
    manifest = get_manifest_for_config(config)
    response = jsonify(manifest)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@app.route('/subtitles/<content_type>/<content_id>.json')
def subtitles_handler(content_type: str, content_id: str):
    """Default subtitle handler (Arabic, Android mode on)"""
    return subtitles_with_config('', content_type, content_id)


@app.route('/<config_b64>/subtitles/<content_type>/<content_id>.json')
def subtitles_with_config(config_b64: str, content_type: str, content_id: str):
    """
    Config-aware subtitle handler
    
    URL format: /{config}/subtitles/{type}/{id}.json
    """
    config = decode_config(config_b64) if config_b64 else {'lang': 'ar', 'android': True}
    lang_code = config.get('lang', 'ar')
    
    print(f"[Subtitle Request] Type: {content_type}, ID: {content_id}, Lang: {lang_code}")
    
    try:
        # Parse content ID
        parts = content_id.replace('.json', '').split(':')
        imdb_id = parts[0]
        
        # Generate subtitle URL that points to our direct stream endpoint
        base_url = request.host_url.rstrip('/')
        
        # Include config in the subtitle URL
        if config_b64:
            subtitle_url = f"{base_url}/{config_b64}/subtitle/{content_type}/{content_id}/translated.srt"
        else:
            subtitle_url = f"{base_url}/subtitle/{content_type}/{content_id}/arabic.srt"
        
        # Get language name for display
        lang_name = 'Arabic'
        lang_flag = '🇸🇦'
        lang_iso = 'ara'
        
        if lang_code in LANGUAGE_NAMES:
            lang_name, lang_native, lang_iso = LANGUAGE_NAMES[lang_code]
            # Map language codes to flags
            flag_map = {
                'ar': '🇸🇦', 'tr': '🇹🇷', 'fa': '🇮🇷', 'ur': '🇵🇰', 'hi': '🇮🇳',
                'bn': '🇧🇩', 'id': '🇮🇩', 'ms': '🇲🇾', 'th': '🇹🇭', 'vi': '🇻🇳',
                'fr': '🇫🇷', 'es': '🇪🇸', 'de': '🇩🇪', 'it': '🇮🇹', 'pt': '🇵🇹',
                'ru': '🇷🇺', 'ja': '🇯🇵', 'ko': '🇰🇷', 'zh-CN': '🇨🇳'
            }
            lang_flag = flag_map.get(lang_code, '🌍')
        
        subtitles = [{
            "id": f"auto-{lang_code}-{imdb_id}",
            "url": subtitle_url,
            "lang": lang_iso,
            "name": f"{lang_flag} {lang_name} (Auto-Translated)"
        }]
        
        response = jsonify({"subtitles": subtitles})
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    
    except Exception as e:
        print(f"[Error] Subtitle handler: {e}")
        response = jsonify({"subtitles": []})
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response


@app.route('/subtitle/<content_type>/<content_id>/arabic.srt')
def serve_translated_subtitle(content_type: str, content_id: str):
    """Default subtitle streaming (Arabic, Android mode on)"""
    return serve_translated_with_config('', content_type, content_id)


@app.route('/<config_b64>/subtitle/<content_type>/<content_id>/translated.srt')
def serve_translated_with_config(config_b64: str, content_type: str, content_id: str):
    """
    Config-aware subtitle streaming
    
    CRITICAL: This is the "Direct Stream" endpoint
    Returns actual subtitle content (not a redirect) with proper headers
    """
    config = decode_config(config_b64) if config_b64 else {'lang': 'ar', 'android': True}
    lang_code = config.get('lang', 'ar')
    android_mode = config.get('android', True)
    
    print(f"[Translate Request] Type: {content_type}, ID: {content_id}, Lang: {lang_code}, Android: {android_mode}")
    
    try:
        # Parse content ID
        parts = content_id.replace('.json', '').split(':')
        imdb_id = parts[0]
        season = int(parts[1]) if len(parts) > 1 else None
        episode = int(parts[2]) if len(parts) > 2 else None
        
        cache_key = f"{imdb_id}:{lang_code}:{season}:{episode}"
        
        # Check cache
        if cache_key in subtitle_cache:
            print(f"[Cache Hit] {cache_key}")
            return create_subtitle_response(subtitle_cache[cache_key], android_mode=android_mode)
        
        # Fetch English subtitle from 33 sources
        print(f"[Fetching] Searching 33 sources for {imdb_id}...")
        
        english_srt = source_manager.get_first_subtitle(imdb_id, content_type, season, episode)
        
        if not english_srt:
            print(f"[Error] No English subtitles found for {imdb_id}")
            return create_subtitle_response("1\n00:00:01,000 --> 00:00:05,000\nNo subtitles available for translation.\n\n", android_mode=android_mode)
        
        # Translate to target language
        lang_name = LANGUAGE_NAMES.get(lang_code, ('Unknown', '', 'und'))[0]
        print(f"[Translating] {len(english_srt)} characters to {lang_name}...")
        translated_srt = translate_srt_content(english_srt, lang_code)
        
        if not translated_srt:
            print(f"[Error] Translation failed for {imdb_id}")
            return create_subtitle_response("1\n00:00:01,000 --> 00:00:05,000\nTranslation failed. Please try again.\n\n", android_mode=android_mode)
        
        # Cache the result
        subtitle_cache[cache_key] = translated_srt
        print(f"[Success] Translated and cached {cache_key}")
        
        return create_subtitle_response(translated_srt, android_mode=android_mode)
    
    except Exception as e:
        print(f"[Error] Translation endpoint: {e}")
        import traceback
        traceback.print_exc()
        return create_subtitle_response(f"1\n00:00:01,000 --> 00:00:05,000\nError: {str(e)}\n\n", android_mode=android_mode)


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "addon": "Auto Arabic Vibe", "sources": 33})


# Handle OPTIONS preflight requests explicitly
@app.route('/', methods=['OPTIONS'])
@app.route('/manifest.json', methods=['OPTIONS'])
@app.route('/subtitles/<path:path>', methods=['OPTIONS'])
@app.route('/subtitle/<path:path>', methods=['OPTIONS'])
def options_handler(path=None):
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
║   🇸🇦  Auto Arabic Vibe - Stremio Addon                      ║
║                                                              ║
║   Server running at: http://localhost:{port}                    ║
║   Manifest URL: http://localhost:{port}/manifest.json           ║
║                                                              ║
║   ✅ Android TV Compatibility Mode ENABLED                   ║
║   ✅ Direct Stream (no redirects)                            ║
║   ✅ UTF-8 Encoding for Arabic                               ║
║   ✅ Strict MIME Type (application/x-subrip)                 ║
║                                                              ║
║   To install in Stremio:                                     ║
║   1. Open Stremio                                            ║
║   2. Go to Addons                                            ║
║   3. Enter the manifest URL above                            ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=port, debug=False)
