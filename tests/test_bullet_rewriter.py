import json
from backend.services import bullet_rewriter as br


PARSED = {
    "experience": [],
    "projects": [
        {"title": "RAG Platform",
         "description": "Built a retrieval pipeline with LangGraph that answers questions over 120 documents. "
                        "Worked on the chatbot frontend using Streamlit and some other things. "
                        "Responsible for the database design and API layer for the app."},
        {"title": "Micrograd", "description": "Autograd engine"},
    ],
}


def test_find_weak_bullets_flags_missing_verb_and_metric():
    weak = br.find_weak_bullets(PARSED)
    bullets = [w["bullet"] for w in weak]
    assert not any(b.startswith("Built a retrieval") for b in bullets)   # verb + metric, fine
    assert any(b.startswith("Worked on the chatbot") for b in bullets)
    assert any(b.startswith("Responsible for") for b in bullets)
    assert all("Autograd engine" != b for b in bullets)                  # too short, skipped
    assert weak[0]["issues"] == "does not start with a strong action verb; no measurable result"


def test_find_weak_bullets_handles_bad_data():
    assert br.find_weak_bullets({"experience": None, "projects": [None, {"description": None}]}) == []


def test_new_numbers_are_rejected_but_placeholders_allowed():
    original = "Trained a classifier on the dataset"
    assert br._introduces_new_numbers(original, "Trained a classifier reaching 95% accuracy")
    assert not br._introduces_new_numbers(original, "Trained a classifier reaching [X%] accuracy")
    assert not br._introduces_new_numbers("Indexed 120 documents", "Indexed 120 documents with [N] queries")


def _fake_groq(monkeypatch, payload):
    monkeypatch.setattr(br, "_get_client", lambda: object())
    monkeypatch.setattr(br, "_call_groq", lambda client, system, user: payload)


def test_rewrite_keeps_safe_rewrites_and_drops_invented_numbers(monkeypatch):
    payload = json.dumps({"rewrites": [
        {"original": "x", "rewrite": "Developed a chatbot frontend in Streamlit serving [N] users", "note": "Added verb and placeholder"},
        {"original": "y", "rewrite": "Designed the database and API layer, cutting latency by 40%", "note": "invented number"},
    ]})
    _fake_groq(monkeypatch, payload)
    out = br.rewrite_bullets([
        "Worked on the chatbot frontend using Streamlit",
        "Responsible for the database design and API layer",
    ])
    assert len(out) == 1
    assert out[0]["original"] == "Worked on the chatbot frontend using Streamlit"
    assert "[N] users" in out[0]["rewrite"]


def test_rewrite_raises_on_garbage(monkeypatch):
    _fake_groq(monkeypatch, "not json at all")
    try:
        br.rewrite_bullets(["Worked on the chatbot frontend using Streamlit"])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_rewrite_empty_input_makes_no_call(monkeypatch):
    monkeypatch.setattr(br, "_get_client", lambda: (_ for _ in ()).throw(AssertionError("no call expected")))
    assert br.rewrite_bullets([]) == []
    assert br.rewrite_bullets(["   ", 5]) == []
