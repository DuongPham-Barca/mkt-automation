import json
import re

from google import genai
from pydantic import BaseModel, Field

from app.config import settings
from app.models import SummarizeResponse


SYSTEM_PROMPT = (
    "You extract facts from job descriptions. "
    "Never invent missing information."
)

FIELD_DEFINITIONS = {
    "job_title": "job title (exact as written)",
    "subtitle": "short subtitle (1 phrase, under 10 words)",
    "employment_type": "employment type: Full-time, Part-time, or Contract",
    "contract_type": "contract type: In-Office, Remote or Hybrid",
    "location": "job location",
    "salary": "salary (exact amount if stated, otherwise N/A)",
    "bounty": "referral / hiring bounty (exact amount if stated, otherwise N/A)",
    "short_description": (
        "exactly one complete sentence (25-35 words) summarizing the primary role, "
        "main responsibilities, core technologies/skills, and the role's main impact. "
        "Avoid generic, repeated, or secondary details."
    ),
    "requirements": (
        "4-5 most important job requirement keywords or short phrases, separated by "
        "semicolons. Prioritize required skills, technologies, years of experience, "
        "domain knowledge, language, and education. Preserve exact technology names "
        "and numeric experience from the job description; never invent requirements."
    ),
    "why_join": (
        "benefits explicitly listed in the Benefits, Perks, What We Offer, or Why Join "
        "section, separated by semicolons; otherwise N/A"
    ),
}


class GeminiExtraction(BaseModel):
    job_title: str = Field(description=FIELD_DEFINITIONS["job_title"])
    subtitle: str = Field(description=FIELD_DEFINITIONS["subtitle"])
    employment_type: str = Field(description=FIELD_DEFINITIONS["employment_type"])
    contract_type: str = Field(description=FIELD_DEFINITIONS["contract_type"])
    location: str = Field(description=FIELD_DEFINITIONS["location"])
    salary: str = Field(description=FIELD_DEFINITIONS["salary"])
    bounty: str = Field(description=FIELD_DEFINITIONS["bounty"])
    short_description: str = Field(description=FIELD_DEFINITIONS["short_description"])
    requirements: str = Field(description=FIELD_DEFINITIONS["requirements"])
    why_join: str = Field(description=FIELD_DEFINITIONS["why_join"])


class Summarizer:
    def __init__(self):
        self.client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if self.client is None:
            if not settings.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY is not configured.")
            self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self.client

    def _truncate_context(self, text: str) -> str:
        max_chars = settings.MAX_INPUT_LENGTH * 4
        return text[:max_chars] if len(text) > max_chars else text

    def build_prompt(self, text: str) -> str:
        context = self._truncate_context(text)
        fields_json = json.dumps(FIELD_DEFINITIONS, ensure_ascii=False, indent=2)
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"Extract the following fields from the job description below. "
            f"Return ONLY a valid JSON object with these keys. "
            f"If information is missing, use N/A as the value.\n\n"
            f"Fields to extract:\n{fields_json}\n\n"
            f"Job description:\n{context}"
        )

    def _generate_answers(self, prompt: str) -> dict[str, str]:
        client = self._get_client()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": GeminiExtraction,
                "temperature": 0.1,
            },
        )
        raw = (response.text or "").strip()
        if not raw:
            raise RuntimeError("Gemini returned an empty response.")
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return GeminiExtraction.model_validate_json(raw).model_dump()

    @staticmethod
    def _clean_scalar(value: str) -> str:
        cleaned = value.strip().strip(" \t\r\n\"'()[]{}")
        if cleaned.lower().strip(". -") in {"", "n/a", "na", "none", "unknown", "not specified", "or"}:
            return ""
        return cleaned

    @staticmethod
    def _truncate_words(value: str, limit: int) -> str:
        words = value.split()
        words = words[:limit]

        # A hard word limit can leave a grammatically incomplete fragment such
        # as "Salary review every" or "Opportunity to". Back up over words
        # that require a complement so text-format requirements and benefits
        # still read as meaningful phrases.
        dangling_words = {
            "a", "an", "the", "and", "or", "but", "to", "of", "for",
            "with", "without", "in", "on", "at", "from", "by", "as",
            "into", "through", "across", "about", "between", "among",
            "every", "each", "any", "all", "both", "either", "neither",
            "this", "that", "these", "those", "your", "our", "their",
        }
        while words and words[-1].lower().strip(" ,;:./()[]{}-\"") in dangling_words:
            words.pop()

        return " ".join(words).strip(" ,;.-")

    @staticmethod
    def _compact_description(value: str, word_limit: int = 35) -> str:
        text = " ".join(value.split()).strip(" \t\r\n\"'")
        if not text:
            return ""

        # Keep one compound sentence even if the model returned several.
        text = re.sub(r"[.!?]+(?=\s+\S)", ";", text)

        if len(text.split()) > word_limit:
            sentence_candidates = [
                match.end()
                for match in re.finditer(r"[.!?](?=\s|$)", text)
                if 12 <= len(text[:match.end()].split()) <= word_limit
            ]
            if sentence_candidates:
                text = text[:sentence_candidates[-1]]
            else:
                clause_candidates = [
                    match.end()
                    for match in re.finditer(r"[,;](?=\s|$)", text)
                    if 15 <= len(text[:match.end()].split()) <= word_limit
                ]
                if clause_candidates:
                    text = text[:clause_candidates[-1]]
                else:
                    text = " ".join(text.split()[:word_limit])

        dangling_words = {
            "a", "an", "and", "as", "at", "by", "for", "from", "in", "of",
            "on", "or", "such", "the", "to", "with",
        }
        words = text.rstrip(" ,;:.!?").split()
        while words and words[-1].lower() in dangling_words:
            words.pop()
        if not words:
            return ""
        return " ".join(words).rstrip(" ,;:") + "."

    @staticmethod
    def _extract_labeled_section(
        text: str,
        labels: str,
        stop_labels: str,
    ) -> str:
        match = re.search(
            rf"(?:^|[\r\n]|\.\s+)(?:{labels})\s*(?:[:?\-]\s*)?",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return ""

        section = text[match.end():]
        stop = re.search(
            rf"(?:^|[\r\n]|\.\s+)(?:{stop_labels})\s*(?:[:?\-]\s*)?",
            section,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if stop:
            section = section[:stop.start()]
        return section.strip(" \t\r\n.-")

    @staticmethod
    def _extract_heading_section(text: str, labels: str, *_ignored: str) -> str:
        heading = re.search(
            rf"(?:^|[\r\n])\s*(?:\[\[HEADING\]\]\s*)?(?:{labels})"
            rf"\s*(?:[:?\-]\s*)?(?:[\r\n]|$)",
            text,
            flags=re.IGNORECASE,
        )
        if not heading:
            return ""

        section = text[heading.end():]
        marked_heading = re.search(
            r"(?:^|[\r\n])\s*\[\[HEADING\]\]\s*[^\r\n]+(?:[\r\n]|$)",
            section,
            flags=re.IGNORECASE,
        )
        if marked_heading:
            return section[:marked_heading.start()].strip(" \t\r\n.-")

        next_heading = re.search(
            r"(?:^|[\r\n])\s*(?:\[\[HEADING\]\]\s*)?"
            r"(?:requirements?|qualifications?|minimum\s+qualifications?|"
            r"note\s+for\s+recruiter|benefits?|why\s+join(?:\s+us)?|"
            r"interview\s+process|hiring\s+process|recruitment\s+process|"
            r"how\s+to\s+apply|company\s+information|"
            r"job\s+description|about\s+(?:the\s+)?(?:job|role))"
            r"\s*(?:[:?\-]\s*)?(?:[\r\n]|$)",
            section,
            flags=re.IGNORECASE,
        )
        if next_heading:
            section = section[:next_heading.start()]
        else:
            flattened_heading = re.search(
                r"\s+(?:Requirements?|Qualifications?|Minimum Qualifications?|"
                r"Note for Recruiter|Benefits?|Why Join(?: Us)?|"
                r"Interview Process|Hiring Process|Recruitment Process|"
                r"How to Apply|Company Information)\s*(?:[:?\-]\s*)?",
                section,
            )
            if flattened_heading:
                section = section[:flattened_heading.start()]
        return section.strip(" \t\r\n.-")

    @staticmethod
    def _compact_requirement_tag(value: str) -> str:
        value = re.sub(r"^(?:and|or)\s+", "", value, flags=re.IGNORECASE)

        semantic_rules = (
            (r"quality\s+of\s+(?:agile\s+)?ceremon(?:y|ies)", "Agile Ceremony Quality"),
            (r"constructive(?:\s+and\s+timely)?\s+feedback", "Constructive Feedback"),
            (r"conflict\s+resolution", "Conflict Resolution"),
            (r"negotiat\w*\s+(?:priorities|priority|timelines)", "Priority Negotiation"),
            (r"english\s+communication", "English Communication"),
            (r"definition\s+of\s+done", "Definition of Done"),
            (r"(?:careful|detail[- ]oriented)", "Detail-Oriented"),
            (r"(?:high\s+sense\s+of\s+responsibility|passionate\s+and)", "High Responsibility"),
            (r"(?:daily\s+scrum|scrums)\b", "Daily Scrum"),
        )
        for pattern, tag in semantic_rules:
            if re.search(pattern, value, flags=re.IGNORECASE):
                return tag

        degree = re.match(
            r"^(?:a\s+)?bachelor'?s?\s+degree(?:\s+in\s+(.+))?$",
            value,
            flags=re.IGNORECASE,
        )
        if degree:
            field = (degree.group(1) or "").strip()
            return f"{field} Degree" if field else "Bachelor's Degree"

        match = re.search(
            r"(?:more than|over|at least)?\s*(\d+)\+?\s*(?:years?|yrs?|YOE)",
            value,
            flags=re.IGNORECASE,
        )
        if match:
            remainder = value[match.end():]
            stop_words = {
                "of", "professional", "development", "experience", "working",
                "with", "in", "the", "a", "an", "strong", "knowledge",
                "playing", "as", "role",
            }
            skill = next(
                (
                    word.strip(" ,;:.-()[]")
                    for word in remainder.split()
                    if word.strip(" ,;:.-()[]").lower() not in stop_words
                ),
                "",
            )
            return f"{match.group(1)}+ YOE" + (f" {skill}" if skill else "")

        prefix = re.match(
            r"^(?:strong\s+knowledge\s+of|knowledge\s+of|experience\s+with|"
            r"experienced\s+with|proficient\s+in|proficiency\s+in|"
            r"familiarity\s+with|familiar\s+with|skills?\s+in)\s+(.+)$",
            value,
            flags=re.IGNORECASE,
        )
        if prefix:
            return prefix.group(1)

        action_prefix = re.match(
            r"^(?:ability\s+to|able\s+to|accountable\s+for|responsible\s+for|"
            r"responsibility\s+for|capable\s+of)\s+(?:the\s+)?(.+)$",
            value,
            flags=re.IGNORECASE,
        )
        if action_prefix:
            return action_prefix.group(1)

        if re.match(r"^good\s+english\s+communication", value, flags=re.IGNORECASE):
            return "English Communication"
        return value

    @staticmethod
    def _finalize_requirement_tag(value: str, word_limit: int = 3) -> str:
        value = re.sub(
            r"^(?:strong|excellent|solid|good|deep)\s+",
            "",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            r"\s+(?:skills?|experience|knowledge)$",
            "",
            value,
            flags=re.IGNORECASE,
        )
        # Preserve both alternatives without spending a word on a connector.
        value = re.sub(r"\s+or\s+", "/", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+and\s+", " & ", value, flags=re.IGNORECASE)

        words = value.split()[:word_limit]
        dangling = {"and", "or", "&", "of", "with", "for", "to", "in", "on"}
        while words and words[0].lower().strip(".,;:/") in {"and", "or", "&"}:
            words.pop(0)
        while words and words[-1].lower().strip(".,;:/") in dangling:
            words.pop()

        tag = " ".join(words).strip(" ,;:./&-")
        tag = re.sub(
            r"(?:(?<=&\s)|(?<=/))([a-z])",
            lambda match: match.group(1).upper(),
            tag,
        )
        return tag[:1].upper() + tag[1:] if tag else ""

    @staticmethod
    def _extract_bounty(text: str) -> str:
        money_match = re.search(
            r"(?:referral\s+bonus|referral\s+bounty|hiring\s+bounty|bounty)"
            r"\s*(?::|\-)?\s*"
            r"((?:[$₫đ€£]|VND|USD)\s*[\d][\d.,\s]*"
            r"|[\d][\d.,\s]*(?:VND|USD|[$₫đ€£]))",
            text,
            flags=re.IGNORECASE,
        )
        if money_match:
            return re.sub(r"\s+", " ", money_match.group(1)).strip(" \t.,;-")

        labeled_match = re.search(
            r"(?:referral\s+bonus|referral\s+bounty|hiring\s+bounty|bounty)"
            r"\s*[:\-]\s*([^\r\n|]{1,80})",
            text,
            flags=re.IGNORECASE,
        )
        if not labeled_match:
            return ""
        return labeled_match.group(1).strip(" \t.,;-")

    def _clean_list(
        self,
        value: str,
        word_limit: int,
        tag_mode: bool = False,
        max_items: int = 5,
        split_commas: bool = False,
    ) -> list[str]:
        separators = r"[;\n\u2022]|\s+-\s+"
        if split_commas:
            separators += r"|,(?=\s*[A-Za-z])"
        parts = re.split(separators, value)
        cleaned: list[str] = []
        for part in parts:
            part = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", part)
            item = re.sub(r"^(requirements?|why join|reasons?)\s*:\s*", "", part, flags=re.IGNORECASE)
            item = self._clean_scalar(item)
            if tag_mode:
                item = self._compact_requirement_tag(item)
                item = self._finalize_requirement_tag(item, word_limit)
            else:
                item = self._truncate_words(item, word_limit)
            if item and item.lower() not in {existing.lower() for existing in cleaned}:
                cleaned.append(item)
                if len(cleaned) == max_items:
                    break
        return cleaned

    def _normalize_answers(
        self,
        answers: dict[str, str],
        req_format: str,
        why_join_format: str,
        source_text: str = "",
    ) -> SummarizeResponse:
        data = {key: self._clean_scalar(value) for key, value in answers.items()}

        source_responsibilities = self._extract_heading_section(
            source_text,
            r"(?:key\s+)?responsibilities?|what\s+you(?:'|'')?ll\s+do|your\s+role",
            r"requirements?|qualifications?|benefits?|why\s+join(?:\s+us)?|"
            r"job\s+description|about\s+(?:the\s+)?(?:job|role)",
        )
        requirement_labels = r"requirements?|qualifications?|yêu cầu(?: công việc)?"
        source_requirements = self._extract_heading_section(
            source_text,
            requirement_labels,
        ) or self._extract_labeled_section(
            source_text,
            requirement_labels,
            r"benefits?|why\s+join(?:\s+us)?|quyền lợi|phúc lợi|responsibilities?|mô tả công việc",
        )
        benefit_labels = (
            r"benefits?|perks?|what\s+we\s+offer|why\s+join(?:\s+us)?|"
            r"quyền lợi|phúc lợi"
        )
        source_why_join = self._extract_heading_section(
            source_text,
            benefit_labels,
        ) or self._extract_labeled_section(
            source_text,
            benefit_labels,
            r"requirements?|qualifications?|yêu cầu(?: công việc)?|responsibilities?|"
            r"mô tả công việc|interview\s+process|hiring\s+process|"
            r"recruitment\s+process|how\s+to\s+apply|company\s+information",
        )
        # Some job sites render the next section as plain bold text instead of
        # a heading. Enforce the Benefits boundary after extraction as well.
        non_benefit_section = re.search(
            r"(?:\[\[HEADING\]\]\s*)?\b(?:interview\s+process|hiring\s+process|"
            r"recruitment\s+process|application\s+process|how\s+to\s+apply|"
            r"company\s+information)\s*(?:[:?\-]|[\r\n]|$)",
            source_why_join,
            flags=re.IGNORECASE,
        )
        if non_benefit_section:
            source_why_join = source_why_join[:non_benefit_section.start()].rstrip()
        # Gemini selects the most relevant requirement keywords. Fall back to
        # the URL's Requirements section, then Responsibilities when necessary.
        data["requirements"] = (
            data.get("requirements") or source_requirements or source_responsibilities
        )
        # Why Join must come only from the URL's explicit benefits section.
        data["why_join"] = source_why_join
        source_bounty = self._extract_bounty(source_text)
        if source_bounty:
            data["bounty"] = source_bounty

        employment = data["employment_type"].lower()
        if "full" in employment:
            data["employment_type"] = "Full-time"
        elif "part" in employment:
            data["employment_type"] = "Part-time"
        elif "contract" in employment or "freelance" in employment:
            data["employment_type"] = "Contract"
        else:
            data["employment_type"] = ""

        if data["subtitle"].lower() == data["job_title"].lower():
            data["subtitle"] = ""
        if data["bounty"].lower() == data["salary"].lower():
            data["bounty"] = ""

        requirement_limits = {"short": 15, "ultra_short": 8, "tag": 3}
        requirements = self._clean_list(
            data.pop("requirements"),
            requirement_limits[req_format],
            tag_mode=req_format == "tag",
            max_items=5,
            split_commas=True,
        )
        why_join_limits = {"short": 30, "ultra_short": 8}
        why_join = self._clean_list(
            data.pop("why_join"),
            why_join_limits[why_join_format],
            max_items=5,
        )

        description = self._compact_description(data["short_description"])
        if not description and data["job_title"]:
            description = f"{data['job_title']} role"
            if data["location"]:
                description += f" in {data['location']}"
            if requirements:
                description += f" requiring {', '.join(requirements[:3])}"
            description += "."
        data["short_description"] = description

        return SummarizeResponse(
            **data,
            requirements=requirements,
            why_join=why_join,
            raw_response=json.dumps(answers, ensure_ascii=False),
        )

    def summarize(
        self,
        text: str,
        req_format: str = "short",
        why_join_format: str = "short",
    ) -> dict:
        if req_format not in settings.REQUIREMENT_FORMATS:
            raise ValueError(f"Unsupported requirements format: {req_format}")
        if why_join_format not in settings.WHY_JOIN_FORMATS:
            raise ValueError(f"Unsupported Why Join format: {why_join_format}")

        prompt = self.build_prompt(text)
        answers = self._generate_answers(prompt)
        return self._normalize_answers(
            answers,
            req_format,
            why_join_format,
            source_text=text,
        ).model_dump()
