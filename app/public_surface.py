"""Public sharing metadata with a fixed canonical origin and no private query data."""

import re
from html import escape

ORIGIN = "https://www.placeai.in"
PATHS = {
    "index.html": "/",
    "privacy.html": "/privacy",
    "terms.html": "/terms",
    "acceptable-use.html": "/acceptable-use",
    "mock-interview.html": "/mock-interview",
}
PATHS.update(
    {
        name: "/static/" + name
        for name in ("about.html", "contact.html", "pricing.html", "service-delivery.html", "refund-cancellation.html")
    }
)


def enhance_public_html(html: str, name: str) -> str:
    if name not in PATHS or 'property="og:title"' in html:
        return html
    path = PATHS.get(name, "/")
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    description = re.search(r'<meta name="description" content="([^"]*)"', html)
    title_text = title.group(1) if title else "PlaceAI"
    description_text = description.group(1) if description else "AI-assisted campus placement operations."
    meta = [
        f'<link rel="canonical" href="{ORIGIN}{path}">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="PlaceAI">',
        f'<meta property="og:title" content="{escape(title_text, quote=True)}">',
        f'<meta property="og:description" content="{description_text}">',
        f'<meta property="og:url" content="{ORIGIN}{path}">',
        f'<meta property="og:image" content="{ORIGIN}/static/placeai-hero-approved-hd.webp">',
        '<meta property="og:image:alt" content="PlaceAI campus placement collaboration">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
    if name == "mock-interview.html":
        meta.append('<meta name="robots" content="noindex, nofollow">')
    return html.replace("</head>", "\n".join(meta) + "\n</head>", 1)
