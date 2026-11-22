"""Assemble the interactive UI review under its own path on the existing site."""
import re
import shutil
import sys
from pathlib import Path

source, target = (Path(arg) for arg in sys.argv[1:])
target.mkdir(parents=True, exist_ok=True)
shutil.copytree(source / "public/static", target / "static", dirs_exist_ok=True)
prefix = "/workspace-review"
for path in (target / "static").iterdir():
    if path.suffix in {".js", ".css", ".html"}:
        text = path.read_text(encoding="utf-8").replace("/static/", prefix + "/static/")
        text = re.sub(r'''(['"])/mock-interview\1''', lambda match: match[1] + prefix + "/mock-interview.html" + match[1], text)
        path.write_text(text, encoding="utf-8")
review = '<link rel="stylesheet" href="/workspace-review/review.css"><script src="/workspace-review/review.js"></script>'
for name, path in (("index.html", source / "public/index.html"),
                   ("mock-interview.html", source / "app/templates/mock-interview.html")):
    text = path.read_text(encoding="utf-8").replace("/static/", prefix + "/static/")
    text = text.replace("</head>", '<meta name="robots" content="noindex,nofollow">' + review + "</head>", 1)
    (target / name).write_text(text, encoding="utf-8")
