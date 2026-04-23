#!/usr/bin/env zsh

# Set script to exit on error
set -e

echo "🔍 Running ESLint and Testing..."
npm run check

if [ $? -eq 0 ]; then
    echo "✅ ESLint and Testing passed"
else
    echo "❌ ESLint and Testing failed"
    exit 1
fi