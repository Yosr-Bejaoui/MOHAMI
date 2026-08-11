import json
from collections import Counter

def check_quality(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total = len(data)
    short_text = 0
    missing_meta = 0
    ids = set()
    dup_ids = 0
    texts = set()
    dup_texts = 0
    ocr_artifacts = 0
    
    for item in data:
        text = item.get('text', '')
        if len(text.strip()) < 15:
            short_text += 1
            
        meta = item.get('metadata', {})
        if not meta.get('source') or not meta.get('law') or not meta.get('article_number'):
            missing_meta += 1
            
        uid = item.get('id')
        if uid in ids:
            dup_ids += 1
        ids.add(uid)
        
        if text in texts:
            dup_texts += 1
        texts.add(text)
        
        if "Impeimerie Officielle" in text or "Imprimerie Officielle" in text:
            ocr_artifacts += 1

    print(f"Total articles: {total}")
    print(f"Short text (<15 chars): {short_text}")
    print(f"Missing critical metadata (source/law/article_number): {missing_meta}")
    print(f"Duplicate IDs: {dup_ids}")
    print(f"Duplicate exact texts: {dup_texts}")
    print(f"OCR Artifacts (Imprimerie Officielle): {ocr_artifacts}")

if __name__ == '__main__':
    check_quality('data/generated/corpus.json')
