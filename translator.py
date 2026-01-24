"""
Arabic Translation Module
Translates English subtitles to any language using deep-translator
Compatible with Python 3.14+
"""

from deep_translator import GoogleTranslator
import re
from typing import List


def get_translator(target_lang: str = 'ar'):
    """Get a translator for the target language"""
    return GoogleTranslator(source='en', target=target_lang)


def translate_text(text: str, target_lang: str = 'ar') -> str:
    """
    Translate a single text string to target language
    
    Args:
        text: Text to translate
        target_lang: Target language code (default: 'ar' for Arabic)
    
    Returns:
        Translated text
    """
    if not text or not text.strip():
        return text
    
    try:
        # Skip if text is mostly special characters/numbers
        if len(re.sub(r'[^a-zA-Z]', '', text)) < 3:
            return text
        
        translator = get_translator(target_lang)
        result = translator.translate(text)
        return result if result else text
    except Exception as e:
        print(f"[Translator] Error: {e}")
        return text  # Return original on failure


def translate_srt_content(srt_content: str, target_lang: str = 'ar') -> str:
    """
    Translate entire SRT content to target language
    
    Args:
        srt_content: Raw SRT subtitle content
        target_lang: Target language code (default: 'ar' for Arabic)
    
    Returns:
        Translated SRT content with preserved formatting
    """
    if not srt_content:
        return ""
    
    # Split into blocks
    blocks = re.split(r'\n\s*\n', srt_content.strip())
    translated_blocks = []
    
    for block in blocks:
        lines = block.strip().split('\n')
        
        if len(lines) < 3:
            translated_blocks.append(block)
            continue
        
        try:
            # First line: index number
            index = lines[0].strip()
            
            # Second line: timestamp
            timestamp = lines[1].strip()
            
            # Remaining lines: text to translate
            text_lines = '\n'.join(lines[2:])
            
            # Translate the text
            if text_lines.strip():
                translated_text = translate_text(text_lines, target_lang)
            else:
                translated_text = text_lines
            
            # Rebuild block
            translated_block = f"{index}\n{timestamp}\n{translated_text}"
            translated_blocks.append(translated_block)
        
        except Exception as e:
            print(f"[Translator] Block error: {e}")
            translated_blocks.append(block)  # Keep original on error
    
    # Join with proper SRT format (blank lines between blocks)
    return '\n\n'.join(translated_blocks)


def batch_translate_srt(srt_content: str, target_lang: str = 'ar', batch_size: int = 10) -> str:
    """
    Translate SRT content - uses deep-translator's batch capability
    
    Args:
        srt_content: Raw SRT content
        target_lang: Target language code
        batch_size: Number of texts to translate at once
    
    Returns:
        Translated SRT content
    """
    if not srt_content:
        return ""
    
    # Parse SRT into structured format
    blocks = re.split(r'\n\s*\n', srt_content.strip())
    
    # Extract all texts
    parsed_blocks = []
    texts_to_translate = []
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            index = lines[0].strip()
            timestamp = lines[1].strip()
            text = '\n'.join(lines[2:])
            
            parsed_blocks.append({
                'index': index,
                'timestamp': timestamp,
                'text': text
            })
            
            if text.strip() and len(re.sub(r'[^a-zA-Z]', '', text)) >= 3:
                texts_to_translate.append((len(parsed_blocks) - 1, text))
        else:
            parsed_blocks.append({'raw': block})
    
    # Batch translate using deep-translator
    if texts_to_translate:
        try:
            translator = get_translator(target_lang)
            texts_only = [t[1] for t in texts_to_translate]
            translated = translator.translate_batch(texts_only)
            
            # Apply translations
            for i, (block_idx, _) in enumerate(texts_to_translate):
                if i < len(translated) and translated[i]:
                    parsed_blocks[block_idx]['text'] = translated[i]
        except Exception as e:
            print(f"[Translator] Batch error: {e}")
            # Fallback to individual translation
            for block_idx, text in texts_to_translate:
                parsed_blocks[block_idx]['text'] = translate_text(text, target_lang)
    
    # Rebuild SRT
    result_blocks = []
    for block in parsed_blocks:
        if 'raw' in block:
            result_blocks.append(block['raw'])
        else:
            result_blocks.append(f"{block['index']}\n{block['timestamp']}\n{block['text']}")
    
    return '\n\n'.join(result_blocks)
