import re
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.router as router_module
from app.formatter import format_output
from app.summarize import Summarizer
from app.url_extractor import _extract_visible_text, _validate_public_url
from index import app as vercel_app
from main import app


VALID_TEXT = "Senior Python developer position with FastAPI experience required."


class FakeSummarizer:
    def summarize(self, text: str, req_format: str, why_join_format: str) -> dict:
        return {
            "job_title": "Python Developer",
            "subtitle": "Backend engineering",
            "employment_type": "Full-time",
            "contract_type": "Permanent",
            "location": "Ho Chi Minh City",
            "salary": "40 million VND",
            "bounty": "",
            "short_description": "Build reliable Python services.",
            "requirements": ["Python", "FastAPI"],
            "why_join": ["Flexible hours"],
            "raw_response": "{}",
        }


class ApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)
        router_module.summarizer = FakeSummarizer()

    def tearDown(self) -> None:
        router_module.summarizer = None

    def test_root_page_is_available(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("MKT Automation", response.text)

    def test_frontend_script_is_available_locally(self) -> None:
        response = self.client.get("/app.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("async function summarize", response.text)

    def test_vercel_entrypoint_exports_the_fastapi_app(self) -> None:
        self.assertIs(vercel_app, app)

    def test_healthcheck_does_not_load_model(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_missing_url_returns_422(self) -> None:
        response = self.client.post(
            "/api/summarize-url",
            data={"req_format": "short"},
        )
        self.assertEqual(response.status_code, 422)

    def test_invalid_requirement_format_returns_422(self) -> None:
        response = self.client.post(
            "/api/summarize-url",
            data={"url": "https://example.com/job", "req_format": "invalid"},
        )
        self.assertEqual(response.status_code, 422)

    def test_invalid_why_join_format_returns_422(self) -> None:
        response = self.client.post(
            "/api/summarize-url",
            data={"url": "https://example.com/job", "req_format": "short", "why_join_format": "tag"},
        )
        self.assertEqual(response.status_code, 422)

    @patch("app.router.fetch_url_text", side_effect=ValueError("Could not extract enough text from the URL."))
    def test_short_page_returns_json_422(self, _fetch) -> None:
        response = self.client.post("/api/summarize-url", data={"url": "https://example.com/job"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertIn("enough text", response.json()["detail"])

    @patch("app.router.fetch_url_text", return_value=VALID_TEXT)
    def test_valid_url_returns_formatted_result(self, _fetch) -> None:
        response = self.client.post(
            "/api/summarize-url",
            data={"url": "https://example.com/job", "req_format": "short"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["job_title"], "Python Developer")
        self.assertIn("PYTHON DEVELOPER", body["formatted_text"])

    @patch("app.router.fetch_url_text", return_value=VALID_TEXT)
    def test_tag_and_ultra_short_options_reach_api(self, _fetch) -> None:
        response = self.client.post(
            "/api/summarize-url",
            data={
                "url": "https://example.com/job",
                "req_format": "tag",
                "why_join_format": "ultra_short",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("[Python] [FastAPI]", response.json()["formatted_text"])


class UrlExtractorTests(unittest.TestCase):
    def test_extracts_visible_html_and_ignores_scripts(self) -> None:
        html = b"<html><script>ignore me</script><h1>Python Developer</h1><p>Build APIs with FastAPI.</p></html>"
        text = _extract_visible_text(html, "text/html", "utf-8")
        self.assertIn("Python Developer", text)
        self.assertIn("Build APIs with FastAPI.", text)
        self.assertNotIn("ignore me", text)

    def test_private_ip_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "private network"):
            _validate_public_url("http://127.0.0.1/job")


class SummarizerNormalizationTests(unittest.TestCase):
    def test_empty_generated_fields_are_valid(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        answers = {
            "job_title": "Python Developer",
            "subtitle": "N/A",
            "employment_type": "Full-time",
            "contract_type": "N/A",
            "location": "N/A",
            "salary": "N/A",
            "bounty": "N/A",
            "short_description": "",
            "requirements": "Python; FastAPI",
            "why_join": "N/A",
        }

        result = summarizer._normalize_answers(answers, "short", "short")

        self.assertEqual(
            result.short_description,
            "Python Developer role requiring Python, FastAPI.",
        )
        self.assertEqual(result.requirements, ["Python", "FastAPI"])
        self.assertEqual(result.why_join, [])

    def test_word_limits_follow_both_prd_options(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        answers = {
            "job_title": "Developer",
            "subtitle": "",
            "employment_type": "Full-time",
            "contract_type": "Permanent",
            "location": "Remote",
            "salary": "",
            "bounty": "",
            "short_description": "",
            "requirements": "one two three four five six seven eight nine ten",
            "why_join": "one two three four five six seven eight nine ten",
        }

        result = summarizer._normalize_answers(
            answers,
            "tag",
            "ultra_short",
            source_text=(
                "Responsibilities\n"
                "one two three four five six seven eight nine ten\n"
                "Benefits\n"
                "one two three four five six seven eight nine ten"
            ),
        )

        self.assertLessEqual(len(result.requirements[0].split()), 3)
        self.assertLessEqual(len(result.why_join[0].split()), 8)

    def test_text_formats_do_not_end_with_dangling_words(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        answers = {
            "job_title": "Developer",
            "subtitle": "",
            "employment_type": "Full-time",
            "contract_type": "Remote",
            "location": "Remote",
            "salary": "",
            "bounty": "",
            "short_description": "Build software.",
            "requirements": (
                "Experience designing reliable distributed services used by teams every day; "
                "Ability to communicate technical decisions clearly to"
            ),
            "why_join": "N/A",
        }
        source = (
            "Benefits\n"
            "Salary reviews occur twice per year every\n"
            "A dedicated learning budget and mentoring program to support career growth"
        )

        result = summarizer._normalize_answers(
            answers,
            "ultra_short",
            "ultra_short",
            source_text=source,
        )

        self.assertEqual(
            result.requirements,
            [
                "Experience designing reliable distributed services used by teams",
                "Ability to communicate technical decisions clearly",
            ],
        )
        self.assertEqual(
            result.why_join,
            [
                "Salary reviews occur twice per year",
                "A dedicated learning budget and mentoring program",
            ],
        )
        dangling = {"every", "to"}
        self.assertTrue(
            all(item.split()[-1].lower() not in dangling for item in result.requirements)
        )
        self.assertTrue(
            all(item.split()[-1].lower() not in dangling for item in result.why_join)
        )

    def test_requirements_and_why_join_are_limited_to_five_items(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        answers = {
            "job_title": "Developer",
            "subtitle": "",
            "employment_type": "Full-time",
            "contract_type": "Permanent",
            "location": "Remote",
            "salary": "",
            "bounty": "",
            "short_description": "Build software.",
            "requirements": "Python; FastAPI; PostgreSQL; AWS; Docker; Redis; Git",
            "why_join": "N/A",
        }
        source = (
            "Benefits\n"
            "Health insurance\nAnnual bonus\nFlexible hours\nCompany trip\n"
            "Training budget\nFree lunch\nExtra leave"
        )

        result = summarizer._normalize_answers(
            answers,
            "short",
            "short",
            source_text=source,
        )

        self.assertEqual(len(result.requirements), 5)
        self.assertEqual(len(result.why_join), 5)
        self.assertEqual(
            result.requirements,
            ["Python", "FastAPI", "PostgreSQL", "AWS", "Docker"],
        )

    def test_tag_output_uses_tag_notation(self) -> None:
        text = format_output(
            {
                "job_title": "Developer",
                "requirements": ["8+ YOE", "Golang Expert", "AWS"],
            },
            requirement_format="tag",
        )

        self.assertIn("[8+ YOE] [Golang Expert] [AWS]", text)
        self.assertIn("Bounty: N/A", text)

    def test_responsibility_tags_are_semantically_complete(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        values = {
            "Accountable for the quality of agile ceremonies": "Agile Ceremony Quality",
            "Ability to provide constructive and timely feedback": "Constructive Feedback",
            "Conflict resolution within delivery teams": "Conflict Resolution",
            "Ability to negotiate priorities and timelines": "Priority Negotiation",
            "Ensuring the team commits to their definition of done": "Definition of Done",
            "Careful": "Detail-Oriented",
            "Passionate and have high sense of responsibility": "High Responsibility",
            "From 3 years of experience playing Scrum Master": "3+ YOE Scrum",
        }

        for source, expected in values.items():
            with self.subTest(source=source):
                tag = summarizer._compact_requirement_tag(source)
                self.assertEqual(tag, expected)
                self.assertLessEqual(len(tag.split()), 3)

    def test_tags_do_not_end_with_dangling_and_or(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        tags = summarizer._clean_list(
            (
                "4+ years of experience; Business Development or Sales; "
                "Fluent English; Understanding of payment; "
                "Strong negotiation and communication skills"
            ),
            word_limit=3,
            tag_mode=True,
        )

        self.assertEqual(
            tags,
            [
                "4+ YOE",
                "Business Development/Sales",
                "Fluent English",
                "Understanding of payment",
                "Negotiation & Communication",
            ],
        )
        self.assertTrue(
            all(not re.search(r"\b(?:and|or)$", tag, re.IGNORECASE) for tag in tags)
        )

    def test_labeled_bounty_is_extracted_from_source(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        answers = {
            "job_title": "Developer",
            "subtitle": "",
            "employment_type": "Full-time",
            "contract_type": "Permanent",
            "location": "Remote",
            "salary": "",
            "bounty": "N/A",
            "short_description": "",
            "requirements": "Python",
            "why_join": "Flexible hours",
        }

        result = summarizer._normalize_answers(
            answers,
            "short",
            "short",
            source_text="Developer role\nBounty: 20,000,000 VND\nRequirements: Python",
        )

        self.assertEqual(result.bounty, "20,000,000 VND")

    def test_bounty_badge_without_colon_is_extracted(self) -> None:
        self.assertEqual(
            Summarizer._extract_bounty("Bounty ₫ 23,040,000\nPosted 5d ago"),
            "₫ 23,040,000",
        )

    def test_description_ends_at_complete_clause(self) -> None:
        description = (
            "The Technical Architect position involves leading a team responsible for designing, "
            "developing, and maintaining complex software systems using JavaScript and related "
            "technologies, working closely with other teams such as the"
        )

        compact = Summarizer._compact_description(description)

        self.assertEqual(
            compact,
            "The Technical Architect position involves leading a team responsible for designing, "
            "developing, and maintaining complex software systems using JavaScript and related "
            "technologies, working closely with other teams.",
        )
        self.assertLessEqual(len(compact.split()), 35)

    def test_description_is_exactly_one_sentence(self) -> None:
        description = (
            "Lead the design and delivery of scalable JavaScript systems across the platform. "
            "Guide engineers, define technical standards, and collaborate with product teams to "
            "turn business requirements into reliable solutions. Improve architecture, code quality, "
            "and operational performance while mentoring the development team."
        )

        compact = Summarizer._compact_description(description)

        self.assertEqual(compact.count("."), 1)
        self.assertTrue(compact.endswith("."))
        self.assertIn("Lead the design and delivery", compact)
        self.assertIn("Guide engineers", compact)
        self.assertLessEqual(len(compact.split()), 35)

    def test_labeled_sections_override_missing_model_answers(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        answers = {
            "job_title": "Developer",
            "subtitle": "",
            "employment_type": "Full-time",
            "contract_type": "Permanent",
            "location": "Remote",
            "salary": "",
            "bounty": "",
            "short_description": "",
            "requirements": "N/A",
            "why_join": "N/A",
        }
        source = (
            "Requirements: more than 8 years of professional Python development experience, "
            "deep Golang expertise, Amazon Web Services. "
            "Benefits: competitive salary, flexible remote working hours, private health insurance."
        )

        result = summarizer._normalize_answers(
            answers,
            "tag",
            "ultra_short",
            source_text=source,
        )

        self.assertEqual(
            result.requirements,
            ["8+ YOE Python", "Golang expertise", "Amazon Web Services"],
        )
        self.assertTrue(any("competitive salary" in item for item in result.why_join))
        self.assertTrue(all(len(item.split()) <= 3 for item in result.requirements))
        self.assertTrue(all(len(item.split()) <= 8 for item in result.why_join))

    def test_model_generated_why_join_is_ignored_without_benefits_section(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        answers = {
            "job_title": "Platform Engineer",
            "subtitle": "",
            "employment_type": "Full-time",
            "contract_type": "Permanent",
            "location": "Remote",
            "salary": "",
            "bounty": "",
            "short_description": "Build a reliable cloud platform.",
            "requirements": "N/A",
            "why_join": (
                "Build a high-impact cloud platform; "
                "Work with modern Kubernetes infrastructure"
            ),
        }

        result = summarizer._normalize_answers(
            answers,
            "short",
            "short",
            source_text=(
                "Build a reliable cloud platform used across engineering teams. "
                "Design and operate modern Kubernetes infrastructure."
            ),
        )

        self.assertEqual(result.why_join, [])

    def test_benefits_are_extracted_from_html_heading(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        answers = {
            "job_title": "Platform Engineer",
            "subtitle": "",
            "employment_type": "Full-time",
            "contract_type": "Permanent",
            "location": "Remote",
            "salary": "",
            "bounty": "",
            "short_description": "Build a reliable cloud platform.",
            "requirements": "N/A",
            "why_join": "N/A",
        }
        html = (
            b"<h2>Benefits</h2><ul><li>Private health insurance</li>"
            b"<li>Salary review every 6 months if salary is less than 30,000,000 VND</li>"
            b"<li>Opportunity to be trained overseas, develop English communication skill</li>"
            b"</ul><p><strong>Interview process:</strong></p>"
            b"<p>R1: Online with HR</p>"
        )

        result = summarizer._normalize_answers(
            answers,
            "short",
            "short",
            source_text=_extract_visible_text(html, "text/html", "utf-8"),
        )

        self.assertEqual(
            result.why_join,
            [
                "Private health insurance",
                "Salary review every 6 months if salary is less than 30,000,000 VND",
                "Opportunity to be trained overseas, develop English communication skill",
            ],
        )
        self.assertFalse(any(item == "000" for item in result.why_join))
        self.assertFalse(any("Online with HR" in item for item in result.why_join))

    def test_interview_process_is_removed_when_not_an_html_heading(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        answers = {
            "job_title": "Developer",
            "subtitle": "",
            "employment_type": "Full-time",
            "contract_type": "Permanent",
            "location": "Remote",
            "salary": "",
            "bounty": "",
            "short_description": "Build software.",
            "requirements": "N/A",
            "why_join": "N/A",
        }
        source = (
            "Benefits: Private health insurance; Company trip once a year "
            "Interview process: R1: Online with HR; R2: Technical interview"
        )

        result = summarizer._normalize_answers(
            answers,
            "short",
            "short",
            source_text=source,
        )

        self.assertEqual(
            result.why_join,
            ["Private health insurance", "Company trip once a year"],
        )

    def test_requirements_output_uses_requirements_not_responsibilities(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        answers = {
            "job_title": "Technical Architect",
            "subtitle": "",
            "employment_type": "Full-time",
            "contract_type": "Permanent",
            "location": "Remote",
            "salary": "",
            "bounty": "",
            "short_description": "Lead architecture and engineering delivery.",
            "requirements": "N/A",
            "why_join": "N/A",
        }
        source = (
            "Responsibilities\n"
            "- Lead the design of scalable JavaScript systems\n"
            "- Collaborate with product and engineering teams\n"
            "Requirements\n"
            "- Ten years of software engineering experience\n"
            "Benefits\n"
            "- Flexible working hours"
        )

        result = summarizer._normalize_answers(
            answers,
            "short",
            "short",
            source_text=source,
        )

        self.assertEqual(
            result.requirements,
            ["Ten years of software engineering experience"],
        )
        self.assertNotIn(
            "Lead the design of scalable JavaScript systems",
            result.requirements,
        )

    def test_responsibilities_stop_at_html_requirements_heading(self) -> None:
        html = (
            b"<h2>Responsibilities</h2><ul><li>Facilitate agile ceremonies</li>"
            b"<li>Coach the delivery team</li></ul><h2>Requirements</h2>"
            b"<p>From 3 years as Scrum Master</p><h2>Note for recruiter</h2>"
            b"<p>Internal recruiter notes</p>"
        )
        source = _extract_visible_text(html, "text/html", "utf-8")

        section = Summarizer._extract_heading_section(
            source,
            r"(?:key\s+)?responsibilities?",
        )

        self.assertIn("Facilitate agile ceremonies", section)
        self.assertIn("Coach the delivery team", section)
        self.assertNotIn("From 3 years", section)
        self.assertNotIn("Internal recruiter notes", section)

    def test_why_join_us_heading_does_not_leak_into_requirement_tags(self) -> None:
        summarizer = Summarizer.__new__(Summarizer)
        answers = {
            "job_title": "Developer",
            "subtitle": "",
            "employment_type": "Full-time",
            "contract_type": "Permanent",
            "location": "Remote",
            "salary": "",
            "bounty": "",
            "short_description": "",
            "requirements": "N/A",
            "why_join": "N/A",
        }
        source = (
            "Requirements\n"
            "5+ YOE in Python\n"
            "Strong knowledge of Golang\n"
            "Experience with AWS\n"
            "Proficient in SQL\n"
            "Good English communication\n"
            "Why Join Us?\n"
            "Competitive salary and annual leave\n"
            "Private health insurance"
        )

        result = summarizer._normalize_answers(
            answers,
            "tag",
            "short",
            source_text=source,
        )

        self.assertEqual(
            result.requirements,
            ["5+ YOE Python", "Golang", "AWS", "SQL", "English Communication"],
        )
        self.assertEqual(
            result.why_join,
            ["Competitive salary and annual leave", "Private health insurance"],
        )
        self.assertNotIn("Why Join Us?", result.requirements)


if __name__ == "__main__":
    unittest.main()
