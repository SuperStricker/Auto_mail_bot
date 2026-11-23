"""
Universal Application Engine
Parses links, flyers/photos, and pasted text.
Extracts job metadata, selects CV, and triggers cold email dispatch.
"""

import os
import re
import json
import time
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime

from config import (
    BASE_DIR, TEMP_DIR, SENT_HISTORY_FILE, ASK_FREELLM_TOOL
)
from ocr_engine import extract_from_image, extract_emails
from email_sender import (
    send_cold_email, detect_explicit_subject, extract_tailored_skills,
    create_email_body, select_cv_for_location, clean_location
)

JUNK_ROLE_WORDS = {
    "alert", "hiring", "urgent", "hiring alert", "job alert", "urgent hiring", 
    "immediate", "opening", "vacancy", "requirement", "opportunity", "we are hiring",
    "looking for", "role", "position", "designation", "job", "update", "notice",
    "location", "company", "null", "none"
}

def extract_company_from_domain(email: str) -> str:
    """Extracts a clean company name from recruiter email domain if not generic."""
    if not email or "@" not in email:
        return ""
    domain = email.split("@")[1].lower()
    generic = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "rediffmail.com", "icloud.com", "protonmail.com", "zoho.com"]
    if domain in generic:
        return ""
    base = re.sub(r'\.(com|co\.[a-z]{2}|[a-z]{2,3}|org|net)$', '', domain)
    parts = re.split(r'[-_.]', base)
    clean_parts = [p.capitalize() for p in parts if p and p.lower() not in ["pvt", "ltd", "corp", "inc"]]
    return " ".join(clean_parts)

def sanitize_job_role(raw_role: str, text: str = "") -> str:
    """Sanitizes extracted role, strips junk buzzwords, and ensures genuine IT designation."""
    clean = (raw_role or "").strip()
    clean = re.sub(r'^(?:hiring\s+alert|job\s+alert|urgent\s+hiring|we\s+are\s+hiring|hiring|alert|urgent)\s*[:|–-]?\s*', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\s*\((?:ksa|india|uae|dubai|delhi|ncr|mumbai|pune|bangalore|[a-z\s]+)\)\s*$', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\s*\d+\s*(?:content|pm|am|followers|kb|mb)?.*$', '', clean, flags=re.IGNORECASE).strip()

    if not clean or clean.lower() in JUNK_ROLE_WORDS or len(clean) < 3:
        clean = ""

    if "|" in clean or "–" in clean or "-" in clean:
        parts = re.split(r'[:|–-]', clean)
        for p in parts:
            p_strip = p.strip()
            if p_strip.lower() not in JUNK_ROLE_WORDS and len(p_strip) >= 3:
                clean = p_strip
                break

    if not clean or clean.lower() in JUNK_ROLE_WORDS:
        known_roles = [
            (r'\bit\s+executive\b', 'IT Executive'),
            (r'\bit\s+head\b', 'IT Head'),
            (r'\bservice\s+delivery\s+manager\b', 'Service Delivery Manager'),
            (r'\bit\s+manager\b', 'IT Manager'),
            (r'\bit\s+lead\b|\binfrastructure\s+lead\b', 'IT Infrastructure Lead'),
            (r'\bdesktop\s+support\s*(?:engineer|executive|lead)?\b', 'Desktop Support Engineer'),
            (r'\bsystem\s+admin(?:istrat(?:or|ion))?\b', 'System Administrator'),
            (r'\bnetwork\s+(?:admin(?:istrat(?:or|ion))?|engineer)\b', 'Network Engineer'),
            (r'\bhelpdesk\s*(?:engineer|executive|analyst)?\b|\bservice\s+desk\s*(?:engineer|analyst)?\b', 'Service Desk Engineer'),
            (r'\bm365\b|\bintune\b|\bcloud\s+support\b', 'M365 & Cloud Support Engineer'),
            (r'\btechnical\s+support\s*(?:engineer|executive)?\b|\btech\s+support\b', 'Technical Support Engineer'),
            (r'\bit\s+support\s*(?:engineer|executive|specialist)?\b', 'IT Support Specialist'),
        ]
        combined = f"{raw_role}\n{text}"
        for pat, title in known_roles:
            if re.search(pat, combined, re.IGNORECASE):
                clean = title
                break

    if not clean:
        clean = "IT Support & System Administrator"

    if clean.isupper() and len(clean) > 3:
        clean = " ".join([w.upper() if w.upper() in ["IT", "L1", "L2", "L3", "AD", "M365", "CCTV", "LAN", "WAN", "NOC", "SOC"] else w.capitalize() for w in clean.split()])

    return clean

def parse_post_intelligence(text: str) -> dict:
    """Analyzes job post text with FreeLLM if available, otherwise pure regex."""
    clean_text = text.strip()[:4000]
    role, comp, loc, subj, recruiter = "", "", "", "", ""

    if os.path.exists(ASK_FREELLM_TOOL):
        try:
            prompt = (
                "Extract JSON with these exact keys from the following job post:\n"
                "- job_role: Exact technical job title/designation hiring for (e.g. IT Executive, IT Head, Desktop Support Engineer, Service Delivery Manager, System Administrator, Network Engineer). Do NOT return words like 'Alert', 'Hiring', 'Urgent', or locations.\n"
                "- company: Exact hiring company or consultancy name (null if unknown)\n"
                "- location: Job city, state, or country (e.g. Saudi Arabia, Dubai UAE, Udaipur, Noida NCR) (null if unknown)\n"
                "- explicit_subject: Exact subject line if recruiter explicitly requested one (e.g. 'Subject: ...'), else null\n"
                "- recruiter_name: Recruiter or contact person name if given, else null\n"
                "Return ONLY valid JSON.\n\n"
                f"Job Post:\n{clean_text}"
            )
            result = subprocess.run(
                ["python", ASK_FREELLM_TOOL, "--prompt", prompt],
                capture_output=True,
                text=True,
                timeout=20
            )
            raw_out = result.stdout.strip()
            if "```json" in raw_out:
                raw_out = raw_out.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_out:
                raw_out = raw_out.split("```")[1].split("```")[0].strip()

            parsed = json.loads(raw_out)
            role = sanitize_job_role(parsed.get("job_role", ""), clean_text)
            comp = (parsed.get("company") or "").strip()
            loc = clean_location(parsed.get("location", ""))
            subj = (parsed.get("explicit_subject") or "").strip()
            recruiter = (parsed.get("recruiter_name") or "").strip()
        except Exception:
            pass

    if not role or role.lower() in JUNK_ROLE_WORDS:
        pre_cleaned = re.sub(r'^(?:hiring\s+alert|job\s+alert|urgent\s+hiring|we\s+are\s+hiring|hiring|alert|urgent)\s*[:|–-]?\s*', '', clean_text, flags=re.IGNORECASE)
        m_role = re.search(r'(?:WE ARE HIRING|WE\'RE HIRING|HIRING|URGENT HIRING|LOOKING FOR|ROLE|POSITION|OPENING FOR|DESIGNATION)\s*[:|–-]?\s*([A-Za-z0-9 /&+().-]{3,50})', pre_cleaned, re.IGNORECASE)
        if m_role:
            role = sanitize_job_role(m_role.group(1).strip(), clean_text)

    if not role or role.lower() in JUNK_ROLE_WORDS:
        role = sanitize_job_role("", clean_text)

    if not comp:
        m_comp = re.search(r'(?:Company|Organization)\s*[:|-]?\s*([A-Za-z0-9 &.,\'-]+)', clean_text, re.IGNORECASE)
        if m_comp:
            comp = m_comp.group(1).strip()
        else:
            m_comp = re.search(r'([A-Z][A-Za-z0-9 &.,\'-]+(?:Services|Consultancy|Technologies|Solutions|Infotech|Infosystems|Pvt Ltd|Private Limited|Corp|LLP|Inc|Group|Holdings))\s+(?:is hiring|is looking|hiring|looking)', clean_text)
            if m_comp:
                comp = m_comp.group(1).strip()

    if not loc:
        m_loc = re.search(r'(?:📍\s*)?(?:Location|Place)\s*[:|-]?\s*([A-Za-z0-9 ,()/.-]+)', clean_text, re.IGNORECASE)
        if m_loc:
            loc = clean_location(m_loc.group(1).split("\n")[0])
        else:
            for country_pat in [r'\bSaudi\s+Arabia\b', r'\bKSA\b', r'\bUAE\b', r'\bDubai\b', r'\bQatar\b', r'\bDoha\b', r'\bOman\b', r'\bKuwait\b', r'\bBahrain\b', r'\bGCC\b']:
                m_country = re.search(country_pat, clean_text, re.IGNORECASE)
                if m_country:
                    loc = m_country.group(0)
                    break

    if not subj:
        subj = detect_explicit_subject(clean_text)

    return {
        "job_role": role,
        "company": comp,
        "location": loc,
        "explicit_subject": subj,
        "recruiter_name": recruiter
    }

def fetch_web_post(url: str) -> tuple[str, list[str]]:
    """Fetches web post text and emails with DOM expansion, mailto extraction & urllib fallback."""
    print(f"[Engine] Fetching Web URL: {url}")
    post_text = ""
    emails = []

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page.goto(url, wait_until="domcontentloaded", timeout=35000)
            time.sleep(2)

            # 1. Expand "see more" / "...more" if present
            try:
                see_more = page.query_selector("button.feed-shared-inline-show-more-text__see-more-less-toggle, button.see-more, button[aria-label*='more']")
                if see_more:
                    see_more.click(timeout=3000)
                    time.sleep(1)
            except Exception:
                pass

            # 2. Extract DOM text
            elem = page.query_selector("main") or page.query_selector("article") or page.query_selector("body")
            if elem:
                post_text = elem.inner_text() or ""

            # 3. Extract raw HTML & unquote mailto links
            raw_html = page.content() or ""
            unquoted_html = urllib.parse.unquote(raw_html)
            mailtos = re.findall(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', unquoted_html, re.IGNORECASE)
            for m in mailtos:
                clean_m = m.lower().strip()
                if clean_m not in emails and not any(junk in clean_m for junk in ["example.com", "w3.org", "sentry.io"]):
                    emails.append(clean_m)

            browser.close()
    except Exception as e:
        print(f"[Playwright Notice]: {e}. Attempting urllib fetch.")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_html = resp.read().decode('utf-8', errors='ignore')
                unquoted_html = urllib.parse.unquote(raw_html)
                mailtos = re.findall(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', unquoted_html, re.IGNORECASE)
                for m in mailtos:
                    clean_m = m.lower().strip()
                    if clean_m not in emails and not any(junk in clean_m for junk in ["example.com", "w3.org", "sentry.io"]):
                        emails.append(clean_m)
                post_text = re.sub(r'<[^>]+>', ' ', raw_html)
        except Exception as e2:
            print(f"[Urllib Fetch Error]: {e2}")

    for em in extract_emails(post_text):
        if em not in emails:
            emails.append(em)

    return post_text, emails

def record_history(email: str, role: str, company: str, location: str, post_url: str, cv_file: str):
    """Saves sent email record into sent_history.json."""
    data = {"sent_emails": [], "sent_posts": [], "history": []}
    if os.path.exists(SENT_HISTORY_FILE):
        try:
            with open(SENT_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    if email not in data["sent_emails"]:
        data["sent_emails"].append(email)
    if post_url and post_url not in data["sent_posts"]:
        data["sent_posts"].append(post_url)

    data["history"].append({
        "timestamp": datetime.now().isoformat(),
        "email": email,
        "role": role,
        "company": company,
        "location": location,
        "cv_attached": cv_file,
        "post_url": post_url
    })

    with open(SENT_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def process_and_apply(input_source: str, is_image_path: bool = False) -> dict:
    """Universal Entrypoint: processes URL, raw text, or flyer image and dispatches cold email."""
    post_text = ""
    emails = []
    post_url = ""

    if is_image_path:
        print(f"[Engine] Processing image file: {input_source}")
        post_text, emails = extract_from_image(input_source)
    else:
        raw_input = input_source.strip()
        url_match = re.search(r'https?://[^\s]+', raw_input)
        if url_match:
            post_url = url_match.group(0)
            post_text, emails = fetch_web_post(post_url)
        else:
            post_text = raw_input
            emails = extract_emails(post_text)

    for e in extract_emails(post_text):
        if e not in emails:
            emails.append(e)

    if not emails:
        return {
            "success": False,
            "error": "Post ya flyer photo me recruiter ki email nahi mili. Kripya check karein ya HR ki email sath me likh kar bhejein."
        }

    meta = parse_post_intelligence(post_text)
    target_email = emails[0]

    job_role = meta["job_role"]
    company = meta["company"]
    if not company or company.lower() in ["hiring team", "recruiter", "unknown", ""]:
        company = extract_company_from_domain(target_email)
    if not company:
        company = "Hiring Team"

    location = clean_location(meta["location"])

    ok, msg, cv_filename, is_intl = send_cold_email(
        to_email=target_email,
        job_role=job_role,
        company=company,
        location=location,
        post_text=post_text
    )

    if ok:
        record_history(target_email, job_role, company, location, post_url, cv_filename)
        subject, _ = create_email_body(job_role, target_email, company, location, post_text, cv_filename)
        return {
            "success": True,
            "role": job_role,
            "company": company if company != "Hiring Team" else "",
            "location": location,
            "subject": subject,
            "cv_attached": cv_filename,
            "is_international": is_intl,
            "emails": emails,
            "post_url": post_url
        }
    else:
        return {
            "success": False,
            "error": f"Email sending failed: {msg}"
        }
