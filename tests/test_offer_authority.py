from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_offer_status_authority_is_explicit_in_backend() -> None:
    source = (ROOT / "app/routers/hardening2.py").read_text(encoding="utf-8")
    assert 'VALID_OFFER_STATUSES' in source
    assert 'STUDENT_OFFER_DECISIONS = {"accepted", "declined"}' in source
    assert 'OPERATOR_OFFER_STATUSES' in source
    assert 'Unsupported offer status' in source
    assert 'Only the student may accept or decline an offer' in source


def test_institution_ui_does_not_make_student_offer_decisions() -> None:
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    institution_anchor = "pageHead('Offer management','Record CTC structure, offer lifecycle, PPO status and joining outcomes.'"
    start = js.index(institution_anchor)
    section = js[start:start + 5000]
    assert '<option value="accepted">Accepted</option>' not in section
    assert '<option value="declined">Declined</option>' not in section
    assert '<option value="joined">Joined</option>' in section


def test_student_offer_decision_controls_remain_available() -> None:
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'data-action="student-offer-decision"' in js
    assert 'data-value="accepted"' in js
    assert 'data-value="declined"' in js
