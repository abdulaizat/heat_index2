#!/usr/bin/env python3
"""
AMSR-2 Domain Test Script
Tests the domain configuration and displays information
"""

from amsr2_config import (
    DOMAIN_COORDINATES, DOMAIN_NAME, DOMAIN_BOUNDS,
    display_domain_info, get_domain_string
)

def test_domain_configuration():
    """Test the domain configuration."""
    print("🧪 Testing AMSR-2 Domain Configuration")
    print("=" * 50)
    
    # Display domain information
    display_domain_info()
    
    # Test domain bounds access
    print(f"\n📊 Domain Bounds Dictionary:")
    for key, value in DOMAIN_BOUNDS.items():
        print(f"   {key.capitalize()}: {value}")
    
    # Test domain string format
    print(f"\n🔤 Domain String Format:")
    print(f"   {get_domain_string()}")
    
    # Validate domain coordinates
    north, west, south, east = DOMAIN_COORDINATES
    print(f"\n✅ Domain Validation:")
    print(f"   ✓ North ({north}) > South ({south}): {north > south}")
    print(f"   ✓ East ({east}) > West ({west}): {east > west}")
    print(f"   ✓ Valid latitude range: {0 <= south <= 90 and 0 <= north <= 90}")
    print(f"   ✓ Valid longitude range: {90 <= west <= 180 and 90 <= east <= 180}")
    
    print(f"\n🎯 Target Region: {DOMAIN_NAME}")
    print(f"   Covers Malaysian territory and surrounding areas")
    print(f"   Includes Peninsular Malaysia, Sabah, Sarawak, and maritime zones")

if __name__ == "__main__":
    test_domain_configuration()