#!/bin/sh
set -eu
mkdir -p design-dist/assets
cp design-preview/index.html design-preview/style.css design-preview/app.js design-dist/
cp public/static/placeai-logo.webp public/static/placeai-hero-approved-hd.webp public/static/placeai-favicon-96.png design-dist/assets/

review_source=$(mktemp -d)
trap 'rm -rf "$review_source"' EXIT
curl --fail --silent --show-error --location --retry 3 \
  "https://codeload.github.com/Sumit413512/placeai/tar.gz/691a23a5940b350330e76e1e28164e978bbe3dcb" \
  --output "$review_source/source.tgz"
tar -xzf "$review_source/source.tgz" --strip-components=1 -C "$review_source"
python3 design-preview/workspace-review/prepare.py "$review_source" design-dist/workspace-review
cp design-preview/workspace-review/sample-data.json design-preview/workspace-review/review.js design-preview/workspace-review/review.css design-dist/workspace-review/
