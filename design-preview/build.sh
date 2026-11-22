#!/bin/sh
set -eu
mkdir -p design-dist/assets
cp design-preview/index.html design-preview/style.css design-preview/app.js design-dist/
cp public/static/placeai-logo.webp public/static/placeai-hero-approved-hd.webp public/static/placeai-favicon-96.png design-dist/assets/

rm -rf design-dist/workspace-review
