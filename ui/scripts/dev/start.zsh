#!/usr/bin/env zsh

# Set script to exit on error
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "${YELLOW}Starting UI Development Server...${NC}"

# Check if node_modules exists, if not install dependencies
if [ ! -d "node_modules" ]; then
    echo "${YELLOW}Installing dependencies...${NC}"
    npm install
fi

# Check if environment variables are set up
if [ ! -f ".env" ]; then
    echo "${YELLOW}Creating default .env file...${NC}"
    cp .env.example .env 2>/dev/null || touch .env
fi

# Start the development server
echo "${GREEN}Starting Vite dev server...${NC}"
npm run dev 