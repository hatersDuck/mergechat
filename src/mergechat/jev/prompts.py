"""Versioned JEV questions for animal-transport order detection."""

from __future__ import annotations

from collections.abc import Sequence

from typesafe_sdk import Choice, Noul, Question

from mergechat.domain.message import RawMessage

PROMPT_VERSION = "jev-animal-orders-v1"


def build_questions() -> dict[str, Question]:
    """Return the structured questions sent to JEV.

    JEV system-one supports noul/choice/score/box questions, not arbitrary JSON
    extraction. Route, date, price, and contact are therefore recorded as
    presence flags rather than free-text fields.
    """

    return {
        "is_animal_transport": Noul(
            instructions="The message is about transporting animals.",
        ),
        "is_order": Noul(
            instructions=(
                "The message is an order or booking request for animal "
                "transportation, not general conversation, advertising, or a "
                "carrier offering their own services."
            ),
        ),
        "has_route": Noul(
            instructions="The message includes both pickup and delivery locations.",
        ),
        "has_contact": Noul(
            instructions="The message includes contact details or asks to be contacted.",
        ),
        "quote_only": Noul(
            instructions=(
                "The message only asks for a price or availability, not a firm order."
            ),
        ),
        "animal_type": Choice(
            instructions="What type of animals are requested for transport?",
            criteria={
                "horses": "Only horses",
                "other_animals": "Only non-horse animals",
                "mixed": "Both horses and other animals",
                "unspecified": "Animal type is not specified",
                "not_animal_transport": "Not about animal transportation",
            },
        ),
        "headcount": Choice(
            instructions="How many animals are requested for transport?",
            criteria={
                "1_2": "1 or 2 animals",
                "3_8": "3 to 8 animals",
                "9_10": "9 or 10 animals",
                "more_than_10": "More than 10 animals",
                "unspecified": "Number of animals is not specified",
            },
        ),
        "capacity_fit": Choice(
            instructions="Can the request be served with the available vehicles?",
            criteria={
                "trailer_only": "Fits the 2-animal trailer only",
                "truck_only": "Fits the 8-horse truck only",
                "both_required": (
                    "Requires both the 8-horse truck and the 2-animal trailer together"
                ),
                "not_possible": (
                    "Exceeds available capacity or cannot be transported"
                ),
                "unknown": "Not enough information to decide",
            },
        ),
    }


def _message_payload(message: RawMessage) -> dict[str, object]:
    return {
        "nickname": message.author_name or message.author_external_id or "unknown",
        "timestamp": message.timestamp.isoformat(),
        "text": message.text,
    }


def build_state(message: RawMessage) -> dict[str, object]:
    """Build the JEV conversation state for a single stored message."""

    return {
        "conversation": {
            "thread_id": message.external_chat_id,
            "messages": [_message_payload(message)],
        }
    }


def build_batch_state(messages: Sequence[RawMessage]) -> dict[str, object]:
    """Build one conversation state from an ordered batch of messages."""

    if not messages:
        raise ValueError("At least one message is required.")
    return {
        "conversation": {
            "thread_id": messages[0].external_chat_id,
            "messages": [_message_payload(message) for message in messages],
        }
    }
