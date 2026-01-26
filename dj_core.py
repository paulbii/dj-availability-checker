"""
DJ Availability Checker - Core Logic Module
This module contains all the booking rules and availability logic.
Shared by both terminal and Streamlit interfaces.
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import calendar
from googleapiclient.discovery import build
import requests
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

# Global variable to track when cache was first populated
_cache_first_used = None
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

# Global variables and setup
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_ID = '1lXwHECkQJy7h87L5oKbo0hDTpalDgKFTbBQJ4pIerFo'
INQUIRIES_SPREADSHEET_ID = '1ng-OytB9LJ8Fmfazju4cfFJRRa6bqfRIZA8GYEWhJRs'
INQUIRIES_SHEET_NAME = 'Form Responses 1'

# Gig Database API
GIG_DATABASE_URL = 'https://database.bigfundj.com/bigfunadmin/availabilityjson.php'

# Year-specific column definitions
COLUMNS_2025 = {
    "A": "Date",
    "D": "Henry",
    "E": "Woody",
    "F": "Paul",
    "G": "Stefano",
    "H": "Felipe",
    "I": "TBA",
    "K": "Stephanie"
}

COLUMNS_2026 = {
    "A": "Date",
    "D": "Henry",
    "E": "Woody",
    "F": "Paul",
    "G": "Stefano",
    "H": "Felipe",
    "I": "TBA",
    "K": "Stephanie",
    "L": "AAG"
}

COLUMNS_2027 = {
    "A": "Date",
    "D": "Henry",
    "E": "Woody",
    "F": "Paul",
    "G": "Stefano",
    "H": "Stephanie",
    "I": "TBA",
    "J": "AAG",
    "L": "Felipe"
}

# DJ name mapping (API full names to short names used in app)
DJ_NAME_MAP = {
    "henry": "Henry",
    "paul": "Paul",
    "stefano": "Stefano",
    "woody": "Woody",
    "felipe": "Felipe",
    "stephanie": "Stephanie"
}


def get_columns_for_year(year):
    """Get the appropriate column mapping for the given year"""
    if year == "2027":
        return COLUMNS_2027
    elif year == "2026":
        return COLUMNS_2026
    else:
        return COLUMNS_2025


def get_fully_booked_dates(year, service, spreadsheet, spreadsheet_id, start_date=None, end_date=None):
    """
    Get all dates with zero available spots (fully booked).
    Optimized to avoid rate limits by fetching all data in bulk.
    
    Args:
        year: Sheet name (e.g., "2026", "2027")
        service: Google Sheets API service
        spreadsheet: Spreadsheet object
        spreadsheet_id: ID of the spreadsheet
        start_date: Optional datetime to filter from (inclusive)
        end_date: Optional datetime to filter to (inclusive)
    
    Returns:
        List of dicts with date info and booking details for fully booked dates
    """
    # Use the bulk fetch function
    all_data = get_bulk_availability_data(year, service, spreadsheet, spreadsheet_id, start_date, end_date)
    
    if all_data is None:
        return None
    
    # Filter for fully booked dates only
    fully_booked = []
    for date_info in all_data:
        if date_info['availability']['available_spots'] == 0:
            fully_booked.append(date_info)
    
    return fully_booked


def get_bulk_availability_data(year, service, spreadsheet, spreadsheet_id, start_date=None, end_date=None):
    """
    Fetch all availability data in bulk (2 API calls total).
    This is the optimized function that avoids rate limits.
    
    Args:
        year: Sheet name (e.g., "2026", "2027")
        service: Google Sheets API service
        spreadsheet: Spreadsheet object
        spreadsheet_id: ID of the spreadsheet
        start_date: Optional datetime to filter from (inclusive)
        end_date: Optional datetime to filter to (inclusive)
    
    Returns:
        List of dicts with full date info and availability for all dates in range
    """
    try:
        sheet = spreadsheet.worksheet(year)
        columns = get_columns_for_year(year)
        
        # Determine the range to fetch based on column letters
        max_col = max(columns.keys())
        range_no_sheet = f"A2:{max_col}400"  # Range without sheet name for worksheet.get()
        range_with_sheet = f"{year}!A2:{max_col}400"  # Range with sheet name for service API
        
        # Fetch all values in ONE API call
        all_values = sheet.get(range_no_sheet)
        
        # Fetch all formatting in ONE API call
        request = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            ranges=range_with_sheet,
            includeGridData=True
        )
        response = request.execute()
        
        # Extract formatting data
        formatting_data = []
        if 'sheets' in response and len(response['sheets']) > 0:
            if 'data' in response['sheets'][0] and len(response['sheets'][0]['data']) > 0:
                if 'rowData' in response['sheets'][0]['data'][0]:
                    formatting_data = response['sheets'][0]['data'][0]['rowData']
        
        # Get column indices
        column_indices = {label: ord(col) - ord('A') for col, label in columns.items()}
        
        # Process each row
        all_dates = []
        
        for row_idx, row_values in enumerate(all_values):
            # Skip empty rows or rows without a date
            if not row_values or len(row_values) == 0:
                continue
            
            date_str = row_values[0] if len(row_values) > 0 else ""
            if not date_str:
                continue
            
            # Parse the date
            try:
                # Date format is like "Sat 1/4" - need to add the year
                full_date_str = f"{year}-{date_str.split()[-1]}"  # Get "1/4" part
                date_obj = datetime.strptime(full_date_str, "%Y-%m/%d")
            except (ValueError, IndexError):
                continue
            
            # Apply date filters if provided
            if start_date and date_obj < start_date:
                continue
            if end_date and date_obj > end_date:
                continue
            
            # Build selected_data dict for this row
            selected_data = {}
            bold_status = {}
            
            for label, index in column_indices.items():
                if index < len(row_values):
                    cell_value = row_values[index]
                    is_bold = False
                    
                    # Check formatting if available
                    if row_idx < len(formatting_data):
                        row_format = formatting_data[row_idx].get('values', [])
                        if index < len(row_format):
                            cell_format = row_format[index]
                            if 'effectiveFormat' in cell_format:
                                is_bold = cell_format['effectiveFormat'].get('textFormat', {}).get('bold', False)
                            if 'textFormatRuns' in cell_format:
                                is_bold = is_bold or any(
                                    run.get('format', {}).get('bold', False) 
                                    for run in cell_format['textFormatRuns']
                                )
                    
                    bold_status[label] = is_bold
                    if is_bold and label != "Date":
                        selected_data[label] = f"{cell_value} (BOLD)"
                    else:
                        selected_data[label] = cell_value
                else:
                    selected_data[label] = ""
                    bold_status[label] = False
            
            # Analyze availability for this date
            availability = analyze_availability(selected_data, date_obj, year)
            
            # Build detailed DJ status lists
            booked_djs = []
            backup_assigned = []
            available_to_book = []
            available_to_backup = []
            
            # List of actual DJs (exclude Date, TBA, AAG)
            dj_names = ["Henry", "Woody", "Paul", "Stefano", "Felipe", "Stephanie"]
            
            for dj_name in dj_names:
                if dj_name not in selected_data:
                    continue
                
                value = selected_data.get(dj_name, "")
                value_str = str(value).replace(" (BOLD)", "") if value else ""
                value_lower = value_str.lower()
                is_bold = bold_status.get(dj_name, False)
                
                if value_lower == "booked":
                    booked_djs.append(dj_name)
                elif value_lower == "backup":
                    backup_assigned.append(dj_name)
                elif value_lower == "reserved":
                    # Stephanie can have RESERVED status
                    booked_djs.append(f"{dj_name} (RESERVED)")
                else:
                    # Special case: Stefano with blank cell = MAYBE (not in system but potentially available)
                    if dj_name == "Stefano" and (not value_str or value_str.strip() == ""):
                        available_to_book.append(f"{dj_name} [MAYBE]")
                        continue
                    
                    # Check availability using existing logic
                    can_book, can_backup = check_dj_availability(dj_name, value_str, date_obj, is_bold, year)
                    if can_book:
                        available_to_book.append(dj_name)
                    elif can_backup:
                        available_to_backup.append(dj_name)
            
            # Get AAG status
            aag_status = selected_data.get("AAG", "")
            
            all_dates.append({
                'date': date_str,
                'date_obj': date_obj,
                'selected_data': selected_data,
                'bold_status': bold_status,
                'booked_djs': booked_djs,
                'backup_assigned': backup_assigned,
                'available_to_book': available_to_book,
                'available_to_backup': available_to_backup,
                'availability': availability,
                'aag_status': aag_status,
                'aag_reserved': availability.get('aag_reserved', False)
            })
        
        return all_dates
        
    except gspread.exceptions.WorksheetNotFound:
        return None
    except Exception as e:
        print(f"Error fetching bulk availability data: {e}")
        return None


def init_google_sheets_from_file(credentials_file='your-credentials.json'):
    """Initialize Google Sheets connection from credentials file"""
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, SCOPE)
    client = gspread.authorize(creds)
    service = build('sheets', 'v4', credentials=creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return service, spreadsheet, SPREADSHEET_ID, client


def init_google_sheets_from_dict(credentials_dict):
    """Initialize Google Sheets connection from credentials dictionary (for Streamlit secrets)"""
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, SCOPE)
    client = gspread.authorize(creds)
    service = build('sheets', 'v4', credentials=creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return service, spreadsheet, SPREADSHEET_ID, client


def get_column_indices(column_letters):
    """Convert column letters to zero-based indices"""
    return {label: ord(col) - ord('A') for col, label in column_letters.items()}


def is_weekend(date_obj):
    """Check if date is a weekend"""
    return date_obj.weekday() >= 5


def get_gig_database_bookings(year, month_day):
    """
    Query the gig database API for bookings on a specific date.
    
    Args:
        year: Year string (e.g., "2026")
        month_day: Date in MM-DD format (e.g., "03-21")
    
    Returns:
        dict with two keys:
        - 'assigned': dict mapping DJ short names to booking info
          {"Paul": {"venue": "Nestldown", "client": "Smith/Jones"}, ...}
        - 'unassigned': list of unassigned (TBA) bookings
          [{"venue": "Kohl Mansion", "client": "Client Name"}, ...]
        Returns {'assigned': {}, 'unassigned': []} if API fails or no bookings.
    """
    try:
        # Construct date in m/d/yyyy format for the API
        month, day = month_day.split('-')
        date_str = f"{int(month)}/{int(day)}/{year}"
        
        url = f"{GIG_DATABASE_URL}?date={date_str}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            return {'assigned': {}, 'unassigned': []}
        
        bookings = response.json()
        
        if not bookings:  # Empty array
            return {'assigned': {}, 'unassigned': []}
        
        # Map API results to short DJ names
        assigned = {}
        unassigned = []
        
        for booking in bookings:
            full_name = booking.get('assigned_dj', '')
            venue = booking.get('venue_name', '')
            client = booking.get('client_name', '')
            
            # Check for unassigned bookings
            if full_name.lower() == 'unassigned':
                unassigned.append({
                    'venue': venue,
                    'client': client
                })
            else:
                # Extract first name and map to short name
                first_name = full_name.split()[0].lower() if full_name else ''
                short_name = DJ_NAME_MAP.get(first_name)
                
                if short_name:
                    assigned[short_name] = {
                        'venue': venue,
                        'client': client
                    }
        
        return {'assigned': assigned, 'unassigned': unassigned}
        
    except Exception:
        # If anything fails, return empty dict (fall back to matrix-only)
        return {'assigned': {}, 'unassigned': []}


@lru_cache(maxsize=100)
def get_gig_database_bookings_cached(year, month_day, cache_time):
    """
    Cached version of get_gig_database_bookings.
    Cache expires every hour (when cache_time changes).
    
    Args:
        year: Year string
        month_day: Date in MM-DD format
        cache_time: Current hour in format "YYYY-MM-DD-HH" (used for cache expiration)
    
    Returns:
        Same as get_gig_database_bookings
    """
    global _cache_first_used
    
    # Track when cache was first populated this session
    if _cache_first_used is None:
        _cache_first_used = datetime.now()
    
    return get_gig_database_bookings(year, month_day)


def get_cache_time():
    """Get current cache time key (hour-based)"""
    return datetime.now().strftime("%Y-%m-%d-%H")


def get_cache_info():
    """Get cache statistics for display"""
    cache_info = get_gig_database_bookings_cached.cache_info()
    current_time = datetime.now()
    
    # If no cache hits yet, data is fresh
    if cache_info.hits == 0 or _cache_first_used is None:
        return {
            'hits': 0,
            'misses': cache_info.misses,
            'size': cache_info.currsize,
            'age_minutes': 0,
            'cache_time': 'Just now',
            'is_fresh': True
        }
    
    # Calculate actual age from when cache was first used
    age_seconds = (current_time - _cache_first_used).total_seconds()
    age_minutes = int(age_seconds / 60)
    cache_time_str = _cache_first_used.strftime("%I:%M %p").lstrip('0')
    
    return {
        'hits': cache_info.hits,
        'misses': cache_info.misses,
        'size': cache_info.currsize,
        'age_minutes': age_minutes,
        'cache_time': cache_time_str,
        'is_fresh': age_minutes < 5
    }


def clear_gig_cache():
    """Clear the gig database cache (force refresh)"""
    global _cache_first_used
    _cache_first_used = None
    get_gig_database_bookings_cached.cache_clear()


def auto_clear_stale_cache(max_age_minutes=60):
    """
    Automatically clear cache if it's older than max_age_minutes.
    Call this at the start of operations to ensure fresh data.
    Returns True if cache was cleared, False otherwise.
    """
    global _cache_first_used
    
    if _cache_first_used is None:
        return False
    
    age_seconds = (datetime.now() - _cache_first_used).total_seconds()
    age_minutes = age_seconds / 60
    
    if age_minutes > max_age_minutes:
        clear_gig_cache()
        return True
    
    return False


def check_dj_availability(dj_name, value, date_obj=None, is_bold=False, year=None):
    """
    Check if a DJ is available based on their current status
    Returns: (can_be_booked, can_be_backup)
    
    Args:
        dj_name: Name of the DJ
        value: Cell value from spreadsheet
        date_obj: Date object for the event
        is_bold: Whether the cell text is bold
        year: The year being checked (e.g., "2025", "2026", "2027") for year-specific rules
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
    
    # Special case for Stephanie 2026 - only available when explicitly assigned
    if dj_name == "Stephanie" and year == "2026":
        if not value:  # Blank cell in 2026
            return False, False  # NOT available (only works when explicitly assigned)
        # For non-blank values, continue to normal processing below
    
    # Special case for Stephanie on weekdays (2027+)
    if dj_name == "Stephanie" and year == "2027" and not is_weekend_day:
        if not value:  # Blank cell on weekday
            return False, False  # NOT available on weekdays
        if value_lower == "out":
            return False, False  # Normal OUT rules apply
    
    if value_lower == "booked" or value_lower == "backup":
        return False, False
    
    # Handle RESERVED status (AAG events)
    if value_lower == "reserved":
        return False, False  # Treated as booked
    
    # Special handling for Felipe in 2026 and 2027
    if dj_name == "Felipe" and year in ["2026", "2027"]:
        if not value:  # Empty cell in 2026/2027
            return False, True  # Available for backup only (default)
        if value_lower == "ok":
            return True, True  # Special exception - can be booked AND backup
        if value_lower == "dad" or value_lower == "ok to backup":
            return False, True  # Available for backup only
        if value_lower == "out" or value_lower == "maxed":
            return False, False  # Not available at all
        # Any other status - default to backup only
        return False, True
        
    if not value:  # Blank cell (for non-2026/2027 Felipe cases)
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
    aag_reserved = False
    
    # First pass: count actual bookings, TBA, and check AAG RESERVED
    for name, value in selected_data.items():
        if name == "Date":  # Skip Date only
            continue
            
        value = str(value).replace(" (BOLD)", "") if value else ""
        value_lower = value.lower()
        
        # Check AAG column for RESERVED (2026/2027) - just sets flag, doesn't count as booking yet
        if name == "AAG" and "reserved" in value_lower:
            aag_reserved = True
            continue
        
        # Check Stephanie RESERVED (counts as booking in 2026/2027 - she's unavailable)
        if name == "Stephanie" and "reserved" in value_lower:
            booked_count += 1
            continue
        
        if name == "TBA" and ("booked" in value_lower or "aag" in value_lower):
            # Split by comma to handle multiple entries like "BOOKED, AAG"
            entries = [entry.strip() for entry in value.split(',')]
            
            for entry in entries:
                entry_lower = entry.lower()
                
                if "booked" in entry_lower:
                    # Check for multiplier in format "BOOKED x N" or "BOOKED X N"
                    if "x" in entry_lower:
                        try:
                            # Extract the number after "x" or "X"
                            multiplier = int(entry_lower.split("x")[1].strip())
                            tba_bookings += multiplier
                            booked_count += multiplier
                        except (ValueError, IndexError):
                            # If parsing fails, assume single booking
                            tba_bookings += 1
                            booked_count += 1
                    else:
                        tba_bookings += 1
                        booked_count += 1
                
                elif "aag" in entry_lower:
                    # AAG counts as one booking
                    tba_bookings += 1
                    booked_count += 1
            
            continue
            
        if value_lower == "booked" or "aag" in value_lower:
            booked_count += 1
    
    # Second pass: analyze availability
    for name, value in selected_data.items():
        if name in ["Date", "TBA", "AAG", "Stephanie"]:  # Skip Date, TBA, AAG (not DJs), and Stephanie
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
    
    # Subtract AAG RESERVED spot (2027+)
    if aag_reserved:
        available_spots = max(0, available_spots - 1)
        
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
        'backup_count': backup_count,
        'aag_reserved': aag_reserved
    }


def get_date_availability_data(sheet_name, month_day, service, spreadsheet, spreadsheet_id):
    """
    Get availability data for a specific date
    Returns: 
        - dict with date info and availability if found
        - {'error': 'invalid_format'} if date format is invalid
        - {'error': 'not_found', 'formatted_date': 'Mon 1/1'} if valid format but no data
    """
    # Auto-clear stale gig database cache (older than 60 minutes)
    auto_clear_stale_cache(60)
    
    try:
        # Get appropriate columns for the year
        columns_to_return = get_columns_for_year(sheet_name)
        
        sheet = spreadsheet.worksheet(sheet_name)
        dates = [date.strip() for date in sheet.col_values(1)]

        try:
            full_date_str = f"{sheet_name}-{month_day}"
            date_obj = datetime.strptime(full_date_str, "%Y-%m-%d")
            formatted_date = f"{calendar.day_name[date_obj.weekday()][:3]} {date_obj.month}/{date_obj.day}"
        except ValueError:
            return {'error': 'invalid_format'}

        if formatted_date in dates:
            row_number = dates.index(formatted_date) + 1
            row_contents = sheet.row_values(row_number)

            # Determine range based on year
            if sheet_name == "2027":
                range_notation = f"{sheet_name}!A{row_number}:L{row_number}"
            elif sheet_name == "2026":
                range_notation = f"{sheet_name}!A{row_number}:L{row_number}"
            else:
                range_notation = f"{sheet_name}!A{row_number}:K{row_number}"
                
            # Get formatting details
            request = service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                ranges=range_notation,
                includeGridData=True
            )
            response = request.execute()
            row_data = response['sheets'][0]['data'][0]['rowData'][0]['values']

            column_indices = get_column_indices(columns_to_return)
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
            
            # Get gig database bookings (using cached version)
            cache_time = get_cache_time()
            gig_bookings = get_gig_database_bookings_cached(sheet_name, month_day, cache_time)
            
            return {
                'date_obj': date_obj,
                'formatted_date': formatted_date,
                'selected_data': selected_data,
                'availability': availability,
                'gig_bookings': gig_bookings
            }
        else:
            return {'error': 'not_found', 'formatted_date': formatted_date}
    except gspread.exceptions.WorksheetNotFound:
        return {'error': 'worksheet_not_found'}


def get_venue_inquiries_for_date(event_date_str, client):
    """
    Get venue inquiry information for a specific date
    
    Args:
        event_date_str: Date string in format like "Fri 1/3" or "1/3/2026"
        client: Authorized gspread client
    
    Returns:
        dict with 'booked' and 'not_booked' lists of venues
    """
    try:
        # Open the inquiries sheet
        inquiries_spreadsheet = client.open_by_key(INQUIRIES_SPREADSHEET_ID)
        inquiries_sheet = inquiries_spreadsheet.worksheet(INQUIRIES_SHEET_NAME)
        
        # Get all data
        all_data = inquiries_sheet.get_all_records()
        
        # Parse target date from event_date_str
        # Could be "Fri 1/3" or "Fri 5/16" format - extract just the date part
        if ' ' in event_date_str:
            date_part = event_date_str.split(' ')[1]  # Get "5/16" from "Fri 5/16"
        else:
            date_part = event_date_str
        
        month_day_parts = date_part.split('/')
        if len(month_day_parts) != 2:
            return {'booked': [], 'not_booked': []}
        
        target_month = int(month_day_parts[0])
        target_day = int(month_day_parts[1])
        
        # Group by venue and keep most recent decision date
        venue_data = {}  # venue -> (resolution, decision_date)
        
        for row in all_data:
            event_date = row.get('Event Date', '').strip()
            if not event_date:
                continue
            
            try:
                # Parse the event date from the sheet
                # Try multiple formats
                parsed_event = None
                for fmt in ["%m/%d/%Y", "%-m/%-d/%Y", "%m/%d/%y", "%-m/%-d/%y"]:
                    try:
                        parsed_event = datetime.strptime(event_date, fmt)
                        break
                    except ValueError:
                        continue
                
                if not parsed_event:
                    continue
                
                # Check if this row matches our target date (month and day only)
                if (parsed_event.month, parsed_event.day) == (target_month, target_day):
                    venue = row.get('Venue (if known)', '').strip()
                    resolution = row.get('Resolution', '').strip()
                    decision_date_str = row.get('Decision Date', '').strip()
                    
                    # Skip if no venue
                    if not venue:
                        continue
                    
                    # Parse decision date
                    decision_date = None
                    for fmt in ["%m/%d/%Y", "%-m/%-d/%Y", "%m/%d/%y", "%-m/%-d/%y"]:
                        try:
                            decision_date = datetime.strptime(decision_date_str, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if not decision_date:
                        decision_date = datetime.min
                    
                    # Check if we should use this entry
                    if venue not in venue_data:
                        venue_data[venue] = (resolution, decision_date)
                    else:
                        # Keep the one with more recent decision date
                        existing_resolution, existing_date = venue_data[venue]
                        if decision_date > existing_date:
                            venue_data[venue] = (resolution, decision_date)
            
            except (ValueError, AttributeError):
                continue
        
        # Organize results
        booked_venues = []
        not_booked_venues = []
        
        for venue, (resolution, _) in venue_data.items():
            if resolution == "Booked":
                booked_venues.append(venue)
            else:
                not_booked_venues.append(f"{venue} ({resolution})")
        
        return {
            'booked': sorted(booked_venues),
            'not_booked': sorted(not_booked_venues)
        }
        
    except Exception as e:
        # If anything goes wrong, return empty results
        return {
            'booked': [],
            'not_booked': [],
            'error': str(e)
        }


def get_nearby_bookings_for_dj(dj_name, date_obj, year, service, spreadsheet, spreadsheet_id):
    """
    Get nearby bookings for a DJ (3 days before and after the target date)
    Uses parallel requests and caching for improved performance.
    
    Args:
        dj_name: Name of the DJ
        date_obj: The target date object
        year: The year being checked (stays within this year only)
        service: Google Sheets API service
        spreadsheet: The spreadsheet object
        spreadsheet_id: The spreadsheet ID
    
    Returns:
        List of formatted date strings where DJ is booked nearby (e.g., ["Thu 1/15", "Sun 1/18"])
    """
    nearby_bookings = []
    cache_time = get_cache_time()  # Get current hour for cache key
    
    # Prepare all dates to check
    dates_to_check = []
    for offset in [-3, -2, -1, 1, 2, 3]:
        check_date = date_obj + timedelta(days=offset)
        
        # Skip if outside the current year
        if check_date.year != int(year):
            continue
        
        dates_to_check.append((offset, check_date))
    
    # Function to check one date
    def check_date_for_dj(date_info):
        offset, check_date = date_info
        month_day = check_date.strftime("%m-%d")
        
        # Use cached version
        gig_bookings = get_gig_database_bookings_cached(year, month_day, cache_time)
        
        if dj_name in gig_bookings.get('assigned', {}):
            # Format as "Day M/D"
            formatted = f"{calendar.day_name[check_date.weekday()][:3]} {check_date.month}/{check_date.day}"
            return (offset, formatted)  # Return offset for sorting
        return None
    
    # Execute requests in parallel (max 6 threads, one per date)
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(check_date_for_dj, d): d for d in dates_to_check}
        
        results = []
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
        
        # Sort by offset to maintain chronological order
        results.sort(key=lambda x: x[0])
        nearby_bookings = [formatted for offset, formatted in results]
    
    return nearby_bookings
