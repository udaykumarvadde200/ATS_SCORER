from backend.utils.action_verbs import detect_action_verbs


def test_counts_bullet_starting_verbs_only():
    text = "\u2022 Developed a REST API. Reduced latency by 20%.\n- Led a team of 4\nLead Engineer, Acme\nResearch Intern\n"
    assert detect_action_verbs(text) == ['developed', 'led', 'reduced']


def test_empty_text():
    assert detect_action_verbs('') == []
