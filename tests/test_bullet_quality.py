import json

from backend.services import bullet_rewriter as br


def fake(monkeypatch, items, captured=None):
    def call(client, system, user):
        if captured is not None:
            captured.append(user)
        return json.dumps({"rewrites": items})
    monkeypatch.setattr(br, "_get_client", lambda: object())
    monkeypatch.setattr(br, "_call_groq", call)


def test_cosmetic_rewrite_of_a_good_bullet_is_dropped_but_ideas_are_kept(monkeypatch):
    original = "Built a RAG chatbot to answer user questions using information retrieved from documents."
    fake(monkeypatch, [{"original": original,
                        "rewrite": "Built a RAG chatbot that answers user questions using information retrieved from documents.",
                        "note": "Added that", "measure_ideas": ["number of documents indexed", "average response time"]}])
    out = br.rewrite_bullets([original])
    assert len(out) == 1 and out[0]["rewrite"] == ""
    assert out[0]["ideas"] == ["number of documents indexed", "average response time"]


def test_cosmetic_rewrite_without_ideas_is_dropped_completely(monkeypatch):
    original = "Extended a scalar engine by implementing logarithm and exponential operations."
    fake(monkeypatch, [{"original": original,
                        "rewrite": "Extended a scalar engine by adding logarithm and exponential operations.",
                        "note": "Synonym", "measure_ideas": []}])
    assert br.rewrite_bullets([original]) == []


def test_buzzword_verbs_are_rejected(monkeypatch):
    original = "Used LangChain and ChromaDB to retrieve document content."
    fake(monkeypatch, [{"original": original, "rewrite": "Leveraged LangChain and ChromaDB to retrieve document content.",
                        "note": "stronger verb", "measure_ideas": ["number of documents indexed"]}])
    out = br.rewrite_bullets([original])
    assert out[0]["rewrite"] == "" and out[0]["ideas"]


def test_a_real_improvement_with_a_concrete_verb_is_kept(monkeypatch):
    original = "Used similarity ranking to return movies with similar traits."
    fake(monkeypatch, [{"original": original, "rewrite": "Applied similarity ranking to return movies with similar traits.",
                        "note": "Concrete verb", "measure_ideas": []}])
    assert br.rewrite_bullets([original])[0]["rewrite"].startswith("Applied")


def test_ongoing_work_keeps_its_ing_verb(monkeypatch):
    original = "Exploring cloud infrastructure for future scope."
    fake(monkeypatch, [{"original": original, "rewrite": "Exploring cloud hosting options for the platform's future scope.",
                        "note": "clearer", "measure_ideas": []}])
    assert br.rewrite_bullets([original])[0]["rewrite"].startswith("Exploring")


def test_ideas_with_numbers_are_removed_and_capped_at_three(monkeypatch):
    original = "Worked on the website for the team."
    fake(monkeypatch, [{"original": original, "rewrite": "", "note": "",
                        "measure_ideas": ["page load time", "increase traffic by 20%", "monthly visitors", "bug count", "pages built"]}])
    ideas = br.rewrite_bullets([original])[0]["ideas"]
    assert ideas == ["page load time", "monthly visitors", "bug count"]


def test_prompt_offers_verbs_the_scorer_recognises(monkeypatch):
    seen = []
    fake(monkeypatch, [], captured=seen)
    br.rewrite_bullets(["Worked on the website for the team."])
    assert "Built" in seen[0] and "Never start with Leveraged" in seen[0]
    assert all(v in br.ACTION_VERBS for v in br._PREFERRED_VERBS)
