"""Retrieve live official references when a provider's search tool has no quota."""
from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

TRUSTED_DOMAINS = frozenset({
    "postgresql.org", "mysql.com", "sqlite.org", "mariadb.com", "microsoft.com",
    "python.org", "pandas.pydata.org", "numpy.org", "scipy.org", "scikit-learn.org",
    "pytorch.org", "tensorflow.org", "keras.io", "r-project.org", "posit.co",
    "developer.mozilla.org", "w3.org", "web.dev", "javascript.info", "typescriptlang.org",
    "react.dev", "vuejs.org", "angular.dev", "nodejs.org", "nextjs.org",
    "java.com", "oracle.com", "openjdk.org", "docs.rs", "rust-lang.org", "go.dev",
    "kotlinlang.org", "swift.org", "php.net", "ruby-lang.org", "dart.dev", "flutter.dev",
    "git-scm.com", "docs.github.com", "docker.com", "kubernetes.io", "aws.amazon.com",
    "cloud.google.com", "apache.org", "redis.io", "mongodb.com", "fastapi.tiangolo.com",
    "mit.edu", "stanford.edu", "berkeley.edu", "harvard.edu", "openstax.org", "nptel.ac.in",
    "khanacademy.org", "open.edu", "nasa.gov", "nist.gov", "cisco.com", "ietf.org",
})
MAX_BYTES = 450_000


def validate_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError("Reference must be a public HTTPS document")
    if parsed.query or parsed.fragment or not any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS):
        raise ValueError("Reference domain is not an approved educational publisher")
    for address in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ValueError("Reference must resolve only to public addresses")
    return url


class DocumentText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title_parts, self.skip, self.in_title = [], [], [], False

    def handle_starttag(self, tag, attrs):
        if tag == "title": self.in_title = True
        if self.skip or tag in {"script", "style", "nav", "header", "footer", "aside", "noscript", "head"}:
            if tag not in {"meta", "link", "br", "img", "input", "hr", "source", "wbr"}:
                self.skip.append(tag)
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "pre", "tr", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title": self.in_title = False
        if self.skip and tag in self.skip:
            self.skip = self.skip[:self.skip.index(tag)]
        elif not self.skip and tag in {"p", "div", "li", "pre", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, value):
        if self.in_title: self.title_parts.append(value)
        if not self.skip: self.parts.append(value)


def fetch_document(url):
    with httpx.Client(timeout=httpx.Timeout(8, connect=4), follow_redirects=False,
                      headers={"User-Agent": "PlaceAI-Learning-Hub/1.0 (+https://www.placeai.in)",
                               "Accept": "text/html,text/plain"}) as client:
        for _ in range(3):
            validate_url(url)
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                if not any(mime in response.headers.get("content-type", "") for mime in ["text/html", "text/plain", "text/markdown"]):
                    raise ValueError("Reference is not a readable web document")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES: raise ValueError("Reference exceeds the document size limit")
                    chunks.append(chunk)
                parser = DocumentText()
                parser.feed(b"".join(chunks).decode("utf-8", errors="replace"))
                text = "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip())
                if len(text) < 500: raise ValueError("Reference has insufficient readable evidence")
                return {"url": url, "title": " ".join(parser.title_parts).strip()[:240] or urlsplit(url).hostname}, text[:14000]
    raise ValueError("Reference has too many redirects")


def research_documents(subject, generate):
    schema = {"type": "object", "properties": {"urls": {"type": "array", "items": {"type": "string"},
              "minItems": 3, "maxItems": 8}}, "required": ["urls"], "additionalProperties": False}
    selected, model = generate(
        "Select 6-8 specific official documentation or university teaching HTTPS pages for the subject below. "
        "Return reference candidates only. They will be fetched and validated; do not claim they have already been researched. "
        "Prefer deep topic-specific pages over homepages. No query strings, fragments, login pages or article reproductions. "
        "Use these publisher domains: " + ", ".join(sorted(TRUSTED_DOMAINS)) + "\nSUBJECT DATA:\n" + subject,
        schema, max_output_tokens=1500,
    )
    sources, excerpts, seen = [], [], set()
    urls = selected.get("urls", [])
    if not isinstance(urls, list): raise ValueError("Reference candidates must be a list")
    # Fallback candidates are still fetched and subjected to the same public-host
    # and evidence checks. A known URL alone never becomes a citation.
    seeds = []
    if re.search(r"\b(?:sql|postgresql|postgres)\b", subject, re.I):
        seeds = ["https://www.postgresql.org/docs/current/" + name for name in
                 ("tutorial-select.html", "queries-table-expressions.html", "sql-expressions.html")]
    elif re.search(r"\bpython\b", subject, re.I):
        seeds = ["https://docs.python.org/3/" + name for name in ("tutorial/", "reference/", "library/")]
    for url in [*urls[:8], *seeds]:
        if not isinstance(url, str) or len(url) > 1800 or url in seen: continue
        seen.add(url)
        try:
            source, excerpt = fetch_document(url)
        except (ValueError, OSError, httpx.HTTPError):
            continue
        if any(existing["url"] == source["url"] for existing in sources): continue
        sources.append(source)
        excerpts.append(f"LIVE REFERENCE {len(sources)}: {source['title']}\nURL: {source['url']}\nEXCERPT:\n{excerpt}")
        if len(sources) == 5: break
    if len(sources) < 3:
        raise RuntimeError("LEARNING_LIVE_REFERENCES_UNAVAILABLE")
    return "\n\n".join(excerpts), sources, "verified-web:" + model
