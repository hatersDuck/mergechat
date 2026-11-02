"""Parsing and validation of JEV structured answers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JevResponseError(ValueError):
    """Raised when JEV returns a response that cannot be used safely."""


class JevClassification(BaseModel):
    is_order: bool
    confidence: float = Field(ge=0.0, le=1.0)
    answers: dict[str, Any]
    attributes: dict[str, Any]
    model: str
    usage: dict[str, Any]
    latency_ms: float
    prompt_version: str


def _answer_payload(answer: Any) -> dict[str, Any]:
    answer_type = getattr(answer, "type", None)
    if answer_type == "noul":
        return {"type": "noul", "noul": float(answer.noul)}
    if answer_type == "choice":
        return {
            "type": "choice",
            "choice": answer.choice,
            "confidence": float(answer.confidence),
            "probabilities": dict(answer.probabilities),
        }
    if answer_type == "score":
        return {
            "type": "score",
            "score": float(answer.score),
            "confidence": float(answer.confidence),
            "legend": dict(answer.legend),
            "probabilities": dict(answer.probabilities),
        }
    raise JevResponseError(f"Unsupported JEV answer type: {answer_type!r}")


def _noul(answers: dict[str, dict[str, Any]], name: str) -> float:
    answer = answers.get(name)
    if not isinstance(answer, dict) or answer.get("type") != "noul":
        raise JevResponseError(f"Missing required noul answer: {name}")
    value = answer.get("noul")
    if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
        raise JevResponseError(f"Invalid noul value for {name}: {value!r}")
    return float(value)


def _choice(
    answers: dict[str, dict[str, Any]], name: str, allowed: set[str]
) -> str:
    answer = answers.get(name)
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise JevResponseError(f"Missing required choice answer: {name}")
    value = answer.get("choice")
    if not isinstance(value, str) or value not in allowed:
        raise JevResponseError(
            f"Invalid choice value for {name}: {value!r}; allowed={sorted(allowed)}"
        )
    return value


def parse_response(
    response: Any,
    *,
    prompt_version: str,
    latency_ms: float,
    threshold: float = 0.5,
) -> JevClassification:
    """Validate a ``SystemOneResponse`` and map it to the order schema."""

    raw_answers = getattr(response, "answers", None)
    if not isinstance(raw_answers, dict) or not raw_answers:
        raise JevResponseError("JEV response contains no answers.")

    answers = {name: _answer_payload(answer) for name, answer in raw_answers.items()}
    order_probability = _noul(answers, "is_order")
    is_animal_transport = _noul(answers, "is_animal_transport") >= threshold
    has_route = _noul(answers, "has_route") >= threshold
    has_contact = _noul(answers, "has_contact") >= threshold
    quote_only = _noul(answers, "quote_only") >= threshold
    animal_type = _choice(
        answers,
        "animal_type",
        {"horses", "other_animals", "mixed", "unspecified", "not_animal_transport"},
    )
    headcount = _choice(
        answers, "headcount", {"1_2", "3_8", "9_10", "more_than_10", "unspecified"}
    )
    capacity_fit = _choice(
        answers,
        "capacity_fit",
        {"trailer_only", "truck_only", "both_required", "not_possible", "unknown"},
    )

    cargo_type = {
        "horses": "horse",
        "other_animals": "other_animal",
        "mixed": "mixed",
    }.get(animal_type)

    attributes: dict[str, Any] = {
        "is_animal_transport": is_animal_transport,
        "has_route": has_route,
        "has_contact": has_contact,
        "quote_only": quote_only,
        "animal_type": animal_type,
        "headcount": headcount,
        "capacity_fit": capacity_fit,
        "cargo_type": cargo_type,
        "route_from": None,
        "route_to": None,
        "date": None,
        "price": None,
        "contact": None,
        "reason": None,
        "extraction_notes": (
            "JEV system-one returns noul/choice answers only; free-text route, "
            "date, price, and contact extraction is not available through this API."
        ),
    }

    usage = getattr(response, "usage", None)
    usage_payload = {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }

    return JevClassification(
        is_order=order_probability >= threshold,
        confidence=order_probability,
        answers=answers,
        attributes=attributes,
        model=str(getattr(response, "model", "") or ""),
        usage=usage_payload,
        latency_ms=latency_ms,
        prompt_version=prompt_version,
    )
