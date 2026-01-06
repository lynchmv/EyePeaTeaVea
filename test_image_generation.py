#!/usr/bin/env python3
"""
Test script to verify placeholder image generation is working.

This script tests the new image generation functions directly.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from image_processor import (
    generate_logo_placeholder,
    generate_poster_placeholder,
    generate_background_placeholder,
    LOGO_WIDTH,
    LOGO_HEIGHT,
    POSTER_WIDTH,
    POSTER_HEIGHT,
    BACKGROUND_WIDTH,
    BACKGROUND_HEIGHT
)

def test_image_generation():
    """Test all placeholder image generators."""
    print("Testing placeholder image generation...")
    print("=" * 60)
    
    test_title = "Test Channel"
    
    # Test logo generation
    print(f"\n1. Generating logo placeholder ({LOGO_WIDTH}x{LOGO_HEIGHT})...")
    try:
        logo = generate_logo_placeholder(test_title)
        print(f"   ✓ Logo generated: {len(logo.getvalue())} bytes")
    except Exception as e:
        print(f"   ✗ Logo generation failed: {e}")
        return False
    
    # Test poster generation
    print(f"\n2. Generating poster placeholder ({POSTER_WIDTH}x{POSTER_HEIGHT})...")
    try:
        poster = generate_poster_placeholder(test_title)
        print(f"   ✓ Poster generated: {len(poster.getvalue())} bytes")
    except Exception as e:
        print(f"   ✗ Poster generation failed: {e}")
        return False
    
    # Test background generation
    print(f"\n3. Generating background placeholder ({BACKGROUND_WIDTH}x{BACKGROUND_HEIGHT})...")
    try:
        background = generate_background_placeholder(test_title)
        print(f"   ✓ Background generated: {len(background.getvalue())} bytes")
    except Exception as e:
        print(f"   ✗ Background generation failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✓ All image generation tests passed!")
    print("\nTo see the generated images in your application:")
    print("1. Make sure you have channels with the generic placeholder URL")
    print("2. Request an image endpoint: http://your-host/{secret_str}/logo/{tvg_id}.png")
    print("3. Check the Docker logs: docker compose logs -f")
    
    return True

if __name__ == "__main__":
    success = test_image_generation()
    sys.exit(0 if success else 1)
