from backend.services.grammar_checker import check_grammar

CLEAN = "Built a churn classifier with Scikit-learn and reached 84% accuracy on the test data."


def words(result, key="critical_errors"):
    return [e["error_text"] for e in result[key]]


def test_clean_text_has_no_errors_and_full_status():
    r = check_grammar(CLEAN)
    assert r["total_errors"] == 0 and r["penalty_applied"] == 0
    assert r["_component_status"] == "available"
    for key in ("critical_errors", "moderate_errors", "minor_errors", "grammar_score", "error_free_percentage"):
        assert key in r


def test_misspelling_is_critical_and_has_a_suggestion():
    r = check_grammar("I worked on the enviroment setup for the team.")
    assert "enviroment" in words(r)
    assert "environment" in r["critical_errors"][0]["suggestions"]


def test_repeated_word_lowercase_i_and_missing_space():
    r = check_grammar("Cleaned and merged merged the data. i built a model.Then deployed it.")
    assert any(e["error_text"] == "merged merged" for e in r["moderate_errors"])
    assert any(e["error_text"] == "i" for e in r["moderate_errors"])
    assert any(e["error_text"] == "model.Then" for e in r["minor_errors"])


def test_names_acronyms_camelcase_urls_and_hyphenated_parts_are_not_flagged():
    text = "Kubernetes NLP FastAPI PyTorch github.com/someone email a.b@example.com fine-tuned Hyderabad"
    assert check_grammar(text)["total_errors"] == 0


def test_words_from_the_candidates_own_skills_are_allowed():
    text = "We used fastapi and streamlit daily for the project."
    assert set(words(check_grammar(text))) == {"fastapi", "streamlit"}
    assert words(check_grammar(text, {"skills": ["FastAPI", "Streamlit"]})) == []


def test_valid_derived_words_pass_but_a_dropped_letter_does_not():
    assert check_grammar("The products were underpriced for months.")["total_errors"] == 0
    assert "featurs" in words(check_grammar("Engineered twelve featurs for the model."))


def test_penalty_grows_with_errors_and_is_capped():
    one = check_grammar("The enviroment was ready.")["penalty_applied"]
    many = check_grammar("enviroment seperate recieve definately occured begining adress wich untill tomorow")["penalty_applied"]
    assert 0 < one < many <= 20.0


def test_empty_and_none_input_are_safe():
    assert check_grammar("")["total_errors"] == 0
    assert check_grammar(None)["total_errors"] == 0


def test_very_long_run_together_words_are_ignored_and_fast():
    import time
    glued = ("ECEundergraduatewithafoundationinPython undergraduatewithafoundationin "
             "probabilitystatisticsmathematics machinelearningprojects ") * 20
    start = time.perf_counter()
    result = check_grammar(glued)
    assert time.perf_counter() - start < 2.0
    assert result["total_errors"] == 0


def test_many_unknown_words_stay_within_the_time_budget():
    import time
    text = " ".join(f"zzq{chr(97 + i % 26)}{chr(97 + (i // 26) % 26)}wxv" for i in range(400))
    start = time.perf_counter()
    result = check_grammar(text)
    assert time.perf_counter() - start < 4.0
    assert result["penalty_applied"] <= 20.0
