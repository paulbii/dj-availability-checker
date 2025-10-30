"""
DJ Availability Checker - Core Logic Module
This module contains all the booking rules and availability logic.
Shared by both terminal and Streamlit interfaces.
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import calendar
from googleapiclient.discovery import build

# Global variables and setup
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_ID = '1lXwHECkQJy7h87L5oKbo0hDTpalDgKFTbBQJ4pIerFo'

# Column definitions
COLUMNS_TO_RETURN = {
    "A": "Date",
    "D": "Henry",
    "E": "Woody",
    "F": "Paul",
    "G": "Stefano",
    "H": "Felipe",
    "I": "TBA",
    "K": "Stephanie"
}


def init_google_sheets_from_file(credentials_file='your-credentials.json'):
    """Initialize Google Sheets connection from credentials file"""
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, SCOPE)
    client = gspread.authorize(creds)
    service = build('sheets', 'v4', credentials=creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return service, spreadsheet, SPREADSHEET_ID


def init_google_sheets_from_dict(credentials_dict):
    """Initialize Google Sheets connection from credentials dictionary (for Streamlit secrets)"""
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, SCOPE)
    client = gspread.authorize(creds)
    service = build('sheets', 'v4', credentials=creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return service, spreadsheet, SPREADSHEET_ID


def get_column_indices(column_letters):
    """Convert column letters to zero-based indices"""
    return {label: ord(col) - ord('A') for col, label in column_letters.items()}


def is_weekend(date_obj):
    """Check if date is a weekend"""
    return date_obj.weekday() >= 5


def check_dj_availability(dj_name, value, date_obj=None, is_bold=False, year=None):
    """
    Check if a DJ is available based on their current status
    Returns: (can_be_booked, can_be_backup)
    
    Args:
        dj_name: Name of the DJ
        value: Cell value from spreadsheet
        date_obj: Date object for the event
        is_bold: Whether the cell text is bold
        year: The year being checked (e.g., "2025", "2026") for year-specific rules
    """
    value = str(value).strip() if value else ""
    value_lower = value.lower()
    is_weekend_day = date_obj and date_obj.weekday() >= 5 if date_obj else False
    
    # Special case for Henry on weekdays
    if dj_name == "Henry" and not is_weekend_day:
        if not value:  # Blank cell on weekday
            return False, True  # Can only be backup on weekdays
        if value_lower == "out":
            return False, False  # Normal OUT rules apply
    
    if value_lower == "booked" or value_lower == "backup":
        return False, False
    
    # Special handling for Felipe in 2026
    if dj_name == "Felipe" and year == "2026":
        if not value:  # Empty cell in 2026
            return False, False  # Not available for booking or backup
        if value_lower == "dad" or value_lower == "ok to backup":
            return False, True  # Available for backup only
        if value_lower == "out" or value_lower == "maxed":
            return False, False
        # Any other explicit status for Felipe in 2026 should be evaluated
        # but he's never available for booking in 2026
        return False, False
        
    if not value:  # Blank cell (for non-2026 Felipe cases)
        if dj_name == "Stefano":
            return False, False
        return True, True
        
    if value_lower == "out" or value_lower == "maxed":
        if dj_name == "Woody" and is_weekend_day and not is_bold:
            return False, True  # Can be backup on weekends if not bold
        return False, False
        
    if value_lower == "ok to backup":
        return False, True
        
    if value_lower == "ok":  # Handle both "ok" and "OK"
        return True, True
        
    if dj_name == "Felipe" and value_lower == "dad":
        return False, True
        
    if dj_name == "Stefano" and value_lower == "ok":
        return True, True
        
    # Handle LAST status - available but should be assigned last
    if value_lower == "last":
        return True, True
        
    return False, False


def analyze_availability(selected_data, date_obj, year=None):
    """Analyze the availability status of all DJs"""
    booked_count = 0
    backup_count = 0
    available_for_booking = []
    available_for_backup = []
    tba_bookings = 0
    
    # First pass: count actual bookings and TBA
    for name, value in selected_data.items():
        if name in ["Date", "Stephanie"]:  # Skip Date and Stephanie
            continue
            
        value = str(value).replace(" (BOLD)", "") if value else ""
        value_lower = value.lower()
        
        if name == "TBA" and "booked" in value_lower:
            # Check for multiple bookings in format "BOOKED x N" or "BOOKED X N"
            if "x" in value_lower:
                try:
                    # Extract the number after "x" or "X"
                    multiplier = int(value_lower.split("x")[1].strip())
                    tba_bookings += multiplier
                    booked_count += multiplier
                except (ValueError, IndexError):
                    # If parsing fails, assume single booking
                    tba_bookings += 1
                    booked_count += 1
            else:
                tba_bookings += 1
                booked_count += 1
            continue
            
        if value_lower == "booked":
            booked_count += 1
    
    # Second pass: analyze availability
    for name, value in selected_data.items():
        if name in ["Date", "TBA", "Stephanie"]:  # Skip Date, TBA (not a DJ), and Stephanie
            continue
            
        is_bold = "(BOLD)" in value if value else False
        value = value.replace(" (BOLD)", "") if value else ""
        value_lower = value.lower()
        
        # Count BACKUP assignments
        if value_lower == "backup":
            backup_count += 1
        # Only check availability for non-booked and non-backup DJs
        elif value_lower != "booked":
            can_book, can_backup = check_dj_availability(name, value, date_obj, is_bold, year)
            if can_book:
                available_for_booking.append(name)
            if can_backup:
                available_for_backup.append(name)
    
    # Calculate available spots
    available_spots = len(available_for_booking)
    
    # Subtract TBA bookings that need to be assigned
    if tba_bookings > 0:
        available_spots = max(0, available_spots - tba_bookings)
        
    # If we have no backup assigned and have available people for backup,
    # we can use the available booking spots
    if backup_count == 0 and len(available_for_backup) == 0:
        available_spots = 0  # No spots available if no one can be backup
    
    return {
        'booked_count': booked_count,  # This now includes TBA BOOKED
        'available_spots': available_spots,
        'available_booking': available_for_booking,
        'available_backup': available_for_backup,
        'tba_bookings': tba_bookings,
        'backup_count': backup_count
    }


def get_date_availability_data(sheet_name, month_day, service, spreadsheet, spreadsheet_id):
    """
    Get availability data for a specific date
    Returns: dict with date info and availability, or None if date not found
    """
    try:
        sheet = spreadsheet.worksheet(sheet_name)
        dates = [date.strip() for date in sheet.col_values(1)]

        try:
            full_date_str = f"{sheet_name}-{month_day}"
            date_obj = datetime.strptime(full_date_str, "%Y-%m-%d")
            formatted_date = f"{calendar.day_name[date_obj.weekday()][:3]} {date_obj.month}/{date_obj.day}"
        except ValueError:
            return None

        if formatted_date in dates:
            row_number = dates.index(formatted_date) + 1
            row_contents = sheet.row_values(row_number)

            # Get formatting details
            range_notation = f"{sheet_name}!A{row_number}:K{row_number}"
            request = service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                ranges=range_notation,
                includeGridData=True
            )
            response = request.execute()
            row_data = response['sheets'][0]['data'][0]['rowData'][0]['values']

            column_indices = get_column_indices(COLUMNS_TO_RETURN)
            selected_data = {}

            for label, index in column_indices.items():
                if index < len(row_contents):
                    cell_value = row_contents[index]
                    is_bold = False
                    
                    if 'effectiveFormat' in row_data[index]:
                        is_bold = row_data[index]['effectiveFormat']['textFormat'].get('bold', False)
                    
                    if 'textFormatRuns' in row_data[index]:
                        is_bold = any(run.get('format', {}).get('bold', False) 
                                    for run in row_data[index]['textFormatRuns'])

                    if is_bold and label != "Date":
                        selected_data[label] = f"{cell_value} (BOLD)"
                    else:
                        selected_data[label] = cell_value

            # Analyze availability
            availability = analyze_availability(selected_data, date_obj, sheet_name)
            
            return {
                'date_obj': date_obj,
                'formatted_date': formatted_date,
                'selected_data': selected_data,
                'availability': availability
            }
        else:
            return None
    except gspread.exceptions.WorksheetNotFound:
        return None
