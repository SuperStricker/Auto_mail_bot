"""
Email Sender Module
Sends tailored cold application emails with dynamic CV attachment via Gmail SMTP:
  - India: 'Shuaib Ali - CV.pdf'
  - Outside India / International (UAE, GCC, Europe, US, UK, etc.): 'Shuaib_Ali.pdf'
"""

import os
import re
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from config import (
    GMAIL_USER, GMAIL_PASS, CV_INDIA_PATH, CV_GLOBAL_PATH
)

CV_SKILLS_MAP = {
    "networking_osi_dhcp": (
        ["osi", "dhcp", "hdcp", "dns", "tcp/ip", "tcp", "ip", "lan", "wan", "cable", "patching", "crimping", "patch panel", "cat6", "switch", "router", "wifi", "wi-fi", "network", "networking"],
        "Networking & Infrastructure: LAN/WAN troubleshooting, OSI layer model, DNS/DHCP configuration, LAN cable patching/crimping, and Wi-Fi AP/switch support"
    ),
    "active_directory_adds": (
        ["ad", "adds", "ad ds", "active directory", "domain", "user provisioning", "password reset", "ou", "m365", "office 365", "o365", "outlook"],
        "Active Directory (AD DS) & Identity: User provisioning, OU management, password resets, and Microsoft 365 / Outlook mailbox administration"
    ),
    "printers_hardware": (
        ["printer", "printers", "thermal", "zebra", "tsc", "print spooler", "spooler", "barcode", "scanner", "hhd", "pda", "hardware", "cctv", "biometric"],
        "Printers & Hardware Peripherals: Industrial thermal printers (Zebra/TSC), network printer setup, print spooler troubleshooting, and barcode scanners/HHDs"
    ),
    "itam_asset_management": (
        ["asset", "itam", "inventory", "audit", "auditing", "rma", "vendor", "tagging", "serial", "lifecycle", "procurement"],
        "IT Asset Management (ITAM): End-to-end hardware asset lifecycle, serial/barcode tagging, physical inventory audits, and vendor RMA coordination"
    ),
    "itsm_jira_sla": (
        ["jira", "sla", "ticket", "tickets", "ticketing", "itsm", "service desk", "helpdesk", "incident", "servicenow", "remedy", "escalation"],
        "ITSM, Jira & SLA Management: Handling incident/service request lifecycles via Jira / ticketing tools with 99%+ SLA compliance"
    ),
    "desktop_support_l1_l2": (
        ["desktop", "l1", "l2", "end user", "laptop", "imaging", "windows 10", "windows 11", "os", "antivirus", "troubleshooting", "rdp", "anydesk", "technical support", "tech support"],
        "L1/L2 Desktop & Technical Support: Windows 10/11 OS deployment/imaging, desktop/laptop hardware repair, and remote technical support (RDP/AnyDesk)"
    )
}

def select_cv_for_location(location: str = "", post_text: str = "") -> tuple[str, str, bool]:
    """
    Selects the right CV based on job location:
      - India: 'Shuaib Ali - CV.pdf'
      - Outside India: 'Shuaib_Ali.pdf'
    Returns: (cv_path, cv_filename, is_international)
    """
    combined_geo = f"{location} {post_text}".lower()

    intl_patterns = [
        r'\buae\b', r'\bdubai\b', r'\babu\s+dhabi\b', r'\bsharjah\b', r'\bqatar\b', r'\bdoha\b',
        r'\bsaudi(\s+arabia)?\b', r'\bksa\b', r'\briyadh\b', r'\bjeddah\b', r'\bdammam\b', r'\bkhobar\b',
        r'\bkuwait\b', r'\boman\b', r'\bmuscat\b', r'\bbahrain\b', r'\bgcc\b', r'\bmiddle\s+east\b',
        r'\beurope\b', r'\bgermany\b', r'\buk\b', r'\bunited\s+kingdom\b', r'\blondon\b',
        r'\bnetherlands\b', r'\bamsterdam\b', r'\bireland\b', r'\bdublin\b', r'\bcanada\b',
        r'\btoronto\b', r'\bvancouver\b', r'\busa\b', r'\bunited\s+states\b', r'\bsingapore\b',
        r'\baustralia\b', r'\bsydney\b', r'\bmelbourne\b', r'\bmalaysia\b', r'\bpoland\b'
    ]

    india_patterns = [
        r'\bindia\b', r'\bdelhi\b', r'\bncr\b', r'\bnoida\b', r'\bgurgaon\b', r'\bgurugram\b',
        r'\bghaziabad\b', r'\bfaridabad\b', r'\bmumbai\b', r'\bbangalore\b', r'\bbengaluru\b',
        r'\bpune\b', r'\bhyderabad\b', r'\bchennai\b', r'\bkolkata\b', r'\brajasthan\b',
        r'\budaipur\b', r'\bjaipur\b', r'\bahmedabad\b', r'\bchandigarh\b', r'\bindore\b',
        r'\bkerala\b', r'\bgujarat\b', r'\bmaharashtra\b', r'\bkarnataka\b', r'\btamil\s*nadu\b',
        r'\btelangana\b'
    ]

    is_intl = any(re.search(pat, combined_geo) for pat in intl_patterns)
    is_india = any(re.search(pat, combined_geo) for pat in india_patterns)

    if is_intl and not is_india:
        if os.path.exists(CV_GLOBAL_PATH):
            return CV_GLOBAL_PATH, "Shuaib_Ali.pdf", True

    if os.path.exists(CV_INDIA_PATH):
        return CV_INDIA_PATH, "Shuaib Ali - CV.pdf", False
    elif os.path.exists(CV_GLOBAL_PATH):
        return CV_GLOBAL_PATH, "Shuaib_Ali.pdf", True
    else:
        return CV_INDIA_PATH, "Shuaib Ali - CV.pdf", False

def detect_explicit_subject(text: str) -> str:
    """Detects if recruiter specified an exact subject line in their post."""
    if not text:
        return ""
    patterns = [
        r'(?:mention|use|keep|with)?\s*subject\s*(?:line)?\s*(?:as|should be|is)?\s*[:\-–]\s*["\'`]?([^\n\r"\'`]+)["\'`]?',
        r'subject\s*[:\-–]\s*["\'`]?([^\n\r"\'`]+)["\'`]?'
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            sub = m.group(1).strip().rstrip('.,;')
            if 4 <= len(sub) <= 85 and not sub.lower().startswith(('dear', 'hi', 'hello', 'http', 'mailto', 'please', 'we are')):
                return sub
    return ""

def extract_tailored_skills(post_text: str, role: str) -> list[str]:
    """Picks top 3 genuine CV highlights that score highest against the recruiter requirement."""
    text_lower = (post_text or "").lower()
    role_lower = (role or "").lower()

    scored = []
    for key, (keywords, bullet) in CV_SKILLS_MAP.items():
        post_matches = sum(3 for k in keywords if k in text_lower)
        role_matches = sum(1 for k in keywords if k in role_lower)
        total_score = post_matches + role_matches
        scored.append((total_score, key, bullet))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [item[2] for item in scored if item[0] > 0]

    if len(selected) < 3:
        for item in scored:
            if item[2] not in selected:
                selected.append(item[2])
            if len(selected) >= 3:
                break

    return selected[:3]

JUNK_LOCATION_WORDS = {
    "location", "(location)", "unspecified", "unknown", "remote (eligible)", "null", "none", "n/a", "na", "remote"
}

def clean_location(location: str) -> str:
    """Sanitizes location string and strips junk placeholders."""
    if not location:
        return ""
    loc = location.strip()
    loc = re.sub(r'^(?:location|place|📍)\s*[:|-]?\s*', '', loc, flags=re.IGNORECASE).strip()
    if loc.startswith("(") and loc.endswith(")"):
        loc = loc[1:-1].strip()
    loc = loc.strip(":-—, ")
    if loc.lower() in JUNK_LOCATION_WORDS or len(loc) < 2:
        return ""
    return loc

def create_email_body(job_role: str, recipient_email: str, company: str = "Hiring Team", location: str = "", post_text: str = "", cv_filename: str = "Shuaib Ali - CV.pdf") -> tuple[str, str]:
    """Generates a dynamic concise subject line and tailored professional email body."""
    role_clean = (job_role or "Desktop Support Engineer").strip()
    comp_clean = company.strip() if company and company.strip().lower() not in ["hiring team", "recruiter", "unknown", "none", "null", ""] else ""
    loc_clean = clean_location(location)

    explicit_subject = detect_explicit_subject(post_text)
    if explicit_subject:
        subject = explicit_subject
    else:
        if comp_clean and loc_clean:
            subject = f"Application for {role_clean} - {comp_clean} ({loc_clean})"
        elif comp_clean:
            subject = f"Application for {role_clean} - {comp_clean}"
        elif loc_clean:
            subject = f"Application for {role_clean} ({loc_clean})"
        else:
            subject = f"Application for {role_clean}"

    matched_bullets = extract_tailored_skills(post_text, role_clean)
    bullet_text = "\n".join([f"• {b}" for b in matched_bullets])
    at_company = f" at {comp_clean}" if comp_clean else ""

    body = f"""Dear {comp_clean if comp_clean else 'Hiring Manager'},

I hope this email finds you well.

I am writing to express my strong interest in the {role_clean} position{at_company}. With over 6+ years of hands-on enterprise IT experience across Swiggy Limited, Flipkart / Instakart, and Rozana, my technical expertise directly aligns with your requirements:

{bullet_text}

Please find my updated CV attached below.

Warm regards,

Shuaib Ali
Phone: +91 9311534763
LinkedIn: https://www.linkedin.com/in/shuaib-ali-ba0977195
Location: Noida / Delhi NCR, India (Available for Relocation / Remote)
"""
    return subject, body

def send_cold_email(to_email: str, job_role: str, company: str = "Hiring Team", location: str = "", post_text: str = "") -> tuple[bool, str, str, bool]:
    """
    Sends cold email via Gmail SMTP with dynamically selected CV.
    Returns: (success, message, cv_filename, is_international)
    """
    cv_path, cv_filename, is_intl = select_cv_for_location(location, post_text)

    if not os.path.exists(cv_path):
        return False, f"CV file not found at: {cv_path}", cv_filename, is_intl

    subject, body = create_email_body(job_role, to_email, company, location, post_text, cv_filename)

    msg = MIMEMultipart()
    msg['From'] = f"Shuaib Ali <{GMAIL_USER}>"
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with open(cv_path, 'rb') as f:
            part = MIMEApplication(f.read(), Name=cv_filename)
            part['Content-Disposition'] = f'attachment; filename="{cv_filename}"'
            msg.attach(part)
    except Exception as e:
        return False, f"Failed to attach CV: {e}", cv_filename, is_intl

    max_retries = 3
    base_delay = 3

    for attempt in range(max_retries):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
                server.login(GMAIL_USER, GMAIL_PASS)
                server.sendmail(GMAIL_USER, to_email, msg.as_string())
            return True, "Email sent successfully", cv_filename, is_intl
        except smtplib.SMTPAuthenticationError as e:
            return False, f"SMTP Authentication Failed (check App Password): {e}", cv_filename, is_intl
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, TimeoutError, OSError) as e:
            if attempt < max_retries - 1:
                sleep_time = base_delay * (2 ** attempt)
                time.sleep(sleep_time)
                continue
            return False, f"SMTP Connection failed after {max_retries} attempts: {e}", cv_filename, is_intl
        except Exception as e:
            return False, f"SMTP Error: {e}", cv_filename, is_intl

    return False, "SMTP Delivery Failed", cv_filename, is_intl
