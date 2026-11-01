from backend.services.ats_scorer import _calc_ats_compatibility_score as calc

GOOD = """Sample Candidate
candidate07@example.com | +91 90000 00007 | github.com/sample-candidate-07
SUMMARY
Computer science student specializing in machine learning with hands-on experience building models.
TECHNICAL SKILLS
Languages: Python, SQL
EXPERIENCE
Machine Learning Intern, Sample Analytics | Jun 2024 - Aug 2024
- Cleaned and merged 3 sales datasets using SQL and Pandas to prepare data for forecasting work
- Built a forecasting prototype that the team used in weekly planning meetings every week
PROJECTS
Customer Churn Prediction
- Built a churn classifier with Scikit-learn and XGBoost on a 7,000-customer dataset
- Engineered 12 features with Pandas and reached 84% accuracy on the held-out test set
- Deployed the model as a Streamlit app packaged with Docker for easy sharing with classmates
EDUCATION
B.Tech Computer Science, Sample Institute of Technology, 2022 - 2026
""" * 1


def test_scanned_or_empty_file_scores_zero():
    assert calc("", {}, {}) == 0.0
    assert calc("   \n  ", {}, {}) == 0.0


def test_complete_resume_scores_high():
    assert calc(GOOD, {}, {}) >= 11.0


def test_missing_headings_and_contact_lower_the_score():
    bare = "Looking for a job where I can learn and grow. " * 40
    assert calc(bare, {}, {}) < calc(GOOD, {}, {})


def test_private_use_characters_are_penalised():
    assert calc(GOOD + "\uf0b7" * 40, {}, {}) < calc(GOOD, {}, {})


def test_location_penalty_is_subtracted_and_score_stays_in_range():
    assert calc(GOOD, {"penalty_applied": 4.0}, {}) == calc(GOOD, {}, {}) - 4.0
    assert 0.0 <= calc(GOOD, {"penalty_applied": 99.0}, {}) <= 15.0
    assert calc(GOOD * 3, {}, {}) <= 15.0


def test_mixed_date_styles_lose_a_point():
    mixed = GOOD + "\nStarted Jun 2024 and ended 08/2024"
    assert calc(mixed, {}, {}) < calc(GOOD, {}, {})
