#!/bin/bash
# Script to update the tv-logos repository (for running containers)

set -e

REPO_DIR="${TV_LOGOS_REPO_PATH:-./tv-logos}"

if [ ! -d "$REPO_DIR" ]; then
    echo "Error: Repository directory not found at $REPO_DIR"
    echo "Set TV_LOGOS_REPO_PATH environment variable or ensure repository is cloned."
    exit 1
fi

echo "Updating tv-logos repository..."
echo "Repository path: $REPO_DIR"
echo ""

cd "$REPO_DIR"
git fetch origin
git reset --hard origin/main
git clean -fd

echo ""
echo "Repository updated successfully."
echo "Repository size:"
du -sh "$REPO_DIR"
