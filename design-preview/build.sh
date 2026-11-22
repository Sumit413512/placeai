#!/bin/sh
set -eu
mkdir -p design-dist/assets
cp design-preview/index.html design-preview/style.css design-preview/app.js design-dist/
cp public/static/placeai-logo.webp public/static/placeai-hero-approved-hd.webp public/static/placeai-favicon-96.png design-dist/assets/

# Replace the old entry points so previously cached links have a retirement notice.
rm -rf design-dist/workspace-review
mkdir -p design-dist/workspace-review
cat > design-dist/workspace-review/index.html <<'RETIRED'
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow"><title>PlaceAI preview retired</title></head>
<body><main><h1>This design preview has been retired.</h1><p><a href="https://www.placeai.in/">Visit PlaceAI</a></p></main></body></html>
RETIRED
cp design-dist/workspace-review/index.html design-dist/workspace-review/mock-interview.html
printf '%s\n' '{}' > design-dist/workspace-review/sample-data.json
: > design-dist/workspace-review/review.js
: > design-dist/workspace-review/review.css
