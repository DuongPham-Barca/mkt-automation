from app.models import SummarizeResponse


def format_output(
    data: SummarizeResponse | dict,
    requirement_format: str = "short",
) -> str:
    normalized = SummarizeResponse.model_validate(data)
    lines = []

    lines.append((normalized.job_title or "N/A").upper())
    if normalized.subtitle:
        lines.append(normalized.subtitle)
    lines.append("")

    emp = normalized.employment_type or "N/A"
    contract = normalized.contract_type or "N/A"
    loc = normalized.location or "N/A"
    lines.append(f"{emp} | {contract} | {loc}")

    lines.append(normalized.salary or "N/A")
    lines.append(f"Bounty: {normalized.bounty or 'N/A'}")

    if normalized.short_description:
        lines.extend(["", normalized.short_description])

    lines.append("")
    lines.append("Requirements")
    if requirement_format == "tag" and normalized.requirements:
        lines.append(" ".join(f"[{req}]" for req in normalized.requirements))
    else:
        for req in normalized.requirements:
            lines.append(f"- {req}")

    if not normalized.requirements:
        lines.append("- N/A")

    lines.append("")
    lines.append("Why Join?")
    for why in normalized.why_join:
        lines.append(f"- {why}")

    if not normalized.why_join:
        lines.append("- N/A")

    return "\n".join(lines)
