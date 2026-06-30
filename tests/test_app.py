import io
import unittest
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient

import app.router as router_module
from app.config import settings
from app.formatter import format_output
from app.summarize import Summarizer
from main import app


def make_docx(text: str) -> bytes:
    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


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
        self.initial_uploads = set(settings.UPLOAD_DIR.iterdir())

    def tearDown(self) -> None:
        router_module.summarizer = None
        self.assertEqual(set(settings.UPLOAD_DIR.iterdir()), self.initial_uploads)

    def test_root_page_is_available(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("MKT Automation", response.text)

    def test_unsupported_extension_returns_415(self) -> None:
        response = self.client.post(
            "/api/upload",
            files={"file": ("job.txt", b"not supported", "text/plain")},
            data={"req_format": "short"},
        )
        self.assertEqual(response.status_code, 415)
        self.assertIn("Unsupported file type", response.json()["detail"])

    def test_invalid_requirement_format_returns_422(self) -> None:
        response = self.client.post(
            "/api/upload",
            files={"file": ("job.docx", make_docx("A valid job description with enough text."))},
            data={"req_format": "invalid"},
        )
        self.assertEqual(response.status_code, 422)

    def test_invalid_why_join_format_returns_422(self) -> None:
        response = self.client.post(
            "/api/upload",
            files={"file": ("job.docx", make_docx("A valid job description with enough text."))},
            data={"req_format": "short", "why_join_format": "tag"},
        )
        self.assertEqual(response.status_code, 422)

    def test_short_document_returns_json_422(self) -> None:
        response = self.client.post(
            "/api/upload",
            files={"file": ("job.docx", make_docx("tiny"))},
            data={"req_format": "short"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertIn("enough text", response.json()["detail"])

    def test_large_upload_returns_413(self) -> None:
        with patch.object(settings, "MAX_UPLOAD_SIZE", 8):
            response = self.client.post(
                "/api/upload",
                files={"file": ("job.docx", make_docx("A sufficiently long job description."))},
                data={"req_format": "short"},
            )
        self.assertEqual(response.status_code, 413)

    def test_valid_document_returns_formatted_result(self) -> None:
        response = self.client.post(
            "/api/upload",
            files={
                "file": (
                    "job.docx",
                    make_docx("Senior Python developer position with FastAPI experience required."),
                )
            },
            data={"req_format": "short"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["job_title"], "Python Developer")
        self.assertIn("PYTHON DEVELOPER", body["formatted_text"])

    def test_tag_and_ultra_short_options_reach_api(self) -> None:
        response = self.client.post(
            "/api/upload",
            files={
                "file": (
                    "job.docx",
                    make_docx("Senior Python developer position with FastAPI experience required."),
                )
            },
            data={"req_format": "tag", "why_join_format": "ultra_short"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("[Python] [FastAPI]", response.json()["formatted_text"])


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

        self.assertEqual(result.short_description, "Python Developer role requiring Python, FastAPI.")
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

        result = summarizer._normalize_answers(answers, "tag", "ultra_short")

        self.assertLessEqual(len(result.requirements[0].split()), 3)
        self.assertLessEqual(len(result.why_join[0].split()), 8)

    def test_tag_output_uses_tag_notation(self) -> None:
        text = format_output(
            {
                "job_title": "Developer",
                "requirements": ["8+ YOE", "Golang Expert", "AWS"],
            },
            requirement_format="tag",
        )

        self.assertIn("[8+ YOE] [Golang Expert] [AWS]", text)

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

        self.assertEqual(result.requirements[0], "8+ YOE Python")
        self.assertIn("deep Golang expertise", result.requirements)
        self.assertIn("competitive salary", result.why_join)
        self.assertTrue(all(len(item.split()) <= 3 for item in result.requirements))
        self.assertTrue(all(len(item.split()) <= 8 for item in result.why_join))

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
