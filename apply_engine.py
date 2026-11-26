"""
Universal Application Engine
Parses links (including attached flyer images via OCR), flyers/photos, and pasted text.
Extracts job metadata, selects CV, and triggers cold email dispatch.
"""

import os
import re
import json
import time
import socket
import html as html_lib
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime

from config import (
    BASE_DIR, TEMP_DIR, SENT_HISTORY_FILE, ASK_FREELLM_TOOL, LINKEDIN_LI_AT
)
from ocr_engine import extract_from_image, extract_emails
from email_sender import (
    send_cold_email, detect_explicit_subject, extract_tailored_skills,
    create_email_body, select_cv_for_location, clean_location
)

JUNK_ROLE_WORDS = {
    "alert", "hiring", "urgent", "hiring alert", "job alert", "urgent hiring",
    "immediate", "opening", "vacancy", "requirement", "opportunity", "we are hiring",
    "we're hiring", "looking for", "role", "position", "designation", "job",
    "update", "notice", "location", "company", "null", "none", "now", "india",
    "remote", "uae", "dubai", "ksa", "saudi arabia"
}

JUNK_ROLE_PHRASES = (
    "our client", "multiple positions", "urgent basis", "immediate joiner",
    "below role", "following role", "your resume", "check below", "please share",
    "experienced professionals", "candidates with", "to join our", "to join the",
    "join our team", "we are looking", "share your", "apply now"
)

ROLE_ACRONYMS = {
    "IT", "L1", "L2", "L3", "AD", "M365", "O365", "EUC", "ITSM", "ITIL",
    "CCTV", "LAN", "WAN", "NOC", "SOC", "IAM", "MDM", "SCCM", "VPN", "SLA",
    "US", "UK", "UAE", "KSA", "AV"
}
LOWER_CONNECTORS = {"and", "or", "for", "of", "in", "at", "to"}

# User's target headlines (aligned with Naukri Alart + CV) ordered most-specific first.
# None => preserve exact matched headline text (cleanly formatted).
USER_HEADLINE_PATTERNS = [
    (r'\bl[1-3]\s*[-–/]?\s*it\s+infrastructure(?:\s*&\s*support)?\s*(?:engineer|lead|specialist)?\b', None),
    (r'\bl1\s*/\s*l2\s+desktop\s+support(?:\s+(?:engineer|executive|technician))?\b', 'L1/L2 Desktop Support Engineer'),
    (r'\bl[1-3]\s+service\s+desk(?:\s+(?:support|engineer|analyst|technician))?\b', None),
    (r'\bl[1-3]\s+(?:it\s+)?helpdesk(?:\s+(?:support|engineer|analyst|technician))?\b', None),
    (r'\bl[1-3]\s+(?:desktop|technical|it)\s+support(?:\s+(?:engineer|executive|specialist|technician|analyst))?\b', None),
    (r'\bsystem\s+engineer\s+service\s+ops\b', 'System Engineer Service Ops'),
    (r'\bservice\s+ops\s+engineer\b', 'Service Ops Engineer'),
    (r'\bservice\s+delivery\s+manager\b', 'Service Delivery Manager'),
    (r'\bservice\s+desk\s+manager\b', 'Service Desk Manager'),
    (r'\bservice\s+desk\s+(?:engineer|analyst|specialist|support)\b', None),
    (r'\bhelpdesk\s+support(?:\s+engineer)?\b|\bit\s+helpdesk(?:\s+(?:engineer|support|technician))?\b|\bhelp\s+desk\s+(?:engineer|analyst|support|technician)\b', None),
    (r'\bdesktop\s+support\s+(?:engineer|executive|specialist|technician|lead)\b|\bdesktop\s+support\b', 'Desktop Support Engineer'),
    (r'\bdeskside\s+support(?:\s+(?:engineer|analyst|specialist|technician))?\b', 'Deskside Support Engineer'),
    (r'\btechnical\s+support\s+(?:engineer|executive|specialist|analyst)\b|\btech\s+support\s+engineer\b', 'Technical Support Engineer'),
    (r'\bit\s+and\s+system\s+support(?:\s+(?:engineer|specialist))?\b', 'IT and System Support'),
    (r'\bit\s+infrastructure(?:\s*&\s*support|\s*&\s*operations)?\s+(?:engineer|lead|specialist|administrator)\b', None),
    (r'\bit\s+operations\s+lead\b', 'IT Operations Lead'),
    (r'\bit\s+support\s+manager\b', 'IT Support Manager'),
    (r'\bassistant\s+manager\s*[-–]?\s*it\b', 'Assistant Manager IT'),
    (r'\bit\s+manager\b', 'IT Manager'),
    (r'\bit\s+head\b', 'IT Head'),
    (r'\bsenior\s+executive\s*[-–|/]?\s*it\b', 'Senior Executive IT'),
    (r'\bit\s+executive\b', 'IT Executive'),
    (r'\bsenior\s+system\s+engineer\b', 'Senior System Engineer'),
    (r'\bit\s+systems?\s+administrator(?:\s*/\s*it\s+operations(?:\s+contractor)?)?\b', None),
    (r'\bsystem\s+administrator\b|\bsystems?\s+admin(?:istrator)?\b', 'System Administrator'),
    (r'\bsystem\s+support(?:\s+(?:engineer|specialist|analyst))?\b', 'System Support Engineer'),
    (r'\bsystem\s+engineer\b', 'System Engineer'),
    (r'\bmicrosoft\s*365\s+(?:engineer|administrator|lead|specialist)\b|\bm365\s+(?:lead|engineer|administrator)\b', None),
    (r'\bend\s+user\s+computing(?:\s*\(euc\))?(?:\s+(?:engineer|specialist|lead))?\b|\beuc\s+(?:engineer|specialist|support)\b', 'End User Computing (EUC) Engineer'),
    (r'\bwintel\s+(?:administrator|engineer|lead)\b', None),
    (r'\bit\s+site\s+engineer\b|\bsite\s+engineer\b', 'IT Site Engineer'),
    (r'\bit\s+support\s+technician\b', 'IT Support Technician'),
    (r'\bit\s+technician\b', 'IT Technician'),
    (r'\bit\s+specialist\b', 'IT Specialist'),
    (r'\bsupport\s+analyst\b', 'Support Analyst'),
    (r'\bit\s+analyst\b', 'IT Analyst'),
    (r'\bsupport\s+engineer\b', 'Support Engineer'),
    (r'\bnetwork\s+(?:admin(?:istrat(?:or|ion))?|engineer)\b', 'Network Engineer'),
    (r'\bit\s+support\s+(?:engineer|executive|specialist)\b|\bit\s+support\b', None),
]

LINKEDIN_LOGIN_MARKERS = (
    "/signup/cold-join", "/uas/login", "/login", "/authwall", "join linkedin now"
)

def _format_role_title(title: str) -> str:
    """Normalizes role casing and slash spacing while preserving acronyms (IT, L1-L3, L1/L2, M365)."""
    s = re.sub(r'\s*/\s*', ' / ', (title or "").strip())
    # Keep compact level slashes like L1/L2 or L2/L3 without spaces
    s = re.sub(r'\b(L[1-3])\s*/\s*(L[1-3])\b', r'\1/\2', s, flags=re.IGNORECASE)
    s = re.sub(r'\s{2,}', ' ', s)
    if not s:
        return ""
    tokens = s.split(" ")
    formatted = []
    for idx, tok in enumerate(tokens):
        if tok in {"/", "-", "–", "&"}:
            formatted.append(tok)
            continue
        # Handle level/compact slashes like L1/L2 and hyphenated tokens like L1-L2
        slash_parts = tok.split("/")
        out_slash = []
        for slp in slash_parts:
            subparts = slp.split("-")
            out_parts = []
            for sp in subparts:
                up = sp.upper()
                low = sp.lower()
                if up in ROLE_ACRONYMS:
                    out_parts.append(up)
                elif idx > 0 and low in LOWER_CONNECTORS and not tok.isupper():
                    out_parts.append(low)
                elif sp.isupper() or sp.islower():
                    out_parts.append(sp.capitalize())
                else:
                    out_parts.append(sp)
            out_slash.append("-".join(out_parts))
        formatted.append("/".join(out_slash))
    return " ".join(formatted)

def _match_user_headline(text: str) -> str:
    """Matches text against the user's configured IT support/sysadmin target headlines."""
    if not text:
        return ""
    for pat, canonical in USER_HEADLINE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            if canonical:
                return canonical
            matched = re.sub(r'\s*[-–]\s*', ' - ', m.group(0).strip())
            return _format_role_title(matched)
    return ""

def _is_prose_or_junk_role(text: str) -> bool:
    """Detects generic recruiter prose/noise that should not become the email subject role."""
    low = (text or "").strip().lower()
    if not low or low in JUNK_ROLE_WORDS or len(low) < 3:
        return True
    if any(jp in low for jp in JUNK_ROLE_PHRASES):
        return True
    words = low.split()
    if len(words) > 8:
        return True
    if re.search(r'\b(?:years?|yrs?|experience|exp|salary|ctc|lpa|aed)\b', low):
        return True
    return False

def _strip_linkedin_comments(text: str) -> str:
    """Removes LinkedIn comments & footer chrome so commenter bios/emails don't pollute post parsing."""
    if not text:
        return ""
    markers = [
        r'\n(?:\d+\s*\n)?(?:\d+\s+Comments?\s*\n)?Like\s*\nComment\s*\nShare\b',
        r'\n\d+\s+Comments?\s*\nLike\b',
        r'\nTo view or add a comment,\s*sign in\b',
        r'\nSee more comments\b',
    ]
    cut_pos = len(text)
    for pat in markers:
        m = re.search(pat, text, re.IGNORECASE)
        if m and m.start() < cut_pos and m.start() > 40:
            cut_pos = m.start()
    return text[:cut_pos].strip()

def extract_company_from_domain(email: str) -> str:
    """Extracts a clean company name from recruiter email domain if not generic."""
    if not email or "@" not in email:
        return ""
    domain = email.split("@")[1].lower()
    generic = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "rediffmail.com", "icloud.com", "protonmail.com", "zoho.com"]
    if domain in generic:
        return ""
    base = re.sub(r'\.(com|co\.[a-z]{2}|com\.[a-z]{2}|[a-z]{2,3}|org|net|io|ai|cloud|dev|systems|solutions|services)$', '', domain)
    parts = re.split(r'[-_.]', base)
    clean_parts = [p.capitalize() for p in parts if p and p.lower() not in ["pvt", "ltd", "corp", "inc"]]
    return " ".join(clean_parts)

def sanitize_job_role(raw_role: str, text: str = "") -> str:
    """Sanitizes extracted role, strips junk buzzwords, and ensures genuine IT designation."""
    clean = (raw_role or "").strip()
    clean = re.sub(r'^[^\w(]+', '', clean).strip()
    clean = re.sub(
        r'^(?:hiring\s+alert|job\s+alert|urgent\s+hiring|we\s+are\s+hiring|we\'re\s+hiring|hiring\s+for|hiring|alert|urgent|looking\s+for|position|role|designation|job\s+title|opening\s+for|vacancy\s+for)\s*[!:|–—\-\s]*',
        '',
        clean,
        flags=re.IGNORECASE
    ).strip()
    clean = re.sub(r'^[^\w(]+|[^\w)]+$', '', clean).strip()
    clean = re.sub(
        r'\s*\((?:ksa|india|uae|dubai|abu\s+dhabi|qatar|doha|delhi(?:\s+ncr)?|ncr|noida|gurgaon|gurugram|mumbai|pune|bangalore|bengaluru|hyderabad|chennai|kolkata|remote|hybrid|onsite|on-site|wfh|urgent|immediate|contract|full[\s-]?time)\)\s*$',
        '',
        clean,
        flags=re.IGNORECASE
    ).strip()
    # Strip LinkedIn DOM/UI noise suffixes ONLY when an explicit unit/noise word follows digits
    clean = re.sub(r'\s*\b\d+\s+(?:content|comments?|reactions?|likes?|followers?|connections?|views?)\b.*$', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\s*\b\d+(?::\d+)?\s*(?:pm|am|kb|mb|gb)\b.*$', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\s*(?:\||–|—|\s-\s)\s*(?:location|experience|exp|salary|india|uae|dubai|remote|urgent).*$', '', clean, flags=re.IGNORECASE).strip()

    if not clean or clean.lower() in JUNK_ROLE_WORDS or len(clean) < 3:
        clean = ""

    # Split compound banner lines on |, :, –, — or spaced ' - ' (never inside L1-L2 or End-User)
    if clean and re.search(r'[:|–—]|\s-\s', clean):
        parts = [p.strip(" -–—:|") for p in re.split(r'[:|–—]|\s+-\s+', clean) if p.strip(" -–—:|")]
        if len(parts) >= 2 and re.fullmatch(r'L[1-3]', parts[0], re.IGNORECASE) and not _is_prose_or_junk_role(parts[1]):
            clean = f"{parts[0].upper()} - {parts[1]}"
        else:
            picked = ""
            for p_strip in parts:
                if not _is_prose_or_junk_role(p_strip) and len(p_strip) >= 3:
                    picked = p_strip
                    break
            clean = picked

    # If extracted candidate looks like prose (e.g. "a skilled Desktop Support Engineer to join..."),
    # extract the matching user headline from inside it or fall back to post headline matching.
    if clean and _is_prose_or_junk_role(clean):
        matched_in_cand = _match_user_headline(clean)
        clean = matched_in_cand if matched_in_cand else ""

    if not clean or clean.lower() in JUNK_ROLE_WORDS:
        clean = _match_user_headline(raw_role) or _match_user_headline(text)

    if not clean:
        clean = "IT Support & System Administrator"

    return _format_role_title(clean)

def _extract_headline_role(clean_text: str) -> str:
    """Extracts standalone job title lines near top of post/JD when no explicit 'Hiring:' prefix exists."""
    role_keywords = re.compile(
        r'\b(?:engineer|administrator|admin|analyst|manager|executive|lead|specialist|architect|consultant|technician|coordinator|officer|support)\b',
        re.IGNORECASE
    )
    domain_keywords = re.compile(
        r'\b(?:it|desktop|support|system|systems|network|infrastructure|cloud|azure|aws|m365|intune|service\s*desk|help\s*desk|helpdesk|noc|soc|iam|devops|server|end\s*user|euc|l1|l2|l3|hardware|technical)\b',
        re.IGNORECASE
    )
    skip_line = re.compile(
        r'^(?:about|key\s+responsibilities|responsibilities|must\s+have|requirements|required\s+skills|qualifications|skills|why\s+join|benefits|perks|send\s+|share\s+|apply\s+|interested|what\s+we|http|www\.|•|\*|-|📍|💼|🚀|🕒|💰)',
        re.IGNORECASE
    )
    for raw_line in clean_text.splitlines()[:30]:
        line = re.sub(r'^[^\w]+', '', raw_line).strip()
        if not line or len(line) < 6 or len(line) > 75:
            continue
        if skip_line.match(line) or "@" in line or "likes this" in line.lower():
            continue
        words = line.split()
        if not (2 <= len(words) <= 9):
            continue
        if role_keywords.search(line) and domain_keywords.search(line):
            cand = _format_role_title(re.sub(r'^(?:hiring\s+alert|job\s+alert|urgent\s+hiring|we\s+are\s+hiring|we\'re\s+hiring|hiring|alert|urgent)\s*[!:|–—\-\s]*', '', line, flags=re.IGNORECASE).strip())
            if cand and not _is_prose_or_junk_role(cand):
                return cand
    return ""

def _freellm_available(host: str = "127.0.0.1", port: int = 31415, timeout: float = 0.25) -> bool:
    """Fast local port probe so offline environments don't stall waiting for FreeLLM."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

def parse_post_intelligence(text: str) -> dict:
    """Analyzes job post text with FreeLLM if available, otherwise multi-tier regex + headline matcher."""
    body_only = _strip_linkedin_comments(text)
    clean_text = body_only.strip()[:6000]
    role, comp, loc, subj, recruiter = "", "", "", "", ""

    if os.path.exists(ASK_FREELLM_TOOL) and _freellm_available():
        try:
            prompt = (
                "Extract JSON with these exact keys from the following job post:\n"
                "- job_role: Exact technical job title/designation hiring for (e.g. L1 Service Desk Support, IT Executive, Desktop Support Engineer, Service Delivery Manager, System Administrator). Use the exact role headline from the post if stated; never return words like 'Alert', 'Hiring', 'Urgent', or locations.\n"
                "- company: Exact hiring company or consultancy name (null if unknown)\n"
                "- location: Job city, state, or country (e.g. Saudi Arabia, Dubai UAE, Udaipur, Noida NCR, India) (null if unknown)\n"
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

    # Tier 1: Explicit labeled role fields (Position:, Role:, Job Title:, Designation:)
    if not role or _is_prose_or_junk_role(role):
        for m_lbl in re.finditer(
            r'(?:POSITION|ROLE|JOB\s+TITLE|DESIGNATION|OPENING\s+FOR|VACANCY\s+FOR)\s*[:–—-]+\s*([^\n\r]{3,75})',
            clean_text,
            re.IGNORECASE
        ):
            cand = m_lbl.group(1).strip()
            if not _is_prose_or_junk_role(cand):
                role = sanitize_job_role(cand, clean_text)
                break

    # Tier 2: Explicit hiring banner headers (WE ARE HIRING | <Title>, HIRING - <Title>, Hiring : <Title>)
    if not role or _is_prose_or_junk_role(role):
        for m_hire in re.finditer(
            r'(?:WE\s+ARE\s+HIRING|WE\'RE\s+HIRING|URGENT\s+HIRING|HIRING\s+FOR|HIRING)\s*[!:|–—\-\s]+([^\n\r]{3,75})',
            clean_text,
            re.IGNORECASE
        ):
            cand = m_hire.group(1).strip()
            # Reject generic prose like "experienced professionals..." unless a clean headline sits inside
            cand_clean = re.sub(r'^[!:|–—\-\s]+', '', cand).strip()
            if _is_prose_or_junk_role(cand_clean):
                matched = _match_user_headline(cand_clean)
                if matched:
                    role = matched
                    break
                continue
            role = sanitize_job_role(cand_clean, clean_text)
            break

    # Tier 3: Headline line near top of post OR match user's configured target headlines in post body
    if not role or _is_prose_or_junk_role(role):
        role = _extract_headline_role(clean_text)

    if not role or _is_prose_or_junk_role(role):
        role = _match_user_headline(clean_text)

    # Tier 4: Final fallback
    if not role or role.lower() in JUNK_ROLE_WORDS:
        role = sanitize_job_role("", clean_text)

    if not comp:
        m_comp = re.search(r'(?:Why\s+Join|About)\s+([A-Z][A-Za-z0-9 &\'.-]{2,40})[?!]', clean_text)
        if m_comp and m_comp.group(1).lower() not in ("the role", "the job", "this role", "this opportunity", "us"):
            comp = m_comp.group(1).strip()
    if not comp:
        m_comp = re.search(r'(?:Company|Organization)\s*[:|-]+\s*([A-Za-z0-9 &.,\'-]+)', clean_text, re.IGNORECASE)
        if m_comp:
            cand_comp = m_comp.group(1).strip().split("\n")[0].strip()
            if cand_comp.lower() not in ("contact", "hiring team", "recruiter", "unknown", "n/a", "na", "confidential", ""):
                comp = cand_comp
    if not comp:
        m_comp = re.search(r'(?<!#)([A-Z][A-Za-z0-9 &.,\'-]+(?:Services|Consultancy|Technologies|Solutions|Infotech|Infosystems|Pvt\.?\s*Ltd\.?|Private Limited|Corp|LLP|Inc|Group|Holdings))\s*(?:\n|is\s+hiring|is\s+looking|hiring|looking|·|\|)', clean_text)
        if m_comp:
            comp = m_comp.group(1).strip()

    if not loc:
        m_loc = re.search(r'(?:📍\s*)?(?:Location|Place)\s*[:|-]+\s*([A-Za-z0-9 ,()/.-]+)', clean_text, re.IGNORECASE)
        if m_loc:
            loc = clean_location(m_loc.group(1).split("\n")[0])
        else:
            city_country_pats = [
                r'\bSaudi\s+Arabia\b', r'\bKSA\b', r'\bUAE\b', r'\bDubai\b', r'\bAbu\s+Dhabi\b',
                r'\bQatar\b', r'\bDoha\b', r'\bOman\b', r'\bKuwait\b', r'\bBahrain\b', r'\bGCC\b',
                r'\bGreater\s+Noida\b', r'\bNew\s+Delhi\b', r'\bDelhi\s+NCR\b', r'\bNoida\b',
                r'\bGurugram\b', r'\bGurgaon\b', r'\bFaridabad\b', r'\bGhaziabad\b', r'\bDelhi\b',
                r'\bBengaluru\b', r'\bBangalore\b', r'\bHyderabad\b', r'\bPune\b', r'\bMumbai\b',
                r'\bChennai\b', r'\bKolkata\b', r'\bJaipur\b', r'\bChandigarh\b', r'\bLondon\b', r'\bUK\b',
                r'\bIndia\b'
            ]
            for pat in city_country_pats:
                m_city = re.search(pat, clean_text, re.IGNORECASE)
                if m_city:
                    loc = m_city.group(0)
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

def _is_flyer_image_url(src: str) -> bool:
    """Filters out avatars, icons, covers, and logos; keeps hiring flyer / post media URLs."""
    if not src or not src.startswith("http"):
        return False
    low = src.lower()
    skip_tokens = (
        "profile-displayphoto", "profile-displaybackgroundimage", "company-logo",
        "static.licdn.com", "favicon", "/emoji", "1x1", "pixel", "avatar"
    )
    if any(tok in low for tok in skip_tokens):
        return False
    return True

def _extract_html_meta_and_images(raw_html: str) -> tuple[str, list[str], list[str]]:
    """Extracts meta descriptions, mailto emails, and candidate flyer image URLs from raw HTML."""
    meta_parts = []
    emails = []
    candidate_imgs = []

    if not raw_html:
        return "", emails, candidate_imgs

    unquoted_html = html_lib.unescape(urllib.parse.unquote(raw_html))

    # 1. Meta tags (og:title, og:description, description, twitter:description)
    for m in re.finditer(r'<meta[^>]+(?:property|name)=["\'](?:og:title|og:description|description|twitter:description)["\'][^>]+content=["\']([^"\']*)["\']', raw_html, re.IGNORECASE):
        val = html_lib.unescape(m.group(1)).strip()
        if val and "500 million+ members" not in val and val not in meta_parts:
            meta_parts.append(val)

    # 2. Mailto links (skip LinkedIn comment mailtos like ?trk=public_post_comment-text)
    mailtos = re.findall(
        r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,15})(?![^"\'\s]*public_post_comment)',
        unquoted_html,
        re.IGNORECASE
    )
    for m in mailtos:
        clean_m = m.lower().strip()
        if clean_m not in emails and not any(junk in clean_m for junk in ["example.com", "w3.org", "sentry.io", "licdn.com", "linkedin.com"]):
            emails.append(clean_m)

    # 3. Prioritized LinkedIn feedshare images + og:image
    feed_imgs = re.findall(r'https://media\.licdn\.com/dms/image[^\s"\'<>\\]+', raw_html)
    for raw_u in feed_imgs:
        u = html_lib.unescape(raw_u)
        if ("feedshare" in u or "article" in u) and _is_flyer_image_url(u) and u not in candidate_imgs:
            candidate_imgs.append(u)

    for m in re.finditer(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']', raw_html, re.IGNORECASE):
        u = html_lib.unescape(m.group(1)).strip()
        if _is_flyer_image_url(u) and u not in candidate_imgs:
            candidate_imgs.append(u)

    return "\n".join(meta_parts), emails, candidate_imgs

def _is_private_or_blocked_post(final_url: str, text: str, http_status: int = 200) -> bool:
    """Detects whether a post is private, login-walled, or blocked from guest viewing."""
    low_u = (final_url or "").lower()
    low_t = (text or "").lower()
    if http_status in (401, 403, 999):
        return True
    wall_urls = (
        "/signup/cold-join", "/uas/login", "/authwall", "/checkpoint",
        "linkedin.com/login", "/accounts/login", "/login/"
    )
    if any(m in low_u for m in wall_urls):
        return True
    wall_phrases = ("join linkedin now", "sign in to view", "log in to see posts", "this post is private")
    if any(p in low_t for p in wall_phrases) and len(low_t) < 700:
        return True
    return False

def _playwright_fetch(url: str, use_li_at: bool = False) -> tuple[str, str, str, list[str]]:
    """Fetches a URL using Playwright Chromium, returning (final_url, dom_text, raw_html, dom_imgs)."""
    from playwright.sync_api import sync_playwright
    dom_text, raw_html, final_url = "", "", url
    dom_imgs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        if use_li_at and LINKEDIN_LI_AT:
            ctx.add_cookies([{
                "name": "li_at",
                "value": LINKEDIN_LI_AT,
                "domain": ".linkedin.com",
                "path": "/"
            }])
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
        time.sleep(2.5)
        final_url = page.url

        # Expand "see more" / "...more" if present
        try:
            see_more = page.query_selector("button.feed-shared-inline-show-more-text__see-more-less-toggle, button.see-more, button[aria-label*='more']")
            if see_more:
                see_more.click(timeout=3000)
                time.sleep(1)
        except Exception:
            pass

        elem = page.query_selector("main") or page.query_selector("article") or page.query_selector("body")
        if elem:
            dom_text = elem.inner_text() or ""

        raw_html = page.content() or ""

        try:
            imgs = page.eval_on_selector_all("img", """els => els.map(e => ({
                src: e.src || e.getAttribute('data-delayed-url') || '',
                cls: e.className || '',
                w: e.naturalWidth || 0,
                h: e.naturalHeight || 0
            }))""")
            for im in imgs:
                src = (im.get("src") or "").strip()
                cls = (im.get("cls") or "").lower()
                w, h = im.get("w") or 0, im.get("h") or 0
                if "cover-img" in cls or "hue-web-entity" in cls:
                    continue
                if _is_flyer_image_url(src) and (w >= 250 or "feedshare" in src.lower()):
                    if src not in dom_imgs:
                        dom_imgs.append(src)
        except Exception:
            pass

        browser.close()

    return final_url, dom_text, raw_html, dom_imgs

def _ocr_candidate_images(img_urls: list[str]) -> tuple[str, list[str]]:
    """Downloads up to top 3 candidate post images, runs OCR to find embedded emails, and cleans up temp files."""
    combined_ocr = []
    found_emails = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for idx, img_url in enumerate(img_urls[:3]):
        tmp_path = os.path.join(TEMP_DIR, f"web_flyer_{int(time.time())}_{idx}.jpg")
        try:
            print(f"[Engine] Downloading post flyer image #{idx + 1} for OCR...")
            req = urllib.request.Request(img_url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            if len(data) < 2048:
                continue
            with open(tmp_path, "wb") as f:
                f.write(data)
            ocr_txt, img_emails = extract_from_image(tmp_path)
            if ocr_txt:
                combined_ocr.append(ocr_txt)
            for em in img_emails:
                if em not in found_emails:
                    found_emails.append(em)
            if found_emails:
                break
        except Exception as e:
            print(f"[Flyer OCR Notice #{idx + 1}]: {e}")
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    return "\n".join(combined_ocr), found_emails

def _fetch_web_post_detailed(url: str) -> tuple[str, list[str], str]:
    """
    Fetches web post text, meta tags, mailto links, and post flyer images (with OCR fallback).
    Returns: (post_text, emails, block_reason)
    """
    print(f"[Engine] Fetching Web URL: {url}")
    post_text = ""
    raw_html = ""
    final_url = url
    http_status = 200
    emails = []
    candidate_imgs = []
    block_reason = ""

    # 1. Clean Playwright fetch first (no stale cookies)
    try:
        final_url, post_text, raw_html, dom_imgs = _playwright_fetch(url, use_li_at=False)
        for im in dom_imgs:
            if im not in candidate_imgs:
                candidate_imgs.append(im)
    except Exception as e:
        print(f"[Playwright Notice]: {e}. Attempting urllib fetch.")

    # 2. Urllib fallback if Playwright returned empty/failed
    if not raw_html:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                http_status = getattr(resp, "status", 200)
                final_url = resp.geturl()
                raw_html = resp.read().decode('utf-8', errors='ignore')
                post_text = re.sub(r'<[^>]+>', ' ', raw_html)
        except urllib.error.HTTPError as e_http:
            http_status = e_http.code
            print(f"[Urllib HTTP Error]: {e_http}")
        except Exception as e2:
            print(f"[Urllib Fetch Error]: {e2}")

    # 3. Retry with LINKEDIN_LI_AT ONLY if LinkedIn gated the post behind a login wall
    if _is_private_or_blocked_post(final_url, post_text, http_status) and LINKEDIN_LI_AT:
        print("[Engine] Private/login wall hit; retrying with LINKEDIN_LI_AT cookie...")
        try:
            auth_url, auth_text, auth_html, auth_imgs = _playwright_fetch(url, use_li_at=True)
            if not _is_private_or_blocked_post(auth_url, auth_text) and len(auth_text) > len(post_text):
                final_url, post_text, raw_html = auth_url, auth_text, auth_html
                http_status = 200
                for im in auth_imgs:
                    if im not in candidate_imgs:
                        candidate_imgs.append(im)
        except Exception as e_auth:
            print(f"[LinkedIn Auth Retry Notice]: {e_auth}")

    # 4. Extract meta text, mailto emails, and HTML image candidates (ignoring comment sections!)
    raw_html_main = re.split(
        r'(?:comments-comments-list|comment__list|comment__message|social-details-social-activity__comments|feed-shared-social-actions|public_post_comment)',
        raw_html,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0] if raw_html else ""
    meta_text, html_emails, html_imgs = _extract_html_meta_and_images(raw_html_main)
    if not html_imgs and raw_html:
        _, _, html_imgs = _extract_html_meta_and_images(raw_html)
    post_body_only = _strip_linkedin_comments(post_text)
    if meta_text:
        post_text = f"{meta_text}\n{post_text}".strip()
        post_body_only = f"{meta_text}\n{post_body_only}".strip()
    for em in html_emails:
        if em not in emails:
            emails.append(em)
    for im in html_imgs:
        if im not in candidate_imgs:
            candidate_imgs.append(im)

    for em in extract_emails(post_body_only):
        if em not in emails:
            emails.append(em)

    # 5. Still private/blocked/unreadable?
    if not emails and not candidate_imgs and _is_private_or_blocked_post(final_url, post_text, http_status):
        block_reason = "private_post"

    # 6. CRITICAL FALLBACK: If main post text had NO email, OCR any flyer images attached to the post!
    if not emails and candidate_imgs:
        ocr_text, img_emails = _ocr_candidate_images(candidate_imgs)
        if ocr_text:
            post_text = f"{post_text}\n{ocr_text}".strip()
            post_body_only = f"{post_body_only}\n{ocr_text}".strip()
        for em in img_emails:
            if em not in emails:
                emails.append(em)
        for em in extract_emails(post_body_only):
            if em not in emails:
                emails.append(em)

    return post_body_only if emails else post_text, emails, block_reason

def fetch_web_post(url: str) -> tuple[str, list[str]]:
    """Backward-compatible wrapper returning (post_text, emails)."""
    post_text, emails, _ = _fetch_web_post_detailed(url)
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

def process_and_apply(input_source: str | list[str], is_image_path: bool = False, extra_text: str = "") -> dict:
    """
    Universal Entrypoint: processes URL, raw text, single flyer image, or an ordered list of
    multi-part screenshot paths (top headline + bottom email) and dispatches one tailored cold email.
    """
    post_text = ""
    emails = []
    post_url = ""
    block_reason = ""

    if is_image_path:
        paths = input_source if isinstance(input_source, list) else [input_source]
        ocr_chunks = []
        if extra_text:
            ocr_chunks.append(extra_text)
        for idx, img_path in enumerate(paths):
            print(f"[Engine] Processing image #{idx + 1}/{len(paths)}: {img_path}")
            ocr_txt, img_emails = extract_from_image(img_path)
            if ocr_txt:
                ocr_chunks.append(ocr_txt)
            for em in img_emails:
                if em not in emails:
                    emails.append(em)
        post_text = "\n\n".join(ocr_chunks).strip()
    else:
        raw_input = (input_source or "").strip()
        url_match = re.search(r'https?://[^\s]+', raw_input)
        if url_match:
            post_url = url_match.group(0)
            post_text, emails, block_reason = _fetch_web_post_detailed(post_url)
            if raw_input != post_url:
                post_text = f"{raw_input}\n{post_text}".strip()
        else:
            post_text = raw_input
            emails = extract_emails(post_text)

    for e in extract_emails(post_text):
        if e not in emails:
            emails.append(e)

    if not emails:
        if block_reason == "private_post":
            return {
                "success": False,
                "is_private": True,
                "post_url": post_url,
                "error": (
                    "🔒 <b>This post is private — please share screenshot!</b>\n\n"
                    "Bot yeh post direct link se nahi dekh paa raha (Private / Login locked hai).\n"
                    "👉 Bas iska <b>Screenshot (SS)</b> ya <b>Text copy</b> bhej dein — main turant apply kar dunga!"
                )
            }
        return {
            "success": False,
            "is_private": False,
            "post_url": post_url,
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
            "is_private": False,
            "post_url": post_url,
            "error": f"Email sending failed: {msg}"
        }
