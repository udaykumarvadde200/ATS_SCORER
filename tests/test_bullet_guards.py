import json
from backend.services import bullet_rewriter as br


def _fake(monkeypatch, rewrites):
    monkeypatch.setattr(br, "_get_client", lambda: object())
    monkeypatch.setattr(br, "_call_groq", lambda c, s, u: json.dumps({"rewrites": rewrites}))


def test_label_prefix_is_ignored_when_checking_the_verb():
    parsed = {"projects": [{"title": "P", "description":
        "Multi-Agent Orchestration: Architected and built a routing system over 40 documents."}]}
    assert br.find_weak_bullets(parsed) == []


def test_typography_is_normalised(monkeypatch):
    _fake(monkeypatch, [{"original": "x",
        "rewrite": "Built a state\u2011driven agent \u2014 routing chats", "note": "ok"}])
    out = br.rewrite_bullets(["Worked on a state-driven agent that routes chats"])
    assert out[0]["rewrite"] == "Built a state-driven agent - routing chats"


def test_invented_improvement_claims_are_dropped(monkeypatch):
    original = "Developed transformer models and retrieval systems using MLflow for experiment tracking"
    _fake(monkeypatch, [{"original": original,
        "rewrite": "Developed transformer models with MLflow, achieving [X%] reproducibility improvement",
        "note": "invented claim"}])
    assert br.rewrite_bullets([original]) == []


def test_improvement_wording_is_kept_when_the_original_already_claims_it(monkeypatch):
    original = "Implemented vision-based detection, significantly improving task success rates"
    _fake(monkeypatch, [{"original": original,
        "rewrite": "Implemented vision-based detection, boosting task success rates by [X%]",
        "note": "placeholder"}])
    assert len(br.rewrite_bullets([original])) == 1
