from pydantic import BaseModel, ConfigDict, Field, field_validator

class SummarizeResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    job_title: str = ""
    subtitle: str = ""
    employment_type: str = ""
    contract_type: str = ""
    location: str = ""
    salary: str = ""
    bounty: str = ""
    short_description: str = ""
    requirements: list[str] = Field(default_factory=list)
    why_join: list[str] = Field(default_factory=list)
    raw_response: str = ""

    @field_validator(
        "job_title",
        "subtitle",
        "employment_type",
        "contract_type",
        "location",
        "salary",
        "bounty",
        "short_description",
        "raw_response",
        mode="before",
    )
    @classmethod
    def normalize_string(cls, value: object) -> str:
        return "" if value is None else str(value)

    @field_validator("requirements", "why_join", mode="before")
    @classmethod
    def normalize_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value)]

class OutputData(BaseModel):
    data: SummarizeResponse
    formatted_text: str
