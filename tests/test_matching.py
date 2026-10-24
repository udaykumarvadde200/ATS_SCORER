from backend.utils.matching import normalize_skill, fuzzy_match_keywords
from backend.services.ats_scorer import _skill_in_text


def test_alias_normalization():
    assert normalize_skill('ReactJS') == 'react'
    assert normalize_skill(' K8s ') == 'kubernetes'


def test_fuzzy_match_uses_aliases_and_reports_missing():
    r = fuzzy_match_keywords(['Python', 'ReactJS', 'sklearn'],
                             ['react', 'scikit-learn', 'Kubernetes'])
    assert r['matched'] == ['react', 'scikit-learn']
    assert r['missing'] == ['Kubernetes']


def test_whole_token_skill_matching():
    assert not _skill_in_text('Java', 'Built apps in JavaScript')
    assert _skill_in_text('C++', 'Wrote C++ and Python')
    assert _skill_in_text('Node.js', 'Backend: Node.js, Express')
