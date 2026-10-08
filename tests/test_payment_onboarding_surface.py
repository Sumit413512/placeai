from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_STATIC = ROOT / "app" / "static"
PUBLIC_STATIC = ROOT / "public" / "static"


def _read(name: str) -> str:
    return (APP_STATIC / name).read_text(encoding="utf-8")


def _read_public(name: str) -> str:
    return (PUBLIC_STATIC / name).read_text(encoding="utf-8")


def test_public_payment_onboarding_pages_are_present_and_linked():
    pricing = _read("pricing.html")
    about = _read("about.html")
    contact = _read("contact.html")
    refund = _read("refund-cancellation.html")
    legal_links = _read("legal-links.js")

    for page in (pricing, about, contact, refund):
        assert "www.placeai.in" in page or "PlaceAI" in page
        assert 'href="/privacy"' in page
        assert 'href="/terms"' in page

    assert "Request access" in contact
    assert "₹299" in pricing
    assert "₹20" in pricing
    assert "₹299" in refund
    assert "₹20" in refund
    assert "original payment" in refund
    assert "/static/pricing.html" in legal_links
    assert "/static/about.html" in legal_links
    assert "/static/contact.html" in legal_links
    assert "/static/refund-cancellation.html" in legal_links


def test_payment_onboarding_surface_is_mirrored_to_public_bundle():
    for name in (
        "pricing.html",
        "about.html",
        "contact.html",
        "refund-cancellation.html",
        "legal-links.js",
    ):
        assert _read(name) == _read_public(name)


def test_payment_policy_never_claims_live_checkout_before_merchant_activation():
    pricing = _read("pricing.html").lower()
    refund = _read("refund-cancellation.html").lower()
    contact = _read("contact.html").lower()
    about = _read("about.html").lower()

    assert "online payment collection is not active yet" in pricing
    assert "checkout is currently disabled" in refund
    assert "live online checkout is not currently activated" in contact
    assert "live online checkout remains disabled" in about
    assert "unofficial personal transfer" in refund
