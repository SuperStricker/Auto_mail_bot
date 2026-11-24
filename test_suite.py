"""
Comprehensive Regression Test Suite for Auto_mail_bot
Covers universal email extraction, OCR healing, metadata parsing, CV selection, and payload routing.
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ocr_engine import extract_emails
from apply_engine import (
    parse_post_intelligence, extract_company_from_domain, sanitize_job_role,
    _is_private_or_blocked_post
)
from email_sender import select_cv_for_location, create_email_body
from bot_core import _extract_image_file_id, handle_telegram_update, _format_failure_reply
from on_demand_worker import parse_cli_or_env_payload

class TestEmailExtraction(unittest.TestCase):
    def test_dotted_usernames_matching_tld_substrings_not_corrupted(self):
        self.assertEqual(extract_emails("Send your resume to agarwal.saumya@thinksys.com"), ["agarwal.saumya@thinksys.com"])
        self.assertEqual(extract_emails("Mail: priya.indira@acme-it.com#hiring"), ["priya.indira@acme-it.com"])
        self.assertEqual(extract_emails("Email: john.cooper@acme.co.uk"), ["john.cooper@acme.co.uk"])
        self.assertEqual(extract_emails("Contact: raj.aishwarya@firm.in"), ["raj.aishwarya@firm.in"])

    def test_universal_corporate_and_country_tlds(self):
        samples = [
            ("Apply at hr@startup.cloud", ["hr@startup.cloud"]),
            ("Drop CV: jobs@company.dev", ["jobs@company.dev"]),
            ("Contact talent@qatarfirm.qa", ["talent@qatarfirm.qa"]),
            ("HR: bewerbung@firma-it.de", ["bewerbung@firma-it.de"]),
            ("Send to hr@acme.solutions", ["hr@acme.solutions"]),
            ("Reach: jobs@vserv.com.sa or hr@tech.co.uk", ["jobs@vserv.com.sa", "hr@tech.co.uk"]),
        ]
        for text, expected in samples:
            self.assertEqual(extract_emails(text), expected)

    def test_ocr_healing_and_glued_text(self):
        self.assertEqual(extract_emails("Contact: hr @ thinksys . com"), ["hr@thinksys.com"])
        self.assertEqual(extract_emails("careers [at] nair-systems [dot] co [dot] qa"), ["careers@nair-systems.co.qa"])
        self.assertEqual(extract_emails("Send to agarwal.saumya@thinksys,com"), ["agarwal.saumya@thinksys.com"])
        self.assertEqual(extract_emails("Drop to hr©thinksys.com"), ["hr@thinksys.com"])
        self.assertEqual(extract_emails("careers@al-kabeer.comcareers@al-kabeer.com"), ["careers@al-kabeer.com"])
        self.assertEqual(extract_emails("Share CV: tech.hr@org.comNextLine"), ["tech.hr@org.com"])
        self.assertEqual(extract_emails("mailto:talent@thinksys.com"), ["talent@thinksys.com"])
        self.assertEqual(extract_emails("-hr@thinksys.com"), ["hr@thinksys.com"])

    def test_junk_and_asset_exclusion(self):
        self.assertEqual(extract_emails("logo@2x.png icon@3x.jpg hr@example.com no@licdn.com"), [])

class TestIntelligenceAndRouting(unittest.TestCase):
    def test_thinksys_flyer_metadata(self):
        sample = """
        We're Hiring! L3 - IT Infrastructure & Support Engineer
        Experience: 6+ Years
        Location: Sector 62, Noida (24x7 Rotational Shift)
        Why Join ThinkSys?
        Send your resume to agarwal.saumya@thinksys.com
        """
        meta = parse_post_intelligence(sample)
        self.assertIn("IT Infrastructure", meta["job_role"])
        self.assertIn("Noida", meta["location"])
        self.assertEqual(extract_company_from_domain("agarwal.saumya@thinksys.com"), "Thinksys")
        _, cv_name, is_intl = select_cv_for_location(meta["location"], sample)
        self.assertEqual(cv_name, "Shuaib Ali - CV.pdf")
        self.assertFalse(is_intl)

    def test_international_cv_routing(self):
        _, cv_name, is_intl = select_cv_for_location("Doha, Qatar", "Systems Administrator Qatar")
        self.assertEqual(cv_name, "Shuaib_Ali.pdf")
        self.assertTrue(is_intl)

    def test_telegram_photo_and_document_payloads(self):
        # Raw photo
        self.assertEqual(_extract_image_file_id({"photo": [{"file_id": "low"}, {"file_id": "high"}]}, {}), "high")
        # Raw image document
        self.assertEqual(_extract_image_file_id({"document": {"file_id": "doc1", "mime_type": "image/png"}}, {}), "doc1")
        # Non-image document ignored
        self.assertEqual(_extract_image_file_id({"document": {"file_id": "pdf1", "mime_type": "application/pdf", "file_name": "jd.pdf"}}, {}), "")
        # Slimmed Cloudflare payload
        self.assertEqual(_extract_image_file_id({}, {"photo_file_id": "cf_photo"}), "cf_photo")
        self.assertEqual(_extract_image_file_id({}, {"doc_file_id": "cf_doc", "doc_mime": "image/jpeg"}), "cf_doc")

    def test_workflow_dispatch_null_payload_handling(self):
        # When workflow_dispatch runs, client_payload JSON is "null" while JOB_TEXT_OR_URL holds the input
        self.assertEqual(parse_cli_or_env_payload("null", "https://lnkd.in/p/gEDGHxSk"), {"text": "https://lnkd.in/p/gEDGHxSk"})
        self.assertEqual(parse_cli_or_env_payload("{}", "https://lnkd.in/p/gEDGHxSk"), {"text": "https://lnkd.in/p/gEDGHxSk"})
        self.assertIsNone(parse_cli_or_env_payload("null", ""))
        # Should never crash on None update
        handle_telegram_update(None)

    def test_private_or_blocked_post_detection(self):
        self.assertTrue(_is_private_or_blocked_post("https://www.linkedin.com/signup/cold-join?session_redirect=x", "Join LinkedIn now"))
        self.assertTrue(_is_private_or_blocked_post("https://example.com/post", "", http_status=403))
        self.assertFalse(_is_private_or_blocked_post("https://www.linkedin.com/posts/ok-share-123", "We are hiring Support Engineer in Noida"))
        msg = _format_failure_reply({"is_private": True, "post_url": "https://lnkd.in/p/gwrNkQKX", "error": "Private!"})
        self.assertIn("https://lnkd.in/p/gwrNkQKX", msg)

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
