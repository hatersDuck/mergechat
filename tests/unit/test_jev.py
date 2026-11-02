from __future__ import annotations

import pytest
from typesafe_sdk import ChoiceAnswer, NoulAnswer, SystemOneResponse, Usage

from mergechat.jev.schemas import JevResponseError, parse_response


def _response(**overrides: object) -> SystemOneResponse:
    answers = {
        "is_animal_transport": NoulAnswer(noul=0.96),
        "is_order": NoulAnswer(noul=0.91),
        "has_route": NoulAnswer(noul=0.88),
        "has_contact": NoulAnswer(noul=0.2),
        "quote_only": NoulAnswer(noul=0.1),
        "animal_type": ChoiceAnswer(
            choice="horses", confidence=0.93, probabilities={"horses": 0.93}
        ),
        "headcount": ChoiceAnswer(
            choice="1_2", confidence=0.8, probabilities={"1_2": 0.8}
        ),
        "capacity_fit": ChoiceAnswer(
            choice="trailer_only",
            confidence=0.7,
            probabilities={"trailer_only": 0.7},
        ),
    }
    answers.update(overrides)
    return SystemOneResponse(
        model="jev-latest",
        usage=Usage(input_tokens=120, output_tokens=12),
        answers=answers,
    )


def test_parses_order_classification() -> None:
    result = parse_response(
        _response(), prompt_version="test-v1", latency_ms=321.0
    )

    assert result.is_order is True
    assert result.confidence == pytest.approx(0.91)
    assert result.attributes["animal_type"] == "horses"
    assert result.attributes["headcount"] == "1_2"
    assert result.attributes["cargo_type"] == "horse"
    assert result.attributes["has_route"] is True
    assert result.attributes["has_contact"] is False
    assert result.usage["input_tokens"] == 120
    assert result.latency_ms == 321.0


def test_missing_required_answer_is_rejected() -> None:
    response = _response()
    del response.answers["is_order"]

    with pytest.raises(JevResponseError):
        parse_response(response, prompt_version="test-v1", latency_ms=1.0)


def test_unknown_choice_value_is_rejected() -> None:
    response = _response(
        animal_type=ChoiceAnswer(
            choice="unicorns", confidence=0.9, probabilities={"unicorns": 0.9}
        )
    )
    with pytest.raises(JevResponseError):
        parse_response(response, prompt_version="test-v1", latency_ms=1.0)


def test_threshold_controls_is_order() -> None:
    result = parse_response(
        _response(is_order=NoulAnswer(noul=0.55)),
        prompt_version="test-v1",
        latency_ms=1.0,
        threshold=0.7,
    )
    assert result.is_order is False
    assert result.confidence == pytest.approx(0.55)
