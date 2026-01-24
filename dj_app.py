"""
DJ Availability Checker - Streamlit Web Interface
Full-featured version with gig database, venue inquiries, and nearby bookings
"""

import streamlit as st
from datetime import datetime
import calendar
from dj_core import (
    init_google_sheets_from_dict, 
    get_date_availability_data, 
    get_columns_for_year,
    get_venue_inquiries_for_date,
    get_nearby_bookings_for_dj,
    check_dj_availability,
    is_weekend,
    get_cache_info,
    clear_gig_cache
)

# Page config
st.set_page_config(
    page_title="DJ Availability Checker",
    page_icon="🎵",
    layout="wide"
)

# Initialize Google Sheets
@st.cache_resource
def get_sheets_connection():
    """Initialize Google Sheets connection using Streamlit secrets"""
    credentials_dict = dict(st.secrets["gcp_service_account"])
    return init_google_sheets_from_dict(credentials_dict)


def format_dj_status_for_display(dj_name, value, date_obj, year, gig_booking=None, nearby_bookings=None):
    """Format DJ status for Streamlit display with venue info and nearby bookings"""
    
    # If we have gig database info, show venue
    if gig_booking:
        venue = gig_booking.get('venue', '')
        return f":red[BOOKED ({venue})]"
    
    # Special case for Stephanie 2026 - only available when explicitly assigned
    if dj_name == "Stephanie" and year == "2026":
        if not value or value.strip() == "":
            return "not available (2026)"
    
    # Special case for Stephanie on weekdays (2027+)
    if dj_name == "Stephanie" and year == "2027" and not is_weekend(date_obj):
        if not value or value.strip() == "":
            return "not available (weekday)"
    
    # Special case for Stefano with blank cell
    if dj_name == "Stefano" and (not value or value.strip() == ""):
        return ":orange[[MAYBE]]"
    
    value_lower = str(value).lower() if value else ""
    
    # Check for RESERVED status (AAG events)
    if value and "reserved" in value_lower:
        return f":red[{value}]"
    
    # Check for booked status
    if value and "booked" in value_lower:
        return f":red[{value}]"
    
    # Check for backup status
    if value and "backup" in value_lower:
        return f":blue[{value}]"
    
    # Felipe blank cell in 2026/2027
    if dj_name == "Felipe" and year in ["2026", "2027"] and (not value or value.strip() == ""):
        return ":blue[[BLANK] - can backup]"
    
    # Check if LAST status
    if value and value_lower == "last":
        return f":green[{value} - available (low priority)]"
    
    # Check availability
    is_bold = "(BOLD)" in value if value else False
    clean_value = value.replace(" (BOLD)", "") if value else ""
    can_book, can_backup = check_dj_availability(dj_name, clean_value, date_obj, is_bold, year)
    
    # Format nearby bookings if available
    nearby_text = ""
    if nearby_bookings and len(nearby_bookings) > 0:
        nearby_text = f" (booked: {', '.join(nearby_bookings)})"
    
    if can_book:
        return f":green[{value if value else 'BLANK'} - available{nearby_text}]"
    
    if can_backup:
        backup_reason = ""
        if dj_name == "Woody" and "out" in value_lower and is_weekend(date_obj):
            backup_reason = " (weekend)"
        elif dj_name == "Henry" and not is_weekend(date_obj) and (not value or value.strip() == ""):
            backup_reason = " (weekday)"
        
        return f":blue[{value if value else 'BLANK'} - can backup{backup_reason}]"
    
    return value if value else ""


def main():
    st.title("🎵 DJ Availability Checker")
    st.markdown("---")
    
    # Year selection
    year = st.selectbox("Select Year", ["2025", "2026", "2027"], index=2)
    
    # Date input
    col1, col2 = st.columns([2, 3])
    
    with col1:
        # Set default date based on selected year
        if int(year) > datetime.now().year:
            # Future year - use January 1st of that year
            default_date = datetime(int(year), 1, 1)
        elif int(year) < datetime.now().year:
            # Past year - use today's month/day if valid, else Jan 1
            try:
                default_date = datetime(int(year), datetime.now().month, datetime.now().day)
            except ValueError:
                # Invalid date (e.g., Feb 29 in non-leap year)
                default_date = datetime(int(year), 1, 1)
        else:
            # Current year - use today
            default_date = datetime.now()
        
        date_input = st.date_input(
            "Select Date",
            value=default_date,
            min_value=datetime(int(year), 1, 1),
            max_value=datetime(int(year), 12, 31)
        )
        
        # Buttons in columns
        btn_col1, btn_col2 = st.columns([2, 1])
        with btn_col1:
            check_button = st.button("Check Availability", type="primary", use_container_width=True)
        with btn_col2:
            refresh_button = st.button("🔄 Refresh", help="Clear cache & fetch fresh data", use_container_width=True)
        
        if refresh_button:
            clear_gig_cache()
            st.success("Cache cleared! Click 'Check Availability' for fresh data.")
            st.rerun()
        
        if check_button:
            month_day = date_input.strftime("%m-%d")
            
            # Get sheets connection (now returns 4 values)
            service, spreadsheet, spreadsheet_id, client = get_sheets_connection()
            
            # Get availability data
            with st.spinner('Checking availability...'):
                result = get_date_availability_data(year, month_day, service, spreadsheet, spreadsheet_id)
            
            if 'error' in result:
                if result['error'] == 'invalid_format':
                    st.error("Invalid date format. Please select a valid date.")
                elif result['error'] == 'not_found':
                    st.error(f"No data found for {result['formatted_date']}")
                elif result['error'] == 'worksheet_not_found':
                    st.error(f"Worksheet '{year}' not found in the spreadsheet")
            else:
                # Get venue inquiries
                venue_info = get_venue_inquiries_for_date(result['formatted_date'], client)
                
                # Store result in session state
                st.session_state['result'] = result
                st.session_state['year'] = year
                st.session_state['venue_info'] = venue_info
                st.session_state['service'] = service
                st.session_state['spreadsheet'] = spreadsheet
                st.session_state['spreadsheet_id'] = spreadsheet_id
    
    # Display results if available
    if 'result' in st.session_state:
        result = st.session_state['result']
        display_year = st.session_state['year']
        venue_info = st.session_state.get('venue_info', {'booked': [], 'not_booked': []})
        service = st.session_state.get('service')
        spreadsheet = st.session_state.get('spreadsheet')
        spreadsheet_id = st.session_state.get('spreadsheet_id')
        
        st.markdown("---")
        st.subheader(f"📅 {result['formatted_date']}, {display_year}")
        
        # Get columns for the year
        columns = get_columns_for_year(display_year)
        
        # Get gig bookings from result
        gig_bookings = result.get('gig_bookings', {'assigned': {}, 'unassigned': []})
        assigned_bookings = gig_bookings.get('assigned', {})
        unassigned_bookings = gig_bookings.get('unassigned', [])
        
        # Display DJ statuses
        st.markdown("#### DJ Status")
        
        # Create two columns for the DJ status display
        status_col1, status_col2 = st.columns(2)
        
        selected_data = result['selected_data']
        date_obj = result['date_obj']
        dj_items = []
        
        for col_letter in sorted(columns.keys()):
            label = columns[col_letter]
            if label in selected_data and label != "Date":
                value = selected_data[label]
                
                # Handle special columns
                if label == "TBA":
                    if unassigned_bookings:
                        venues = [b.get('venue', 'Unknown') for b in unassigned_bookings]
                        formatted_value = f":red[BOOKED ({', '.join(venues)})]"
                    elif value and ("booked" in str(value).lower() or "aag" in str(value).lower()):
                        formatted_value = f":red[{value}]"
                    else:
                        formatted_value = value if value else ""
                    dj_items.append((label, formatted_value))
                
                elif label == "AAG":
                    # AAG RESERVED in red (2027+)
                    value_lower = str(value).lower()
                    if "reserved" in value_lower:
                        formatted_value = f":red[{value}]"
                    elif value:
                        formatted_value = value
                    else:
                        formatted_value = ""
                    dj_items.append((label, formatted_value))
                
                elif label == "Stephanie":
                    # Check if Stephanie has a gig database booking
                    steph_booking = assigned_bookings.get("Stephanie")
                    
                    # Get nearby bookings if available
                    nearby_bookings = []
                    if not steph_booking:
                        is_bold = "(BOLD)" in value if value else False
                        clean_value = value.replace(" (BOLD)", "") if value else ""
                        can_book, _ = check_dj_availability(label, clean_value, date_obj, is_bold, display_year)
                        if can_book:
                            nearby_bookings = get_nearby_bookings_for_dj(
                                label, date_obj, display_year, service, spreadsheet, spreadsheet_id
                            )
                    
                    formatted_value = format_dj_status_for_display(
                        label, value, date_obj, display_year, steph_booking, nearby_bookings
                    )
                    dj_items.append((label, formatted_value))
                
                else:
                    # Regular DJ
                    dj_gig_booking = assigned_bookings.get(label)
                    
                    # Get nearby bookings if DJ is available
                    nearby_bookings = []
                    if not dj_gig_booking:
                        is_bold = "(BOLD)" in value if value else False
                        clean_value = value.replace(" (BOLD)", "") if value else ""
                        can_book, _ = check_dj_availability(label, clean_value, date_obj, is_bold, display_year)
                        if can_book:
                            nearby_bookings = get_nearby_bookings_for_dj(
                                label, date_obj, display_year, service, spreadsheet, spreadsheet_id
                            )
                    
                    formatted_value = format_dj_status_for_display(
                        label, value, date_obj, display_year, dj_gig_booking, nearby_bookings
                    )
                    dj_items.append((label, formatted_value))
        
        # Split items between columns
        mid_point = len(dj_items) // 2 + len(dj_items) % 2
        
        with status_col1:
            for label, formatted_value in dj_items[:mid_point]:
                st.markdown(f"**{label}:** {formatted_value}")
        
        with status_col2:
            for label, formatted_value in dj_items[mid_point:]:
                st.markdown(f"**{label}:** {formatted_value}")
        
        # Display availability summary
        st.markdown("---")
        st.markdown("#### 📊 Availability Summary")
        
        avail = result['availability']
        
        summary_col1, summary_col2, summary_col3 = st.columns(3)
        
        with summary_col1:
            st.metric("Total Booked", avail['booked_count'])
        
        with summary_col2:
            st.metric("Assigned Backups", avail['backup_count'])
        
        with summary_col3:
            st.metric(
                "Open Spots", 
                avail['available_spots'],
                delta="Available" if avail['available_spots'] > 0 else "FULL"
            )
        
        # Additional info
        if avail.get('tba_bookings', 0) > 0:
            st.info(f"📝 TBA Bookings (need assignment): **{avail['tba_bookings']}**")
        
        if avail.get('aag_reserved', False):
            st.warning("🏛️ **AAG Spot Reserved:** 1 spot held for Allied Arts Guild")
        
        # Stefano uncertainty
        has_uncertain_stefano = False
        if "Stefano" in selected_data and (not selected_data["Stefano"] or selected_data["Stefano"].strip() == ""):
            has_uncertain_stefano = True
        
        # Available DJs
        if avail['available_spots'] > 0:
            if has_uncertain_stefano and avail['available_spots'] <= 2:
                st.success("✓ Spots available for booking! *")
                st.caption("* Availability depends on Stefano's confirmation")
            else:
                st.success("✓ Spots available for booking!")
            
            avail_col1, avail_col2 = st.columns(2)
            
            with avail_col1:
                st.markdown("**Available for Booking:**")
                for dj in avail['available_booking']:
                    st.markdown(f"- {dj}")
            
            with avail_col2:
                st.markdown("**Available for Backup:**")
                for dj in avail['available_backup']:
                    st.markdown(f"- {dj}")
        else:
            st.error("✗ **FULL** - No spots available")
            if len(avail['available_backup']) > 0:
                st.markdown("**Available for Backup:**")
                for dj in avail['available_backup']:
                    st.markdown(f"- {dj}")
        
        # Venue inquiries
        if venue_info and venue_info.get('not_booked'):
            st.markdown("---")
            st.markdown("#### 📋 Venue Inquiries (Not Booked)")
            st.warning(", ".join(venue_info['not_booked']))
        
        # Show cache info
        cache_info = get_cache_info()
        if cache_info:
            st.markdown("---")
            age = cache_info['age_minutes']
            if age == 0:
                st.info("ℹ️ **Gig database:** Fresh data (just fetched)")
            elif age < 5:
                st.info(f"ℹ️ **Gig database:** Cached from {cache_info['cache_time']} ({age} min ago) - Fresh!")
            else:
                st.info(f"ℹ️ **Gig database:** Cached from {cache_info['cache_time']} ({age} min ago)")
                st.caption("💡 Click 🔄 Refresh button to fetch fresh data")
    
    # Sidebar with instructions
    with st.sidebar:
        st.markdown("### 📖 How to Use")
        st.markdown("""
        1. Select the year you want to check
        2. Choose a date from the calendar
        3. Click "Check Availability"
        4. Review the DJ status and availability summary
        """)
        
        st.markdown("---")
        st.markdown("### 🎨 Status Colors")
        st.markdown("""
        - :red[**Red**] = Booked (with venue name)
        - :blue[**Blue**] = Backup assigned
        - :green[**Green**] = Available
        - :orange[**Orange**] = Maybe/Other status
        """)
        
        st.markdown("---")
        st.markdown("### ✨ Features")
        st.markdown("""
        - **Venue Names** from gig database
        - **Nearby Bookings** (±3 days)
        - **Venue Inquiries** tracking
        - **AAG Reserved** spots (2027)
        - **Stefano [MAYBE]** indicators
        """)
        
        st.markdown("---")
        st.markdown("### 📋 2027 Updates")
        st.markdown("""
        - **Stephanie** (weekends only)
        - **AAG** column for Allied Arts Guild
        - **Felipe** backup-only default
        """)

if __name__ == "__main__":
    main()
