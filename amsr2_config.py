#!/usr/bin/env python3
"""
AMSR-2 Configuration Module
Centralized configuration for domain settings and other parameters
"""

# Domain configuration for Malaysia region
# Format: [North, West, South, East] in decimal degrees
DOMAIN_COORDINATES = [7.8, 99.3, 0.6, 119.8]
DOMAIN_NAME = "Malaysia"

# Domain coordinate names for clarity
DOMAIN_BOUNDS = {
    'north': DOMAIN_COORDINATES[0],
    'west': DOMAIN_COORDINATES[1],
    'south': DOMAIN_COORDINATES[2],
    'east': DOMAIN_COORDINATES[3]
}

# Data products configuration
FREQUENCIES = ['06GHz', '10GHz', '18GHz', '23GHz', '36GHz', '89GHz']
BASE_PATH = '/AMSR2/L3/L3TB'
RESOLUTION = '0.1deg'

# G-Portal credentials
GPORTAL_HOST = 'ftp.gportal.jaxa.jp'
GPORTAL_PORT = 2051
GPORTAL_USER = 'aizat'
GPORTAL_PASS = 'Aiz@t.900627'

# Local storage
LOCAL_BASE_DIR = '/mnt/AizatDrive/amsr2_data'
MAX_WORKERS = 4  # Number of concurrent downloads

# Data range
START_YEAR = 2020
END_YEAR = 2024


def display_domain_info():
    """Display information about the configured domain."""
    north, west, south, east = DOMAIN_COORDINATES
    print(f"\n📍 Domain Configuration: {DOMAIN_NAME}")
    print(f"   North: {north}°N")
    print(f"   West:  {west}°E")
    print(f"   South: {south}°N")
    print(f"   East:  {east}°E")
    print(f"   Coverage: {north-south:.1f}°N-S, {east-west:.1f}°E-W")
    print(f"   Area: {(north-south) * (east-west):.1f} square degrees")


def get_domain_string():
    """Get a string representation of the domain bounds."""
    return f"{DOMAIN_COORDINATES[0]}N,{DOMAIN_COORDINATES[1]}E,{DOMAIN_COORDINATES[2]}N,{DOMAIN_COORDINATES[3]}E"


if __name__ == "__main__":
    display_domain_info()
    print(f"\nDomain String: {get_domain_string()}")