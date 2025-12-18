#!/bin/bash
# Script to clone or update the tv-logos repository

set -e

REPO_URL="https://github.com/tv-logo/tv-logos.git"
REPO_DIR="${TV_LOGOS_REPO_PATH:-./tv-logos}"

echo "TV Logos Repository Manager"
echo "============================"
echo "Repository: $REPO_URL"
echo "Local path: $REPO_DIR"
echo ""

if [ -d "$REPO_DIR" ]; then
    echo "Repository exists. Updating..."
    cd "$REPO_DIR"
    git fetch origin
    git reset --hard origin/main
    git clean -fd
    echo "Repository updated successfully."
else
    echo "Repository not found. Cloning..."
    git clone --depth 1 "$REPO_URL" "$REPO_DIR"
    echo "Repository cloned successfully."
fi

echo ""
echo "Repository size:"
du -sh "$REPO_DIR"

echo ""
echo "Done!"
