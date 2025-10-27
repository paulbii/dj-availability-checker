import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import calendar
from googleapiclient.discovery import build
import time

# Page configuration
st.set_page_config(
    page_title="DJ Availability Checker",
    page_icon="🎵",
    layout="wide"
)

# Global variables and setup
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

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

@st.cache_resource
def init_google_sheets():
    """Initialize Google Sheets connection (cached)"""
# Check if running on Streamlit Cloud or locally
if 'STREAMLIT_SHARING_MODE' in st.secrets:
    # Running on Streamlit Cloud - use secrets
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], scope
    )
else:
    # Running locally - use file
    creds = ServiceAccountCredentials.from_json_keyfile_name('your-credentials.json', scope)
    client = gspread.authorize(creds)
    service = build('sheets', 'v4', credentials=creds)
    spreadsheet_id = '1lXwHECkQJy7h87L5oKbo0hDTpalDgKFTbBQJ4pIerFo'
    spreadsheet = client.open_by_key(spreadsheet_id)
    return service, spreadsheet

def get_column_indices(column_letters):
    """Convert column letters to zero-based indices"""
    return {label: ord(col) - ord('A') for col, label in column_letters.items()}

def is_weekend(date_obj):
    """Check if date is a weekend"""
    return date_obj.weekday() >= 5

def check_dj_availability(dj_name, value, date_obj=None, is_bold=False, year=None):
    """Check if a DJ is available based on their current status"""
    value = str(value).strip() if value else ""
    value_lower = value.lower()
    is_weekend_day = date_obj and date_obj.weekday() >= 5 if date_obj else False
    
    if dj_name == "Henry" and not is_weekend_day:
        if not value:
            return False, True
        if value_lower == "out":
            return False, False
    
    if value_lower == "booked" or value_lower == "backup":
        return False, False
    
    if dj_name == "Felipe" and year == "2026":
        if not value:
            return False, False
        if value_lower == "dad" or value_lower == "ok to backup":
            return False, True
        if value_lower == "out" or value_lower == "maxed":
            return False, False
        return False, False
        
    if not value:
        if dj_name == "Stefano":
            return False, False
        return True, True
        
    if value_lower == "out" or value_lower == "maxed":
        if dj_name == "Woody" and is_weekend_day and not is_bold:
            return False, True
        return False, False
        
    if value_lower == "ok to backup":
        return False, True
        
    if value_lower == "ok":
        return True, True
        
    if dj_name == "Felipe" and value_lower == "dad":
        return False, True
        
    if dj_name == "Stefano" and value_lower == "ok":
        return True, True
        
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
    
    for name, value in selected_data.items():
        if name in ["Date", "Stephanie"]:
            continue
            
        value = str(value).replace(" (BOLD)", "") if value else ""
        value_lower = value.lower()
        
        if name == "TBA" and "booked" in value_lower:
            if "x" in value_lower:
                try:
                    multiplier = int(value_lower.split("x")[1].strip())
                    tba_bookings += multiplier
                    booked_count += multiplier
                except (ValueError, IndexError):
                    tba_bookings += 1
                    booked_count += 1
            else:
                tba_bookings += 1
                booked_count += 1
            continue
            
        if value_lower == "booked":
            booked_count += 1
    
    for name, value in selected_data.items():
        if name in ["Date", "TBA", "Stephanie"]:
            continue
            
        is_bold = "(BOLD)" in value if value else False
        value = value.replace(" (BOLD)", "") if value else ""
        value_lower = value.lower()
        
        if value_lower == "backup":
            backup_count += 1
        elif value_lower != "booked":
            can_book, can_backup = check_dj_availability(name, value, date_obj, is_bold, year)
            if can_book:
                available_for_booking.append(name)
            if can_backup:
                available_for_backup.append(name)
    
    available_spots = len(available_for_booking)
    
    if tba_bookings > 0:
        available_spots = max(0, available_spots - tba_bookings)
        
    if backup_count == 0 and len(available_for_backup) == 0:
        available_spots = 0
    
    return {
        'booked_count': booked_count,
        'available_spots': available_spots,
        'available_booking': available_for_booking,
        'available_backup': available_for_backup,
        'tba_bookings': tba_bookings,
        'backup_count': backup_count
    }

def get_date_availability_data(sheet_name, month_day, service, spreadsheet, spreadsheet_id):
    """Get availability data for a specific date"""
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

def format_dj_status_html(dj_name, value, date_obj, is_bookable, is_backup, year=None):
    """Format a DJ's status with HTML/CSS styling"""
    if dj_name == "Stefano" and (not value or value.strip() == ""):
        return f"<span style='color: #FFA500;'>{dj_name}: [MAYBE]</span>"
    
    value_lower = value.lower() if value else ""
    if value and "booked" in value_lower:
        return f"<span style='color: #FF0000; font-weight: bold;'>{dj_name}: {value}</span>"
    
    if value and "backup" in value_lower:
        return f"<span style='color: #0000FF;'>{dj_name}: {value}</span>"
    
    if dj_name == "Felipe" and year == "2026" and (not value or value.strip() == ""):
        return f"{dj_name}: - not available"
    
    if value and value_lower == "last":
        return f"<span style='color: #00AA00;'>{dj_name}: {value} - available (low priority)</span>"
    
    if is_bookable:
        return f"<span style='color: #00AA00;'>{dj_name}: {value} - available</span>"
    
    if is_backup:
        backup_reason = ""
        if dj_name == "Woody" and "out" in value_lower and is_weekend(date_obj):
            backup_reason = " (weekend)"
        elif dj_name == "Henry" and not is_weekend(date_obj) and (not value or value.strip() == ""):
            backup_reason = " (weekday)"
        
        return f"<span style='color: #0000FF;'>{dj_name}: {value} - can backup{backup_reason}</span>"
    
    return f"{dj_name}: {value}"

# Main App
def main():
    st.title("🎵 DJ Availability Checker")
    
    # Initialize Google Sheets
    try:
        service, spreadsheet = init_google_sheets()
        spreadsheet_id = '1lXwHECkQJy7h87L5oKbo0hDTpalDgKFTbBQJ4pIerFo'
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {str(e)}")
        return
    
    # Sidebar for year selection
    year = st.sidebar.selectbox("Select Year", ["2025", "2026"], index=1)
    
    # Main menu
    st.sidebar.markdown("---")
    option = st.sidebar.radio(
        "Choose an option:",
        [
            "Check Specific Date",
            "Query Date Range",
            "Find Dates with Availability",
            "Check DJ Availability"
        ]
    )
    
    # Option 1: Check Specific Date
    if option == "Check Specific Date":
        st.header("Check Specific Date")
        
        date_input = st.date_input(
            "Select a date",
            min_value=datetime(int(year), 1, 1),
            max_value=datetime(int(year), 12, 31)
        )
        
        if st.button("Check Availability", type="primary"):
            month_day = date_input.strftime("%m-%d")
            data = get_date_availability_data(year, month_day, service, spreadsheet, spreadsheet_id)
            
            if data:
                st.success(f"**Date:** {data['formatted_date']}")
                
                # Display DJ statuses
                st.subheader("DJ Status")
                for label, value in data['selected_data'].items():
                    if label != "Date":
                        if label == "TBA":
                            if value and "booked" in str(value).lower():
                                st.markdown(f"<span style='color: #FF0000; font-weight: bold;'>{label}: {value}</span>", unsafe_allow_html=True)
                            else:
                                st.write(f"{label}: {value}")
                        elif label == "Stephanie":
                            value_lower = str(value).lower()
                            if "booked" in value_lower:
                                st.markdown(f"<span style='color: #FF0000; font-weight: bold;'>{label}: {value}</span>", unsafe_allow_html=True)
                            elif "backup" in value_lower:
                                st.markdown(f"<span style='color: #0000FF;'>{label}: {value}</span>", unsafe_allow_html=True)
                            else:
                                st.write(f"{label}: {value}")
                        else:
                            is_bold = "(BOLD)" in value if value else False
                            clean_value = value.replace(" (BOLD)", "") if value else ""
                            can_book, can_backup = check_dj_availability(label, clean_value, data['date_obj'], is_bold, year)
                            
                            formatted = format_dj_status_html(label, value, data['date_obj'], can_book, can_backup, year)
                            st.markdown(formatted, unsafe_allow_html=True)
                
                # Availability summary
                st.markdown("---")
                st.subheader("Availability Summary")
                availability = data['availability']
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Confirmed Bookings", availability['booked_count'])
                with col2:
                    st.metric("Available Spots", availability['available_spots'])
                
                if availability['available_booking']:
                    st.info(f"**Available DJs:** {', '.join(availability['available_booking'])}")
            else:
                st.error("No data found for this date.")
    
    # Option 2: Query Date Range
    elif option == "Query Date Range":
        st.header("Query Date Range")
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "Start Date",
                min_value=datetime(int(year), 1, 1),
                max_value=datetime(int(year), 12, 31)
            )
        with col2:
            end_date = st.date_input(
                "End Date",
                min_value=datetime(int(year), 1, 1),
                max_value=datetime(int(year), 12, 31)
            )
        
        day_filter = st.selectbox(
            "Filter by day (optional)",
            ["All Days", "Saturday", "Sunday", "Weekend", "Weekday"]
        )
        
        if st.button("Search", type="primary"):
            if start_date > end_date:
                st.error("Start date must be before or equal to end date.")
            else:
                filter_value = None if day_filter == "All Days" else day_filter
                
                results = []
                current_date = start_date
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total_days = (end_date - start_date).days + 1
                day_count = 0
                
                while current_date <= end_date:
                    month_day = current_date.strftime("%m-%d")
                    
                    day_name = calendar.day_name[current_date.weekday()]
                    include_date = True
                    
                    if filter_value:
                        filter_lower = filter_value.lower()
                        if filter_lower == "weekend":
                            include_date = current_date.weekday() >= 5
                        elif filter_lower == "weekday":
                            include_date = current_date.weekday() < 5
                        else:
                            include_date = day_name.lower() == filter_lower
                    
                    if include_date:
                        data = get_date_availability_data(year, month_day, service, spreadsheet, spreadsheet_id)
                        if data:
                            results.append({
                                'date': data['formatted_date'],
                                'available_spots': data['availability']['available_spots'],
                                'available_djs': data['availability']['available_booking']
                            })
                    
                    current_date += timedelta(days=1)
                    day_count += 1
                    progress_bar.progress(day_count / total_days)
                    status_text.text(f"Checking {day_count}/{total_days} days...")
                    time.sleep(0.05)  # Small delay to avoid rate limits
                
                progress_bar.empty()
                status_text.empty()
                
                if results:
                    st.success(f"Found {len(results)} matching dates")
                    
                    for result in results:
                        spots = result['available_spots']
                        color = "#00AA00" if spots >= 2 else ("#FFA500" if spots == 1 else "#FF0000")
                        dj_list = f" ({', '.join(result['available_djs'])})" if result['available_djs'] else ""
                        
                        st.markdown(
                            f"<span style='color: {color}; font-weight: bold;'>{result['date']}: {spots} spot(s) available</span>{dj_list}",
                            unsafe_allow_html=True
                        )
                else:
                    st.warning("No dates found matching your criteria.")
    
    # Option 3: Find Dates with Availability
    elif option == "Find Dates with Availability":
        st.header("Find Dates with Minimum Availability")
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "Start Date",
                min_value=datetime(int(year), 1, 1),
                max_value=datetime(int(year), 12, 31),
                key="min_start"
            )
        with col2:
            end_date = st.date_input(
                "End Date",
                min_value=datetime(int(year), 1, 1),
                max_value=datetime(int(year), 12, 31),
                key="min_end"
            )
        
        min_spots = st.number_input("Minimum available spots", min_value=1, max_value=5, value=1)
        
        day_filter = st.selectbox(
            "Filter by day (optional)",
            ["All Days", "Saturday", "Sunday", "Weekend", "Weekday"],
            key="min_filter"
        )
        
        if st.button("Find Dates", type="primary"):
            if start_date > end_date:
                st.error("Start date must be before or equal to end date.")
            else:
                filter_value = None if day_filter == "All Days" else day_filter
                
                results = []
                current_date = start_date
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total_days = (end_date - start_date).days + 1
                day_count = 0
                
                while current_date <= end_date:
                    month_day = current_date.strftime("%m-%d")
                    
                    day_name = calendar.day_name[current_date.weekday()]
                    include_date = True
                    
                    if filter_value:
                        filter_lower = filter_value.lower()
                        if filter_lower == "weekend":
                            include_date = current_date.weekday() >= 5
                        elif filter_lower == "weekday":
                            include_date = current_date.weekday() < 5
                        else:
                            include_date = day_name.lower() == filter_lower
                    
                    if include_date:
                        data = get_date_availability_data(year, month_day, service, spreadsheet, spreadsheet_id)
                        if data and data['availability']['available_spots'] >= min_spots:
                            results.append({
                                'date': data['formatted_date'],
                                'available_spots': data['availability']['available_spots'],
                                'available_djs': data['availability']['available_booking']
                            })
                    
                    current_date += timedelta(days=1)
                    day_count += 1
                    progress_bar.progress(day_count / total_days)
                    status_text.text(f"Searching {day_count}/{total_days} days...")
                    time.sleep(0.05)
                
                progress_bar.empty()
                status_text.empty()
                
                if results:
                    st.success(f"Found {len(results)} dates with {min_spots}+ spots available")
                    
                    for result in results:
                        spots = result['available_spots']
                        color = "#00AA00" if spots >= 2 else "#FFA500"
                        dj_list = f" ({', '.join(result['available_djs'])})" if result['available_djs'] else ""
                        
                        st.markdown(
                            f"<span style='color: {color}; font-weight: bold;'>{result['date']}: {spots} spot(s) available</span>{dj_list}",
                            unsafe_allow_html=True
                        )
                else:
                    st.warning(f"No dates found with {min_spots}+ spots available.")
    
    # Option 4: Check DJ Availability
    elif option == "Check DJ Availability":
        st.header("Check DJ Availability in Range")
        
        dj_name = st.selectbox(
            "Select DJ",
            ["Henry", "Woody", "Paul", "Stefano", "Felipe"]
        )
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "Start Date",
                min_value=datetime(int(year), 1, 1),
                max_value=datetime(int(year), 12, 31),
                key="dj_start"
            )
        with col2:
            end_date = st.date_input(
                "End Date",
                min_value=datetime(int(year), 1, 1),
                max_value=datetime(int(year), 12, 31),
                key="dj_end"
            )
        
        if st.button("Check DJ", type="primary"):
            if start_date > end_date:
                st.error("Start date must be before or equal to end date.")
            else:
                available_dates = []
                booked_dates = []
                backup_dates = []
                current_date = start_date
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total_days = (end_date - start_date).days + 1
                day_count = 0
                
                while current_date <= end_date:
                    month_day = current_date.strftime("%m-%d")
                    data = get_date_availability_data(year, month_day, service, spreadsheet, spreadsheet_id)
                    
                    if data and dj_name in data['selected_data']:
                        value = data['selected_data'][dj_name]
                        is_bold = "(BOLD)" in value if value else False
                        clean_value = value.replace(" (BOLD)", "") if value else ""
                        value_lower = clean_value.lower()
                        
                        if "booked" in value_lower:
                            booked_dates.append(data['formatted_date'])
                        elif "backup" in value_lower:
                            backup_dates.append(data['formatted_date'])
                        else:
                            can_book, can_backup = check_dj_availability(
                                dj_name, clean_value, data['date_obj'], is_bold, year
                            )
                            if can_book:
                                available_dates.append(data['formatted_date'])
                    
                    current_date += timedelta(days=1)
                    day_count += 1
                    progress_bar.progress(day_count / total_days)
                    status_text.text(f"Checking {day_count}/{total_days} days...")
                    time.sleep(0.05)
                
                progress_bar.empty()
                status_text.empty()
                
                # Display results in columns
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown(f"### 🟢 Available ({len(available_dates)})")
                    if available_dates:
                        for date in available_dates:
                            st.write(date)
                    else:
                        st.write("None")
                
                with col2:
                    st.markdown(f"### 🔴 Booked ({len(booked_dates)})")
                    if booked_dates:
                        for date in booked_dates:
                            st.write(date)
                    else:
                        st.write("None")
                
                with col3:
                    st.markdown(f"### 🔵 Backup ({len(backup_dates)})")
                    if backup_dates:
                        for date in backup_dates:
                            st.write(date)
                    else:
                        st.write("None")

if __name__ == "__main__":
    main()
