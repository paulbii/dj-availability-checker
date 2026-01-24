"""
DJ Availability Checker - Terminal Interface for 2026
Imports core logic from dj_core.py
"""

# Add path to colorama package
import sys
sys.path.append('/Users/paulburchfield/miniconda3/lib/python3.12/site-packages')

# Now import colorama
try:
    from colorama import init, Fore, Style, Back
    init(autoreset=True)
except ImportError:
    class DummyColors:
        def __init__(self):
            self.GREEN = ''
            self.YELLOW = ''
            self.BLUE = ''
            self.RED = ''
            self.RESET_ALL = ''
            self.BRIGHT = ''
    
    Fore = DummyColors()
    Style = DummyColors()
    Back = DummyColors()

from datetime import datetime, timedelta
import calendar

# Import core functionality
from dj_core import (
    init_google_sheets_from_file,
    get_date_availability_data,
    get_venue_inquiries_for_date,
    get_nearby_bookings_for_dj,
    check_dj_availability,
    is_weekend,
    get_cache_info,
    clear_gig_cache
)


def format_dj_status(dj_name, value, date_obj, is_bookable, is_backup, year=None, nearby_bookings=None, gig_booking=None):
    """Format a DJ's status line with appropriate colors and indicators"""
    
    # If we have gig database info for this DJ, they're booked - show venue
    if gig_booking:
        venue = gig_booking.get('venue', '')
        return f"{Fore.RED}{dj_name}: BOOKED ({venue}){Style.RESET_ALL}"
    
    if dj_name == "Stefano" and (not value or value.strip() == ""):
        return f"{Fore.YELLOW}{dj_name}: [MAYBE]{Style.RESET_ALL}"
    
    value_lower = value.lower() if value else ""
    if value and "booked" in value_lower:
        return f"{Fore.RED}{dj_name}: {value}{Style.RESET_ALL}"
    
    if value and "backup" in value_lower:
        return f"{Fore.BLUE}{dj_name}: {value}{Style.RESET_ALL}"
    
    if dj_name == "Felipe" and year == "2026" and (not value or value.strip() == ""):
        return f"{Fore.BLUE}{dj_name}: [BLANK] - can backup{Style.RESET_ALL}"
    
    if value and value_lower == "last":
        return f"{Fore.GREEN}{dj_name}: {value} - available (low priority){Style.RESET_ALL}"
    
    # Format nearby bookings if available
    nearby_text = ""
    if nearby_bookings and len(nearby_bookings) > 0:
        nearby_text = f" (booked: {', '.join(nearby_bookings)})"
    
    if is_bookable:
        return f"{Fore.GREEN}{dj_name}: {value} - available{nearby_text}{Style.RESET_ALL}"
    
    if is_backup:
        backup_reason = ""
        if dj_name == "Woody" and "out" in value_lower and is_weekend(date_obj):
            backup_reason = " (weekend)"
        elif dj_name == "Henry" and not is_weekend(date_obj) and (not value or value.strip() == ""):
            backup_reason = " (weekday)"
        elif dj_name == "Felipe" and ("dad" in value_lower or "ok to backup" in value_lower):
            backup_reason = ""
        
        return f"{Fore.BLUE}{dj_name}: {value} - can backup{backup_reason}{Style.RESET_ALL}"
    
    return f"{dj_name}: {value}"


def check_availability(sheet_name, month_day_to_check, service, spreadsheet, spreadsheet_id, client):
    """Check availability for a specific date"""
    data = get_date_availability_data(sheet_name, month_day_to_check, service, spreadsheet, spreadsheet_id)
    
    # Handle different error types
    if data is None or (isinstance(data, dict) and 'error' in data):
        if data is None:
            return f"{Fore.RED}An unexpected error occurred.{Style.RESET_ALL}"
        if data['error'] == 'invalid_format':
            return f"{Fore.RED}Invalid date format. Please use MM-DD format (e.g., 07-05).{Style.RESET_ALL}"
        elif data['error'] == 'not_found':
            return f"{Fore.YELLOW}No entry found for {data['formatted_date']} in the {sheet_name} availability sheet.{Style.RESET_ALL}"
        elif data['error'] == 'worksheet_not_found':
            return f"{Fore.RED}Error: The {sheet_name} worksheet was not found.{Style.RESET_ALL}"
        else:
            return f"{Fore.RED}An error occurred while checking availability.{Style.RESET_ALL}"
    
    # If we get here, data is valid
    date_obj = data['date_obj']
    selected_data = data['selected_data']
    availability = data['availability']
    gig_bookings = data.get('gig_bookings', {'assigned': {}, 'unassigned': []})
    assigned_bookings = gig_bookings.get('assigned', {})
    unassigned_bookings = gig_bookings.get('unassigned', [])
    
    # Get venue inquiries for this date
    venue_info = get_venue_inquiries_for_date(selected_data['Date'], client)
    
    response = ["\n" + "=" * 50]
    response.append(f"Year: {Back.WHITE}{Fore.BLACK}{Style.BRIGHT}{sheet_name}{Style.RESET_ALL}")
    response.append(f"Date: {selected_data['Date']}")
    
    for label, value in selected_data.items():
        if label != "Date":
            if label == "TBA":
                # Show unassigned bookings from gig database with venue names
                if unassigned_bookings:
                    venues = [b.get('venue', 'Unknown') for b in unassigned_bookings]
                    response.append(f"{Fore.RED}{label}: BOOKED ({', '.join(venues)}){Style.RESET_ALL}")
                elif value and ("booked" in str(value).lower() or "aag" in str(value).lower()):
                    response.append(f"{Fore.RED}{label}: {value}{Style.RESET_ALL}")
                else:
                    response.append(f"{label}: {value}")
            elif label == "AAG":
                # Show AAG RESERVED status (2026+)
                value_lower = str(value).lower()
                if "reserved" in value_lower:
                    response.append(f"{Fore.RED}{label}: {value}{Style.RESET_ALL}")
                elif value:
                    response.append(f"{label}: {value}")
                else:
                    response.append(f"{label}: ")
            elif label == "Stephanie":
                value_lower = str(value).lower()
                # Check if Stephanie has a gig database booking
                steph_booking = assigned_bookings.get("Stephanie")
                if steph_booking:
                    venue = steph_booking.get('venue', '')
                    response.append(f"{Fore.RED}{label}: BOOKED ({venue}){Style.RESET_ALL}")
                elif "booked" in value_lower or "aag" in value_lower:
                    response.append(f"{Fore.RED}{label}: {value}{Style.RESET_ALL}")
                elif "reserved" in value_lower:
                    response.append(f"{Fore.RED}{label}: {value}{Style.RESET_ALL}")
                elif "backup" in value_lower:
                    response.append(f"{Fore.BLUE}{label}: {value}{Style.RESET_ALL}")
                elif not value or value.strip() == "":
                    # Blank Stephanie in 2026 = not available
                    response.append(f"{label}: not available (2026)")
                else:
                    response.append(f"{label}: {value}")
            else:
                # Check if this DJ has a booking in the gig database
                dj_gig_booking = assigned_bookings.get(label)
                
                # Check if this DJ is available for booking or backup
                is_bold = "(BOLD)" in value if value else False
                clean_value = value.replace(" (BOLD)", "") if value else ""
                can_book, can_backup = check_dj_availability(label, clean_value, date_obj, is_bold, sheet_name)
                
                # Get nearby bookings if DJ is available
                nearby_bookings = []
                if can_book and not dj_gig_booking:
                    nearby_bookings = get_nearby_bookings_for_dj(label, date_obj, sheet_name, service, spreadsheet, spreadsheet_id)
                
                # Format the status line with colors and indicators
                formatted_line = format_dj_status(label, value, date_obj, can_book, can_backup, sheet_name, nearby_bookings, dj_gig_booking)
                response.append(formatted_line)
    
    response.append("\nAVAILABILITY SUMMARY:")
    response.append(f"Confirmed bookings: {availability['booked_count']}")
    
    # Show AAG RESERVED if applicable (2026+)
    if availability.get('aag_reserved', False):
        response.append(f"{Fore.YELLOW}AAG Spot Reserved: 1{Style.RESET_ALL}")
    
    available_spots = availability['available_spots']
    
    has_uncertain_stefano = False
    if "Stefano" in selected_data and (not selected_data["Stefano"] or selected_data["Stefano"].strip() == ""):
        has_uncertain_stefano = True
        
    if available_spots <= 2 and available_spots > 0:
        if has_uncertain_stefano:
            asterisk = f"{Fore.YELLOW}*{Style.RESET_ALL}"
            response.append(f"Available spots: {available_spots}{asterisk} ({', '.join(availability['available_booking'])})")
            response.append(f"{Fore.YELLOW}* Availability depends on Stefano's confirmation{Style.RESET_ALL}")
        else:
            response.append(f"Available spots: {available_spots} ({', '.join(availability['available_booking'])})")
    else:
        if has_uncertain_stefano:
            asterisk = f"{Fore.YELLOW}*{Style.RESET_ALL}"
            response.append(f"Available spots: {available_spots}{asterisk}")
            response.append(f"{Fore.YELLOW}* Availability depends on Stefano's confirmation{Style.RESET_ALL}")
        else:
            response.append(f"Available spots: {available_spots}")
    
    # Add venue information - now showing inquiries that didn't book
    # (booked venues now come from gig database via DJ lines above)
    if venue_info and venue_info.get('not_booked'):
        response.append(f"\n{Fore.YELLOW}INQUIRIES (not booked): {', '.join(venue_info['not_booked'])}{Style.RESET_ALL}")
    
    # Show cache info if venue/gig database data was used
    cache_info = get_cache_info()
    if cache_info:
        age = cache_info['age_minutes']
        if age == 0:
            cache_msg = f"{Fore.CYAN}ℹ Gig database: Fresh data{Style.RESET_ALL}"
        else:
            cache_msg = f"{Fore.CYAN}ℹ Gig database: Cached from {cache_info['cache_time']} ({age} min ago){Style.RESET_ALL}"
        response.append(f"\n{cache_msg}")
    
    return "\n".join(response) + "\n" + "=" * 50


def get_valid_date(prompt, year):
    """Prompt for a date and validate format immediately"""
    while True:
        date_str = input(prompt).strip()
        try:
            datetime.strptime(f"{year}-{date_str}", "%Y-%m-%d")
            return date_str
        except ValueError:
            print(f"{Fore.RED}Invalid format. Please use MM-DD (e.g., 07-05){Style.RESET_ALL}")


def get_valid_dj_name(prompt):
    """Prompt for a DJ name and validate (case-insensitive)"""
    valid_djs = ["Henry", "Woody", "Paul", "Stefano", "Felipe"]
    valid_djs_lower = [dj.lower() for dj in valid_djs]
    
    while True:
        dj_name = input(prompt).strip()
        dj_name_lower = dj_name.lower()
        
        if dj_name_lower in valid_djs_lower:
            return valid_djs[valid_djs_lower.index(dj_name_lower)]
        else:
            print(f"{Fore.RED}Invalid DJ name. Choose from: {', '.join(valid_djs)}{Style.RESET_ALL}")


def parse_date_range(start_str, end_str, year):
    """Parse start and end dates into datetime objects"""
    try:
        start_date = datetime.strptime(f"{year}-{start_str}", "%Y-%m-%d")
        end_date = datetime.strptime(f"{year}-{end_str}", "%Y-%m-%d")
        return start_date, end_date
    except ValueError:
        return None, None


def query_date_range(sheet_name, start_date_str, end_date_str, day_filter, service, spreadsheet, spreadsheet_id, min_spots=None):
    """Query availability across a date range"""
    start_date, end_date = parse_date_range(start_date_str, end_date_str, sheet_name)
    
    if not start_date or not end_date:
        return "Invalid date format. Please use MM-DD format for both dates."
    
    if start_date > end_date:
        print(f"{Fore.RED}Start date must be before or equal to end date.{Style.RESET_ALL}")
        return ""
    
    results = []
    current_date = start_date
    
    while current_date <= end_date:
        month_day = current_date.strftime("%m-%d")
        
        day_name = calendar.day_name[current_date.weekday()]
        include_date = True
        
        if day_filter:
            day_filter_lower = day_filter.lower()
            if day_filter_lower == "weekend":
                include_date = current_date.weekday() >= 5
            elif day_filter_lower == "weekday":
                include_date = current_date.weekday() < 5
            else:
                include_date = day_name.lower() == day_filter_lower
        
        if include_date:
            data = get_date_availability_data(sheet_name, month_day, service, spreadsheet, spreadsheet_id)
            # Skip if error or no data
            if data and isinstance(data, dict) and 'date_obj' in data:
                available_spots = data['availability']['available_spots']
                
                if min_spots is None or available_spots >= min_spots:
                    results.append({
                        'date': data['formatted_date'],
                        'available_spots': available_spots,
                        'available_djs': data['availability']['available_booking']
                    })
        
        current_date += timedelta(days=1)
    
    if not results:
        return f"No dates found matching criteria in range {start_date_str} to {end_date_str}."
    
    output = ["\n" + "=" * 50]
    output.append(f"AVAILABILITY QUERY RESULTS - {sheet_name}")
    output.append(f"Date range: {start_date_str} to {end_date_str}")
    
    if day_filter:
        output.append(f"Filter: {day_filter}")
    if min_spots is not None:
        output.append(f"Minimum spots: {min_spots}")
    
    output.append(f"Total matching dates: {len(results)}")
    output.append("=" * 50 + "\n")
    
    for result in results:
        spots = result['available_spots']
        color = Fore.GREEN if spots >= 2 else (Fore.YELLOW if spots == 1 else Fore.RED)
        
        dj_list = f" ({', '.join(result['available_djs'])})" if result['available_djs'] else ""
        output.append(f"{result['date']}: {color}{spots} spot(s) available{Style.RESET_ALL}{dj_list}")
    
    output.append("\n" + "=" * 50)
    return "\n".join(output)


def query_dj_availability(sheet_name, dj_name, start_date_str, end_date_str, service, spreadsheet, spreadsheet_id):
    """Query when a specific DJ is available"""
    start_date, end_date = parse_date_range(start_date_str, end_date_str, sheet_name)
    
    if not start_date or not end_date:
        return "Invalid date format. Please use MM-DD format for both dates."
    
    if start_date > end_date:
        print(f"{Fore.RED}Start date must be before or equal to end date.{Style.RESET_ALL}")
        return ""
    
    available_dates = []
    booked_dates = []
    backup_dates = []
    current_date = start_date
    
    while current_date <= end_date:
        month_day = current_date.strftime("%m-%d")
        data = get_date_availability_data(sheet_name, month_day, service, spreadsheet, spreadsheet_id)
        
        # Skip if error or no data
        if data and isinstance(data, dict) and 'date_obj' in data and dj_name in data['selected_data']:
            value = data['selected_data'][dj_name]
            is_bold = "(BOLD)" in value if value else False
            clean_value = value.replace(" (BOLD)", "") if value else ""
            value_lower = clean_value.lower()
            
            # Check gig database for actual bookings
            gig_bookings = data.get('gig_bookings', {'assigned': {}, 'unassigned': []})
            assigned_bookings = gig_bookings.get('assigned', {})
            
            if dj_name in assigned_bookings:
                venue = assigned_bookings[dj_name].get('venue', '')
                booked_dates.append(f"{data['formatted_date']} ({venue})")
            elif "booked" in value_lower:
                booked_dates.append(data['formatted_date'])
            elif "backup" in value_lower:
                backup_dates.append(data['formatted_date'])
            else:
                can_book, can_backup = check_dj_availability(
                    dj_name, clean_value, data['date_obj'], is_bold, sheet_name
                )
                if can_book:
                    available_dates.append(data['formatted_date'])
        
        current_date += timedelta(days=1)
    
    output = ["\n" + "=" * 50]
    output.append(f"DJ AVAILABILITY QUERY - {sheet_name}")
    output.append(f"DJ: {dj_name}")
    output.append(f"Date range: {start_date_str} to {end_date_str}")
    output.append("=" * 50 + "\n")
    
    output.append(f"{Fore.GREEN}AVAILABLE FOR BOOKING ({len(available_dates)} dates):{Style.RESET_ALL}")
    if available_dates:
        for date in available_dates:
            output.append(f"  {date}")
    else:
        output.append("  None")
    
    output.append(f"\n{Fore.RED}BOOKED ({len(booked_dates)} dates):{Style.RESET_ALL}")
    if booked_dates:
        for date in booked_dates:
            output.append(f"  {date}")
    else:
        output.append("  None")
    
    output.append(f"\n{Fore.BLUE}BACKUP ({len(backup_dates)} dates):{Style.RESET_ALL}")
    if backup_dates:
        for date in backup_dates:
            output.append(f"  {date}")
    else:
        output.append("  None")
    
    output.append("\n" + "=" * 50)
    return "\n".join(output)


def display_menu():
    """Display the main menu options"""
    print("\n" + "=" * 50)
    print("DJ AVAILABILITY CHECKER")
    print("=" * 50)
    print("1. Check specific date")
    print("2. Query date range")
    print("3. Find dates with minimum availability")
    print("4. Check DJ availability in range")
    print("5. Exit")
    print("=" * 50)


def main(sheet_name):
    """Main function to run the DJ availability checker"""
    # Initialize Google Sheets connection
    service, spreadsheet, spreadsheet_id, client = init_google_sheets_from_file()
    
    year = sheet_name
    
    print(f"\n{Style.BRIGHT}DJ Availability Checker - {year}{Style.RESET_ALL}")
    
    while True:
        display_menu()
        choice = input("\nSelect an option (1-5): ").strip()
        
        if choice == "1":
            while True:
                month_day = get_valid_date(f"\nEnter the {Style.BRIGHT}{year}{Style.RESET_ALL} date to check (MM-DD): ", year)
                result = check_availability(sheet_name, month_day, service, spreadsheet, spreadsheet_id, client)
                print(result)
                
                next_action = input("\nWhat would you like to do?\n  1. Check another date\n  2. Return to main menu\nChoice (1-2): ").strip()
                if next_action != "1":
                    break
            
        elif choice == "2":
            while True:
                start_date = get_valid_date(f"\nEnter start date (MM-DD): ", year)
                end_date = get_valid_date(f"Enter end date (MM-DD): ", year)
                day_filter = input("Filter by day (Saturday/Sunday/Weekend/Weekday or leave blank): ").strip() or None
                
                result = query_date_range(sheet_name, start_date, end_date, day_filter, service, spreadsheet, spreadsheet_id)
                if result:
                    print(result)
                
                next_action = input("\nWhat would you like to do?\n  1. Query another date range\n  2. Return to main menu\nChoice (1-2): ").strip()
                if next_action != "1":
                    break
            
        elif choice == "3":
            while True:
                start_date = get_valid_date(f"\nEnter start date (MM-DD): ", year)
                end_date = get_valid_date(f"Enter end date (MM-DD): ", year)
                
                while True:
                    min_spots_str = input("Minimum available spots (1, 2, etc.): ").strip()
                    try:
                        min_spots = int(min_spots_str)
                        if min_spots < 0:
                            print(f"{Fore.RED}Please enter a positive number.{Style.RESET_ALL}")
                        else:
                            break
                    except ValueError:
                        print(f"{Fore.RED}Invalid number. Please enter a number (e.g., 1, 2, 3).{Style.RESET_ALL}")
                
                day_filter = input("Filter by day (Saturday/Sunday/Weekend/Weekday or leave blank): ").strip() or None
                
                result = query_date_range(sheet_name, start_date, end_date, day_filter, service, spreadsheet, spreadsheet_id, min_spots)
                if result:
                    print(result)
                
                next_action = input("\nWhat would you like to do?\n  1. Search with different criteria\n  2. Return to main menu\nChoice (1-2): ").strip()
                if next_action != "1":
                    break
                
        elif choice == "4":
            while True:
                dj_name = get_valid_dj_name("\nEnter DJ name (Henry/Woody/Paul/Stefano/Felipe): ")
                start_date = get_valid_date(f"Enter start date (MM-DD): ", year)
                end_date = get_valid_date(f"Enter end date (MM-DD): ", year)
                
                result = query_dj_availability(sheet_name, dj_name, start_date, end_date, service, spreadsheet, spreadsheet_id)
                if result:
                    print(result)
                
                next_action = input("\nWhat would you like to do?\n  1. Check another DJ\n  2. Return to main menu\nChoice (1-2): ").strip()
                if next_action != "1":
                    break
            
        elif choice == "5":
            print("\nGoodbye!")
            break
            
        else:
            print("Invalid option. Please select 1-5.")


if __name__ == "__main__":
    main("2026")
