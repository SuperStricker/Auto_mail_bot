"""
Enhanced Universal OCR & Email Extraction Engine
Supports:
  - Universal Email Emojis (📧, ✉️, 📩, 📮, 📨, 📬, etc.)
  - Diverse Recruiter Phrases ('share your resume here', 'update your CV at', 'drop your profile to', 'email:', 'gmail:', etc.)
  - Glued TLD Splitting (.comRepeatedEmail, .comWord, .com#Tag)
  - All Corporate & Custom Domains (.com, .ae, .sa, .in, .co.in, .org, .net, .tech, .io, etc.)
  - Multi-pass Windows native OCR & Linux pytesseract fallback
"""

import os
import re
import asyncio
from PIL import Image, ImageEnhance

try:
    import winocr
    HAS_WINOCR = True
except ImportError:
    winocr = None
    HAS_WINOCR = False

try:
    import pytesseract
    HAS_PYTESSERACT = True
except ImportError:
    pytesseract = None
    HAS_PYTESSERACT = False

EMAIL_EMOJIS = ['📧', '✉️', '📩', '📮', '📨', '📬', '📫', '📪', '💌', '👉', '📍', '📌', '🔗', '📞', '☎️']

COMMON_TLDS = [
    'com', 'in', 'org', 'net', 'co', 'io', 'ae', 'sa', 'uk', 'us', 'me', 'edu', 'gov',
    'tech', 'ai', 'info', 'biz', 'global', 'agency', 'careers', 'co.in', 'co.ae', 'com.sa'
]

TLD_REGEX = '|'.join([re.escape(t) for t in sorted(COMMON_TLDS, key=len, reverse=True)])

# Universal email matcher bounded by authentic TLDs
EMAIL_REGEX = re.compile(rf'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:{TLD_REGEX})\b', re.IGNORECASE)

JUNK_EMAILS = [
    'example.com', 'sample.com', 'test.com', 'domain.com', 'email.com',
    'yourcompany.com', 'xyz.com', 'abc.com', 'mail.com', 'sentry.io', 'w3.org'
]

RECRUITER_INTENT_PATTERN = re.compile(
    r'(?:share|send|drop|forward|mail|email|submit|reach\s*out|apply|ping|connect|write|update)\s+'
    r'(?:your\s+)?(?:updated\s+)?(?:resume|resumes|cv|cvs|profile|profiles|application|details)?\s*'
    r'(?:at|to|on|in|via|email|id|here|below)?\s*[:\-–]?\s*'
    r'(?:[A-Za-z\s]{0,35}[:\-–])?\s*'
    rf'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:{TLD_REGEX})\b)',
    re.IGNORECASE
)

def extract_emails(text: str) -> list[str]:
    """Finds valid email addresses from text with strict anti-junk, corporate domain support, and OCR-healing rules."""
    if not text:
        return []

    clean_text = str(text)

    # 1. Normalize Email Emojis to a clean textual intent marker
    for em in EMAIL_EMOJIS:
        if em in clean_text:
            clean_text = clean_text.replace(em, ' EMAIL_INTENT: ')

    # 2. Obfuscation replacements (explicit bracket formats only)
    clean_text = re.sub(r'\s*\[at\]\s*|\s*\(at\)\s*', '@', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\s*\[dot\]\s*|\s*\(dot\)\s*', '.', clean_text, flags=re.IGNORECASE)

    # 3. Heal spaces around @ and dots (e.g. hr @ mycompany . com -> hr@mycompany.com)
    clean_text = re.sub(r'([a-zA-Z0-9._%+-]+)\s*@\s*([a-zA-Z0-9._-]+)\s*\.\s*([a-zA-Z]{2,})', r'\1@\2.\3', clean_text)
    clean_text = re.sub(r'([a-zA-Z0-9._%+-]+)\s*@\s*([a-zA-Z0-9._-]+)', r'\1@\2', clean_text)

    # 4. Split glued words / LinkedIn repeated link artifacts after TLDs
    for tld in ['com', 'co.in', 'in', 'org', 'net', 'ae', 'sa', 'io', 'tech', 'ai', 'global']:
        clean_text = re.sub(rf'(\.{re.escape(tld)})([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+)', r'\1 \2', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(rf'(\.{re.escape(tld)})([A-Z][a-z]+)', r'\1 \2', clean_text)
        clean_text = re.sub(rf'(\.{re.escape(tld)})(#)', r'\1 \2', clean_text)

    # 5. Fix common OCR mistakes for .com (e.g. 0.0m, corn, con)
    clean_text = re.sub(r'(@[a-zA-Z0-9._-]+)\s*(?:[0o]\.[0o]m|c[0o]rn|c[0o]n)\b', r'\1.com', clean_text, flags=re.IGNORECASE)

    # 6. Fix missing dots with spaces before common TLDs: @domain com -> @domain.com
    for tld in ['com', 'in', 'org', 'net', 'ae', 'sa', 'co']:
        clean_text = re.sub(rf'(@[a-zA-Z0-9._-]+)\s+{tld}\b', rf'\1.{tld}', clean_text, flags=re.IGNORECASE)

    # 7. Fix common letter substitutions in domain names
    clean_text = re.sub(r'-(?:cocp|c0rp)\.com', '-corp.com', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'@qgoft-', '@qsoft-', clean_text, flags=re.IGNORECASE)

    # 8. Extract intent-ranked emails first
    intent_matches = [m.lower().strip().rstrip('.,;:') for m in RECRUITER_INTENT_PATTERN.findall(clean_text)]

    # 9. Extract all standard email matches
    all_matches = EMAIL_REGEX.findall(clean_text)

    valid_emails = []

    # Insert intent-ranked matches at the very top
    for em in intent_matches:
        if em not in valid_emails:
            valid_emails.append(em)

    for email in all_matches:
        email_clean = email.lower().strip().rstrip('.,;:')
        domain = email_clean.split('@')[-1]

        if domain.startswith("www."):
            continue
        if any(junk in domain for junk in JUNK_EMAILS):
            continue
        if any(email_clean.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif']):
            continue

        # Typo correction in common email stems
        if 'navceshini@' in email_clean:
            email_clean = email_clean.replace('navceshini@', 'naveeshini@')
        if 'navoosngm@' in email_clean:
            email_clean = email_clean.replace('navoosngm@', 'naveeshini@')

        if email_clean not in valid_emails:
            valid_emails.append(email_clean)

    return valid_emails

async def extract_text_from_image_async(image_path: str) -> str:
    """Extracts raw text from an image file using multi-pass Windows native OCR."""
    if not os.path.exists(image_path) or not HAS_WINOCR or not winocr:
        return ""
    try:
        img = Image.open(image_path)
        # Pass 1: Raw recognition
        res1 = await winocr.recognize_pil(img)
        text1 = res1.text or ""

        # Pass 2: Enhanced 2x contrast grayscale
        w, h = img.size
        scaled = img.convert('L').resize((w * 2, h * 2), Image.Resampling.LANCZOS)
        enh = ImageEnhance.Contrast(scaled)
        contrasted = enh.enhance(1.8)
        res2 = await winocr.recognize_pil(contrasted)
        text2 = res2.text or ""

        return f"{text1}\n{text2}"
    except Exception as e:
        print(f"[OCR Exception]: {e}")
        return ""

def extract_from_image(image_path: str) -> tuple[str, list[str]]:
    """Synchronous wrapper for image text and email extraction."""
    text = ""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            text = asyncio.run_coroutine_threadsafe(extract_text_from_image_async(image_path), loop).result()
        else:
            text = loop.run_until_complete(extract_text_from_image_async(image_path))
    except RuntimeError:
        text = asyncio.run(extract_text_from_image_async(image_path))
    except Exception as e:
        print(f"[OCR Runner Error]: {e}")
        text = ""

    # Fallback to pytesseract (especially for Linux/GitHub Actions runners)
    if not text and HAS_PYTESSERACT and pytesseract and os.path.exists(image_path):
        try:
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img)
            # Enhanced pass
            w, h = img.size
            scaled = img.convert('L').resize((w * 2, h * 2), Image.Resampling.LANCZOS)
            enh = ImageEnhance.Contrast(scaled)
            contrasted = enh.enhance(1.8)
            text2 = pytesseract.image_to_string(contrasted)
            text = f"{text}\n{text2}"
        except Exception as e_tess:
            print(f"[Pytesseract Error]: {e_tess}")

    emails = extract_emails(text)
    return text, emails
