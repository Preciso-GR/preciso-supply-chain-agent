from preciso_supply_agent.intent import resolve_chat_intent


REGISTRY = {
    "entities": [
        {
            "canonical_id": "facility:arkon-components:northbridge",
            "entity_type": "FACILITY",
            "display_name": "Northbridge Fabrication Facility",
            "documented_aliases": [{"alias": "Northbridge Site"}],
        },
        {
            "canonical_id": "facility:redwood-materials:harbor",
            "entity_type": "FACILITY",
            "display_name": "Harbor Casting Works",
            "documented_aliases": [],
        },
    ],
    "ambiguous_aliases": [{"alias": "Plant 7", "status": "unresolved"}],
}


def test_resolves_only_documented_facility_names_and_aliases():
    result = resolve_chat_intent("What is exposed if Northbridge Site is unavailable?", REGISTRY)
    assert result["status"] == "resolved"
    assert result["facility_id"] == "facility:arkon-components:northbridge"


def test_ambiguous_identity_is_never_resolved():
    result = resolve_chat_intent("What is affected if Plant 7 closes?", REGISTRY)
    assert result == {
        "status": "ambiguous_identity",
        "message": "Plant 7 is explicitly unresolved and was not mapped to a facility.",
        "alias": "Plant 7",
    }


def test_unsupported_question_does_not_become_a_graph_query():
    result = resolve_chat_intent("Forecast next quarter's inventory shortage", REGISTRY)
    assert result["status"] == "unsupported_intent"
