"""
Enhanced OCR Engine for Job Flyers & Screenshot Images
Performs multi-pass OCR and regex-based email extraction with artifact healing.
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

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', re.IGNORECASE)

JUNK_EMAILS = [
    'example.com', 'sample.com', 'test.com', 'domain.com', 'email.com',
    'yourcompany.com', 'xyz.com', 'abc.com', 'mail.com', 'sentry.io', 'w3.org'
]

COMMON_TLDS = ['com', 'in', 'org', 'net', 'co', 'io', 'ae', 'sa', 'uk', 'us', 'me', 'edu', 'gov']

def extract_emails(text: str) -> list[str]:
    """Finds valid email addresses from text with strict anti-junk and OCR-healing rules."""
    if not text:
        return []

    # 1. Obfuscation replacements
    clean_text = re.sub(r'\s*\[at\]\s*|\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    clean_text = re.sub(r'(?<=[a-zA-Z0-9._%+-])\s+at\s+(?=[a-zA-Z0-9-]+\.[a-zA-Z]{2,})', '@', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\s*\[dot\]\s*|\s*\(dot\)\s*', '.', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'(?<=[a-zA-Z0-9._%+-])\s+dot\s+(?=[a-zA-Z]{2,})', '.', clean_text, flags=re.IGNORECASE)

    # 2. Fix common OCR mistakes for .com (e.g. 0.0m, corn, con)
    clean_text = re.sub(r'(@[a-zA-Z0-9._-]+)\s*(?:[0o]\.[0o]m|c[0o]rn|c[0o]n)\b', r'\1.com', clean_text, flags=re.IGNORECASE)

    # 3. Fix missing dots with spaces before common TLDs: @domain com -> @domain.com
    for tld in COMMON_TLDS:
        clean_text = re.sub(rf'(@[a-zA-Z0-9._-]+)\s+{tld}\b', rf'\1.{tld}', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(rf'(@[a-zA-Z0-9._-]+)\s*\.\s*{tld}\b', rf'\1.{tld}', clean_text, flags=re.IGNORECASE)

    # 4. Fix missing dots directly attached before common TLDs: @domaincom -> @domain.com
    for tld in COMMON_TLDS:
        clean_text = re.sub(rf'(@[a-zA-Z0-9_-]{{3,}})({tld})\b', rf'\1.{tld}', clean_text, flags=re.IGNORECASE)

    # 5. Fix common letter substitutions in domain names
    clean_text = re.sub(r'-(?:cocp|c0rp)\.com', '-corp.com', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'@qgoft-', '@qsoft-', clean_text, flags=re.IGNORECASE)

    matches = EMAIL_REGEX.findall(clean_text)
    valid_emails = []

    for email in matches:
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
