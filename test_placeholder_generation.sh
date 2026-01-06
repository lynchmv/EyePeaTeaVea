#!/bin/bash
# Test script to verify placeholder image generation

echo "Testing placeholder image generation..."
echo "========================================"
echo ""

# Get the secret_str from the first user in Redis (if available)
# Or you can manually set it
SECRET_STR="${1:-}"

if [ -z "$SECRET_STR" ]; then
    echo "Usage: $0 <secret_str> [tvg_id]"
    echo ""
    echo "To find your secret_str, check Redis or your Stremio addon URL"
    echo "Example: $0 muKgaVH6Co4J6XWux7ixxplpxfhWIJn9UCSR4W7t8aY"
    exit 1
fi

TVG_ID="${2:-test_channel}"

HOST_URL="${HOST_URL:-http://localhost:8020}"

echo "Testing with:"
echo "  Secret: ${SECRET_STR:0:20}..."
echo "  Channel ID: $TVG_ID"
echo "  Host: $HOST_URL"
echo ""

# Test logo endpoint
echo "1. Testing logo endpoint..."
curl -s -o /dev/null -w "   Status: %{http_code}\n" \
    "${HOST_URL}/${SECRET_STR}/logo/${TVG_ID}.png"

# Test poster endpoint  
echo "2. Testing poster endpoint..."
curl -s -o /dev/null -w "   Status: %{http_code}\n" \
    "${HOST_URL}/${SECRET_STR}/poster/${TVG_ID}.png"

# Test background endpoint
echo "3. Testing background endpoint..."
curl -s -o /dev/null -w "   Status: %{http_code}\n" \
    "${HOST_URL}/${SECRET_STR}/background/${TVG_ID}.png"

echo ""
echo "Check Docker logs for placeholder generation messages:"
echo "  docker compose logs -f | grep -i 'placeholder\|generating'"
echo ""
echo "To view a generated image, open in browser:"
echo "  ${HOST_URL}/${SECRET_STR}/logo/${TVG_ID}.png"
