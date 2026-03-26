from __future__ import annotations

import json
import re
from dataclasses import dataclass


TEXT_CONTENT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/xml",
}


@dataclass
class DocumentExtraction:
    extracted_text: str
    extraction_confidence: float
    extracted_fields: dict[str, object]


def _decode_text(content: bytes, content_type: str) -> str:
    if content_type not in TEXT_CONTENT_TYPES and not content_type.startswith("text/"):
        return ""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""


def _match_amounts(text: str) -> list[float]:
    dollar_matches = re.findall(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text)
    matches = dollar_matches or re.findall(r"\b([0-9][0-9,]{2,}(?:\.[0-9]{1,2})?)\b", text)
    amounts: list[float] = []
    for match in matches[:5]:
        try:
            amount = float(match.replace(",", ""))
            if amount >= 100:
                amounts.append(amount)
        except ValueError:
            continue
    return amounts


def _match_days(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:calendar\s+)?day", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    week_match = re.search(r"(\d+)\s*week", text, re.IGNORECASE)
    if week_match:
        return int(week_match.group(1)) * 7
    return None


def _risk_tags(text: str) -> list[str]:
    tags: list[str] = []
    lowered = text.casefold()
    keyword_map = {
        "permit_blocker": ["revision", "permit", "resubmit", "plan check", "inspector"],
        "schedule_risk": ["delay", "late", "extension", "calendar day", "week"],
        "owner_scope_gap": ["owner request", "scope gap", "added scope"],
        "unpriced_exposure": ["tbd", "budget", "pricing pending", "unpriced"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in lowered for keyword in keywords):
            tags.append(tag)
    return tags


def extract_document_artifacts(filename: str, content_type: str, content: bytes) -> DocumentExtraction:
    extracted_text = _decode_text(content, content_type).strip()
    if not extracted_text:
        return DocumentExtraction(
            extracted_text="",
            extraction_confidence=0.1,
            extracted_fields={"filename": filename, "summary": "Binary document stored without text extraction."},
        )

    first_lines = [line.strip() for line in extracted_text.splitlines() if line.strip()][:6]
    summary = " ".join(first_lines)[:500]

    permit_number_match = re.search(r"(?:permit|application)\s*(?:number|#|no\.?)[:\s]+([A-Z0-9-]+)", extracted_text, re.IGNORECASE)
    revision_match = re.search(r"(revision|resubmittal|correction)", extracted_text, re.IGNORECASE)

    extracted_fields: dict[str, object] = {
        "filename": filename,
        "summary": summary,
        "risk_tags": _risk_tags(extracted_text),
    }
    if permit_number_match:
        extracted_fields["permit_number"] = permit_number_match.group(1)
    if revision_match:
        extracted_fields["revision_requested"] = True

    amounts = _match_amounts(extracted_text)
    if amounts:
        extracted_fields["amount_candidates_usd"] = amounts

    schedule_days = _match_days(extracted_text)
    if schedule_days is not None:
        extracted_fields["schedule_impact_days"] = schedule_days

    if content_type == "application/json":
        try:
            extracted_fields["json_preview"] = json.loads(extracted_text)
        except json.JSONDecodeError:
            pass

    confidence = 0.92 if len(extracted_text) > 80 else 0.68
    return DocumentExtraction(
        extracted_text=extracted_text[:20_000],
        extraction_confidence=confidence,
        extracted_fields=extracted_fields,
    )
