#!/bin/bash
# Install AION git hooks into .git/hooks/
# Run once after cloning: bash scripts/hooks/install.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$(git -C "$SCRIPT_DIR" rev-parse --git-dir)/hooks"

cp "$SCRIPT_DIR/pre-commit" "$HOOKS_DIR/pre-commit"
chmod +x "$HOOKS_DIR/pre-commit"

echo "✓ AION git hooks installed."
echo "  pre-commit: doc-sync reminder when code changes without doc updates"
