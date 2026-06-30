import json
import re

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from app.config import settings
from app.models import SummarizeResponse


FIELD_QUESTIONS = {
    "job_title": "What is the job title?",
    "subtitle": "Write a short subtitle for this job.",
    "employment_type": "What is the employment type? Answer Full-time, Part-time, or Contract.",
    "contract_type": "Is this job permanent, temporary, fixed-term, freelance, or another contract type?",
    "location": "Where is the job located?",
    "salary": "What is the salary?",
    "bounty": "Is a referral or hiring bounty explicitly stated? If not, answer N/A.",
    "short_description": "Summarize this job in one short sentence.",
    "requirements": "List the job requirements, separated by semicolons.",
    "why_join": "List the reasons to join, separated by semicolons.",
}


class Summarizer:
    def __init__(self):
        self.device = settings.DEVICE
        print(f"Loading model {settings.MODEL_NAME} on {self.device}...")

        # bfloat16 keeps the 1.5B model usable on CPU without a 6+ GB fp32 copy.
        dtype = torch.float16 if self.device == "cuda" else torch.bfloat16
        self.tokenizer = AutoTokenizer.from_pretrained(settings.MODEL_NAME)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "left"

        self.model = AutoModelForCausalLM.from_pretrained(
            settings.MODEL_NAME,
            dtype=dtype,
        ).to(self.device)
        self.model.eval()
        print("Model loaded successfully!")

    def _truncate_context(self, text: str) -> str:
        context_limit = max(128, settings.MAX_INPUT_LENGTH - 96)
        token_ids = self.tokenizer.encode(
            text,
            add_special_tokens=False,
            max_length=context_limit,
            truncation=True,
        )
        return self.tokenizer.decode(token_ids, skip_special_tokens=True)

    def build_prompts(self, text: str) -> list[str]:
        context = self._truncate_context(text)
        return [
            (
                "Answer the question using only the job description. "
                "If the information is missing, answer N/A. Keep the answer concise.\n"
                f"Question: {question}\n"
                f"Job description:\n{context}\n"
                "Answer:"
            )
            for question in FIELD_QUESTIONS.values()
        ]

    def _generate_answers(self, prompts: list[str]) -> list[str]:
        answers: list[str] = []
        batch_size = settings.INFERENCE_BATCH_SIZE

        for start in range(0, len(prompts), batch_size):
            batch = prompts[start : start + batch_size]
            chat_batch = [
                self.tokenizer.apply_chat_template(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You extract facts from job descriptions. "
                                "Never invent missing information."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    tokenize=False,
                    add_generation_prompt=True,
                )
                for prompt in batch
            ]
            inputs = self.tokenizer(
                chat_batch,
                return_tensors="pt",
                padding=True,
                max_length=settings.MAX_INPUT_LENGTH,
                truncation=True,
            ).to(self.device)

            with torch.inference_mode():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=settings.MAX_FIELD_OUTPUT_LENGTH,
                    do_sample=False,
                    repetition_penalty=1.1,
                    no_repeat_ngram_size=3,
                    pad_token_id=self.tokenizer.pad_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                )

            prompt_length = inputs["input_ids"].shape[1]
            generated_tokens = outputs[:, prompt_length:]
            answers.extend(
                value.strip()
                for value in self.tokenizer.batch_decode(
                    generated_tokens,
                    skip_special_tokens=True,
                )
            )

        return answers

    @staticmethod
    def _clean_scalar(value: str) -> str:
        cleaned = value.strip().strip(" \t\r\n\"'()[]{}")
        if cleaned.lower().strip(". -") in {"", "n/a", "na", "none", "unknown", "not specified", "or"}:
            return ""
        return cleaned

    @staticmethod
    def _truncate_words(value: str, limit: int) -> str:
        words = value.split()
        return " ".join(words[:limit]).strip(" ,;.-")

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
    def _compact_requirement_tag(value: str) -> str:
        value = re.sub(r"^(?:and|or)\s+", "", value, flags=re.IGNORECASE)

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

        if re.match(r"^good\s+english\s+communication", value, flags=re.IGNORECASE):
            return "English Communication"
        return value

    def _clean_list(
        self,
        value: str,
        word_limit: int,
        tag_mode: bool = False,
    ) -> list[str]:
        parts = re.split(
            r"[;\n\u2022]|\s+-\s+|,(?=\s*[^,])",
            value,
        )
        cleaned: list[str] = []
        for part in parts:
            part = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", part)
            item = re.sub(r"^(requirements?|why join|reasons?)\s*:\s*", "", part, flags=re.IGNORECASE)
            item = self._clean_scalar(item)
            if tag_mode:
                item = self._compact_requirement_tag(item)
            item = self._truncate_words(item, word_limit)
            if item and item.lower() not in {existing.lower() for existing in cleaned}:
                cleaned.append(item)
        return cleaned

    def _normalize_answers(
        self,
        answers: dict[str, str],
        req_format: str,
        why_join_format: str,
        source_text: str = "",
    ) -> SummarizeResponse:
        data = {key: self._clean_scalar(value) for key, value in answers.items()}

        source_requirements = self._extract_labeled_section(
            source_text,
            r"requirements?|qualifications?|yêu cầu(?: công việc)?",
            r"benefits?|why\s+join(?:\s+us)?|quyền lợi|phúc lợi|responsibilities?|mô tả công việc",
        )
        source_why_join = self._extract_labeled_section(
            source_text,
            r"benefits?|why\s+join(?:\s+us)?|quyền lợi|phúc lợi",
            r"requirements?|qualifications?|yêu cầu(?: công việc)?|responsibilities?|mô tả công việc",
        )
        if source_requirements:
            data["requirements"] = source_requirements
        if source_why_join:
            data["why_join"] = source_why_join

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
        )
        why_join_limits = {"short": 15, "ultra_short": 8}
        why_join = self._clean_list(
            data.pop("why_join"), why_join_limits[why_join_format]
        )

        description_lines = data["short_description"].splitlines()
        description = self._truncate_words(description_lines[0] if description_lines else "", 30)
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

        prompts = self.build_prompts(text)
        generated = self._generate_answers(prompts)
        answers = dict(zip(FIELD_QUESTIONS, generated, strict=True))
        return self._normalize_answers(
            answers,
            req_format,
            why_join_format,
            source_text=text,
        ).model_dump()
