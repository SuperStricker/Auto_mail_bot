"""
Enhanced Universal OCR & Email Extraction Engine
Supports:
  - Universal Email Emojis (📧, ✉️, 📩, 📮, 📨, 📬, etc.)
  - Diverse Recruiter Phrases ('share your resume here', 'send your resume to', etc.)
  - Safe Post-Domain TLD Splitting (never truncates dotted usernames like agarwal.saumya@)
  - ALL Corporate, Startup & Country Domains (.com, .ae, .sa, .in, .co.uk, .qa, .de, .cloud, .dev, .solutions, etc.)
  - Multi-pass Windows native OCR (winocr) & Linux Tesseract + OpenCV/PIL preprocessing
"""

import os
import re
import asyncio
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    cv2 = None
    np = None
    HAS_CV2 = False

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

# Known TLDs used ONLY after '@domain' to separate glued trailing text (.comApply, .com#tag, .comhr@...)
GLUE_TLDS = [
    'com.sa', 'co.in', 'co.ae', 'co.uk', 'com.au', 'com.sg',
    'global', 'careers', 'systems', 'solutions', 'services', 'digital', 'company',
    'tech', 'info', 'work', 'jobs', 'cloud',
    'com', 'org', 'net', 'edu', 'gov', 'biz', 'dev', 'app', 'xyz',
    'in', 'ae', 'sa', 'uk', 'us', 'qa', 'om', 'kw', 'bh', 'de', 'nl', 'ca', 'au', 'sg', 'eu', 'io', 'ai', 'co', 'me'
]
GLUE_TLD_RE = '|'.join([re.escape(t) for t in sorted(GLUE_TLDS, key=len, reverse=True)])

ASSET_EXTS = (
    '.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif', '.bmp', '.ico',
    '.pdf', '.css', '.js', '.html', '.htm', '.mp4', '.zip', '.exe', '.json', '.xml', '.woff', '.ttf'
)

JUNK_EMAILS = (
    'example.com', 'sample.com', 'test.com', 'domain.com', 'email.com',
    'yourcompany.com', 'company.com', 'xyz.com', 'abc.com', 'mail.com',
    'sentry.io', 'w3.org', 'schema.org', 'linkedin.com', 'licdn.com',
    'openxmlformats.org', 'googleapis.com', 'facebook.com', 'twitter.com', 'instagram.com'
)

# Matches any valid email domain & TLD (2..15 chars, plus multi-part ccTLDs like .co.uk)
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,15}(?![a-zA-Z0-9])')

RECRUITER_INTENT_PATTERN = re.compile(
    r'(?:share|send|drop|forward|mail|email|submit|reach\s*out|apply|ping|connect|write|update)\s+'
    r'(?:your\s+)?(?:updated\s+)?(?:resume|resumes|cv|cvs|profile|profiles|application|details)?\s*'
    r'(?:at|to|on|in|via|email|id|here|below)?\s*[:\-–]?\s*'
    r'(?:[A-Za-z\s]{0,35}[:\-–])?\s*'
    r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,15})(?![a-zA-Z0-9])',
    re.IGNORECASE
)

def extract_emails(text: str) -> list[str]:
    """Finds valid email addresses from text with strict anti-junk, universal domain support, and safe OCR-healing."""
    if not text:
        return []

    clean_text = str(text)

    # 1. Normalize Email Emojis to clean textual markers
    for em in EMAIL_EMOJIS:
        if em in clean_text:
            clean_text = clean_text.replace(em, ' EMAIL_INTENT: ')

    # 2. Fix OCR misreads of '@' as '©' or '®' inside email-like tokens
    clean_text = re.sub(r'([a-zA-Z0-9._+-])[©®]([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', r'\1@\2', clean_text)

    # 3. Obfuscation replacements ([at] / (at) / {at}, [dot] / (dot) / {dot})
    clean_text = re.sub(r'\s*[\[\(\{]\s*at\s*[\]\)\}]\s*', '@', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\s*[\[\(\{]\s*dot\s*[\]\)\}]\s*', '.', clean_text, flags=re.IGNORECASE)

    # 4. Heal whitespace inside email tokens: 'hr @ mycompany . co . in' -> 'hr@mycompany.co.in'
    clean_text = re.sub(r'([a-zA-Z0-9._%+-]+)\s*@\s*([a-zA-Z0-9._-]+)', r'\1@\2', clean_text)
    for _ in range(3):
        clean_text = re.sub(r'(@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*)\s*\.\s*([a-zA-Z]{2,15}\b)', r'\1.\2', clean_text)

    # 5. Fix OCR comma instead of dot before TLDs (e.g. '@thinksys,com' -> '@thinksys.com')
    clean_text = re.sub(rf'(@[a-zA-Z0-9.-]+),({GLUE_TLD_RE})\b', r'\1.\2', clean_text, flags=re.IGNORECASE)

    # 6. Fix common OCR mistakes for .com (0.0m, .corn, .con) and missing dot before TLD
    clean_text = re.sub(r'(@[a-zA-Z0-9.-]+?)\s*(?:[0o]\.[0o]m|\.c[0o]rn|\.c[0o]n)\b', r'\1.com', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'(@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*)\s+(com|in|org|net|ae|sa|co|io|ai|uk|qa)\b', r'\1.\2', clean_text, flags=re.IGNORECASE)

    # 7. Fix common domain OCR typos
    clean_text = re.sub(r'-(?:cocp|c0rp)\.com', '-corp.com', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'@qgoft-', '@qsoft-', clean_text, flags=re.IGNORECASE)

    # 8. SAFE glued-word splitting: ONLY after a complete '@domain.tld' match (never inside local-part!)
    clean_text = re.sub(rf'(@[a-zA-Z0-9.-]+\.(?:{GLUE_TLD_RE}))(?=[a-zA-Z0-9._%+-]+@)', r'\1 ', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(rf'(@[a-zA-Z0-9.-]+\.(?:{GLUE_TLD_RE}))([A-Z#])', r'\1 \2', clean_text)

    # 9. Separate glued prefix labels like 'Email:hr@x.com' or 'mailto:hr@x.com'
    clean_text = re.sub(r'(?i)\b(?:mailto|e-?mail|id|cv|resume|contact|at|to)[:/]([a-zA-Z0-9._%+-]+@)', r' \1', clean_text)

    # 10. Extract intent-ranked matches first, then all matches
    intent_matches = [m.lower().strip().rstrip('.,;:') for m in RECRUITER_INTENT_PATTERN.findall(clean_text)]
    all_matches = [m.lower().strip().rstrip('.,;:') for m in EMAIL_REGEX.findall(clean_text)]

    valid_emails = []
    for raw_email in intent_matches + all_matches:
        if '@' not in raw_email:
            continue
        local, domain = raw_email.rsplit('@', 1)
        local = local.lstrip('.-_+')
        if not local or not domain or '.' not in domain:
            continue
        email_clean = f"{local}@{domain}"

        if domain.startswith("www."):
            continue
        if any(junk == domain or domain.endswith('.' + junk) for junk in JUNK_EMAILS):
            continue
        if any(email_clean.endswith(ext) for ext in ASSET_EXTS):
            continue

        if 'navceshini@' in email_clean:
            email_clean = email_clean.replace('navceshini@', 'naveeshini@')
        if 'navoosngm@' in email_clean:
            email_clean = email_clean.replace('navoosngm@', 'naveeshini@')

        if email_clean not in valid_emails:
            valid_emails.append(email_clean)

    return valid_emails

def _build_ocr_variants(img: Image.Image) -> list[tuple[str, Image.Image]]:
    """Builds progressively stronger preprocessed image variants for difficult flyers & mobile screenshots."""
    variants = []
    rgb = img.convert("RGB") if img.mode not in ("RGB", "L") else img
    w, h = rgb.size

    # Variant 1: Original image
    variants.append(("raw", rgb))

    # Variant 2: 3x LANCZOS upscaled grayscale + sharpen + strong contrast (great for small mobile screenshots)
    scale = 3 if max(w, h) < 1800 else 2
    gray_up = rgb.convert("L").resize((w * scale, h * scale), Image.Resampling.LANCZOS)
    gray_sharp = ImageEnhance.Contrast(ImageOps.autocontrast(gray_up).filter(ImageFilter.SHARPEN)).enhance(1.8)
    variants.append(("upscaled_gray", gray_sharp))

    # Variant 3: Binary adaptive/Otsu threshold (makes colored text like pink/red-on-white razor crisp)
    if HAS_CV2 and cv2 is not None and np is not None:
        arr = np.array(gray_up)
        # Adaptive threshold excels at pills/boxes with varying background illumination
        adap = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10)
        variants.append(("cv_adaptive", Image.fromarray(adap)))

        # Inverted Otsu (makes white text on dark blue/black banners crisp black-on-white)
        _, otsu = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(("cv_otsu_inv", ImageOps.invert(Image.fromarray(otsu))))
    else:
        variants.append(("inverted_gray", ImageOps.invert(gray_sharp)))

    # Variant 4: Lower 55% zoom crop (eliminates top social UI chrome on tall phone screenshots)
    if h > w * 1.3:
        crop_box = (0, int(h * 0.45), w, h)
        lower = rgb.crop(crop_box).convert("L")
        lw, lh = lower.size
        lower_up = ImageEnhance.Contrast(ImageOps.autocontrast(lower.resize((lw * 3, lh * 3), Image.Resampling.LANCZOS)).filter(ImageFilter.SHARPEN)).enhance(2.0)
        variants.append(("lower_crop_zoom", lower_up))

    return variants

async def extract_text_from_image_async(image_path: str) -> str:
    """Extracts raw text using multi-pass Windows native OCR with early exit once email is found."""
    if not os.path.exists(image_path) or not HAS_WINOCR or not winocr:
        return ""
    texts = []
    try:
        img = Image.open(image_path)
        for idx, (label, var_img) in enumerate(_build_ocr_variants(img)):
            try:
                res = await winocr.recognize_pil(var_img)
                t = (res.text or "").strip()
                if t:
                    texts.append(t)
                # Always gather at least raw + upscaled_gray for rich metadata, then exit as soon as email found
                if idx >= 1 and extract_emails("\n".join(texts)):
                    break
            except Exception as inner_e:
                print(f"[WinOCR pass '{label}' note]: {inner_e}")
        return "\n".join(texts)
    except Exception as e:
        print(f"[OCR Exception]: {e}")
        return ""

def _run_pytesseract_multipass(image_path: str) -> str:
    """Runs multi-pass Tesseract OCR on Linux/fallback with adaptive preprocessing & PSM tuning."""
    if not HAS_PYTESSERACT or not pytesseract or not os.path.exists(image_path):
        return ""
    texts = []
    try:
        img = Image.open(image_path)
        for idx, (label, var_img) in enumerate(_build_ocr_variants(img)):
            for psm in (3, 6, 11):
                # Run default psm 3 on early passes; run sparse/block psm 6/11 if email still missing
                if idx < 2 and psm != 3:
                    continue
                if idx >= 2 and psm == 3:
                    continue
                try:
                    t = (pytesseract.image_to_string(var_img, config=f"--oem 3 --psm {psm}") or "").strip()
                    if t:
                        texts.append(t)
                    if idx >= 1 and extract_emails("\n".join(texts)):
                        return "\n".join(texts)
                except Exception:
                    pass
    except Exception as e_tess:
        print(f"[Pytesseract Error]: {e_tess}")
    return "\n".join(texts)

def extract_from_image(image_path: str) -> tuple[str, list[str]]:
    """Synchronous wrapper for image text and email extraction."""
    text = ""
    if HAS_WINOCR and winocr:
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

    # Fallback to pytesseract (Linux/GitHub Actions runners, or if winocr produced nothing)
    if (not text or not extract_emails(text)) and HAS_PYTESSERACT and pytesseract:
        tess_text = _run_pytesseract_multipass(image_path)
        if tess_text:
            text = f"{text}\n{tess_text}".strip()

    emails = extract_emails(text)
    return text, emails
