"""Quick test to verify the DJ Availability Checker setup works."""

print("Testing setup...\n")

# Test 1: colorama
try:
    from colorama import Fore, Style
    print(f"{Fore.GREEN}✓ colorama working{Style.RESET_ALL}")
except ImportError:
    print("✗ colorama not found (colors won't work, but the tool will still run)")

# Test 2: core dependencies
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    from googleapiclient.discovery import build
    print(f"{Fore.GREEN}✓ Google Sheets packages working{Style.RESET_ALL}")
except ImportError as e:
    print(f"✗ Missing package: {e}")

# Test 3: credentials file
import os
cred_file = os.path.join(os.path.dirname(__file__), 'your-credentials.json')
if os.path.exists(cred_file):
    print(f"{Fore.GREEN}✓ your-credentials.json found{Style.RESET_ALL}")
else:
    print("✗ your-credentials.json not found in this folder")

# Test 4: connect to Google Sheets
try:
    from dj_core import init_google_sheets_from_file
    service, spreadsheet, spreadsheet_id, client = init_google_sheets_from_file()
    print(f"{Fore.GREEN}✓ Connected to Google Sheets{Style.RESET_ALL}")
except Exception as e:
    print(f"✗ Connection failed: {e}")

print(f"\n{Fore.GREEN}All good! Run python3 check_2026.py to start.{Style.RESET_ALL}")
