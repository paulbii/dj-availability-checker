"""
DJ Availability Checker - Streamlit Web Interface
Full-featured version with all query types, gig database, venue inquiries,
and nearby bookings. Matches the terminal and GUI versions.
"""

import streamlit as st
from datetime import datetime
import calendar
from dj_core import (
    init_google_sheets_from_dict,
    get_date_availability_data,
    get_columns_for_year,
    get_venue_inquiries_for_date,
    get_full_inquiries_for_date,
    get_nearby_bookings_for_dj,
    check_dj_availability,
    is_weekend,
    get_cache_info,
    clear_gig_cache,
    get_fully_booked_dates,
    get_bulk_availability_data,
    auto_clear_stale_cache,
    get_gig_database_bookings,
    KNOWN_CELL_VALUES,
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
    clean_value = value.replace(" (BOLD)", "").strip() if value else ""
    clean_lower = clean_value.lower()

    # If we have gig database info, show venue
    if gig_booking:
        venue = gig_booking.get('venue', '')
        text = f":red[BOOKED ({venue})]"
        # Warn if matrix doesn't match
        if clean_lower != "booked":
            if clean_value:
                text += f"  :orange[⚠️ matrix shows \"{clean_value}\"]"
            else:
                text += f"  :orange[⚠️ matrix is blank]"
        return text

    # Special case for Stephanie 2026 - only available when explicitly assigned
    if dj_name == "Stephanie" and year == "2026":
        if not value or value.strip() == "":
            return "not available (2026)"

    # Special case for Stephanie on weekdays (2027+)
    if dj_name == "Stephanie" and int(year) >= 2027 and not is_weekend(date_obj):
        if not value or value.strip() == "":
            return "not available (weekday)"

    # Special case for Stefano with blank cell
    if dj_name == "Stefano" and (not value or value.strip() == ""):
        return ":orange[[MAYBE]]"

    value_lower = str(value).lower() if value else ""

    # Check for RESERVED status
    if value and "reserved" in value_lower:
        return f":red[RESERVED]"

    # Check for STANFORD status
    if value and value_lower == "stanford":
        return f":red[STANFORD]"

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

    # Unknown cell value warning
    if clean_value and clean_lower not in KNOWN_CELL_VALUES:
        return f":orange[{clean_value} ⚠️ unknown status — treating as unavailable]"

    # Check availability
    is_bold = "(BOLD)" in value if value else False
    can_book, can_backup = check_dj_availability(dj_name, clean_value, date_obj, is_bold, year, warn=False)

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
        elif dj_name == "Felipe" and ("dad" in value_lower or "ok to backup" in value_lower):
            backup_reason = ""

        return f":blue[{value if value else 'BLANK'} - can backup{backup_reason}]"

    return value if value else ""


# ── Tab: Check Specific Date ──────────────────────────────────────────────────

def tab_check_date(year, service, spreadsheet, spreadsheet_id, client):
    """Check availability for a specific date."""

    col1, col2 = st.columns([2, 3])

    with col1:
        # Set default date based on selected year
        year_int = int(year)
        now = datetime.now()
        if year_int > now.year:
            default_date = datetime(year_int, 1, 1)
        elif year_int < now.year:
            try:
                default_date = datetime(year_int, now.month, now.day)
            except ValueError:
                default_date = datetime(year_int, 1, 1)
        else:
            default_date = now

        date_input = st.date_input(
            "Select Date",
            value=default_date,
            min_value=datetime(year_int, 1, 1),
            max_value=datetime(year_int, 12, 31),
            key="single_date"
        )

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

            with st.spinner('Checking availability...'):
                result = get_date_availability_data(year, month_day, service, spreadsheet, spreadsheet_id)

            if result is None or (isinstance(result, dict) and 'error' in result):
                if result is None:
                    st.error("An unexpected error occurred.")
                elif result['error'] == 'invalid_format':
                    st.error("Invalid date format.")
                elif result['error'] == 'not_found':
                    st.error(f"No data found for {result['formatted_date']}")
                elif result['error'] == 'worksheet_not_found':
                    st.error(f"Worksheet '{year}' not found")
            else:
                st.session_state['single_result'] = result
                venue_info = get_venue_inquiries_for_date(result['formatted_date'], client)
                st.session_state['single_venue_info'] = venue_info

    # Display results
    if 'single_result' in st.session_state:
        result = st.session_state['single_result']
        venue_info = st.session_state.get('single_venue_info', {'booked': [], 'not_booked': []})

        st.markdown("---")
        st.subheader(f"📅 {result['formatted_date']}, {year}")

        columns = get_columns_for_year(year)
        gig_bookings = result.get('gig_bookings', {'assigned': {}, 'unassigned': []})
        assigned_bookings = gig_bookings.get('assigned', {})
        unassigned_bookings = gig_bookings.get('unassigned', [])

        st.markdown("#### DJ Status")
        status_col1, status_col2 = st.columns(2)

        selected_data = result['selected_data']
        date_obj = result['date_obj']
        year_int = int(year)
        dj_items = []

        for col_letter in sorted(columns.keys()):
            label = columns[col_letter]
            if label in selected_data and label != "Date":
                value = selected_data[label]

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
                    vl = str(value).lower()
                    if "reserved" in vl:
                        formatted_value = f":red[{value}]"
                    else:
                        formatted_value = value if value else ""
                    dj_items.append((label, formatted_value))

                elif label == "Stephanie":
                    steph_booking = assigned_bookings.get("Stephanie")
                    nearby_bookings = []
                    if not steph_booking:
                        is_bold = "(BOLD)" in value if value else False
                        clean_value = value.replace(" (BOLD)", "") if value else ""
                        can_book, _ = check_dj_availability(label, clean_value, date_obj, is_bold, year, warn=False)
                        if can_book:
                            nearby_bookings = get_nearby_bookings_for_dj(
                                label, date_obj, year, service, spreadsheet, spreadsheet_id
                            )
                    formatted_value = format_dj_status_for_display(
                        label, value, date_obj, year, steph_booking, nearby_bookings
                    )
                    dj_items.append((label, formatted_value))

                else:
                    dj_gig_booking = assigned_bookings.get(label)
                    nearby_bookings = []
                    if not dj_gig_booking:
                        is_bold = "(BOLD)" in value if value else False
                        clean_value = value.replace(" (BOLD)", "") if value else ""
                        can_book, _ = check_dj_availability(label, clean_value, date_obj, is_bold, year, warn=False)
                        if can_book:
                            nearby_bookings = get_nearby_bookings_for_dj(
                                label, date_obj, year, service, spreadsheet, spreadsheet_id
                            )
                    formatted_value = format_dj_status_for_display(
                        label, value, date_obj, year, dj_gig_booking, nearby_bookings
                    )
                    dj_items.append((label, formatted_value))

        mid_point = len(dj_items) // 2 + len(dj_items) % 2

        with status_col1:
            for label, formatted_value in dj_items[:mid_point]:
                st.markdown(f"**{label}:** {formatted_value}")

        with status_col2:
            for label, formatted_value in dj_items[mid_point:]:
                st.markdown(f"**{label}:** {formatted_value}")

        # Availability summary
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

        if avail.get('tba_bookings', 0) > 0:
            st.info(f"📝 TBA Bookings (need assignment): **{avail['tba_bookings']}**")

        if avail.get('aag_reserved', False):
            st.warning("🏛️ **AAG Spot Reserved:** 1 spot held for Allied Arts Guild")

        has_uncertain_stefano = "Stefano" in selected_data and (
            not selected_data["Stefano"] or selected_data["Stefano"].strip() == ""
        )

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

        # Cache info
        cache_info = get_cache_info()
        if cache_info:
            st.markdown("---")
            age = cache_info['age_minutes']
            cache_time = cache_info['cache_time']
            if age == 0 or cache_time == 'Just now':
                st.info("ℹ️ **Gig database:** Fresh data (just fetched)")
            elif age < 5:
                st.info(f"ℹ️ **Gig database:** Cached from {cache_time} ({age} min ago) - Fresh!")
            else:
                st.info(f"ℹ️ **Gig database:** Cached from {cache_time} ({age} min ago)")
                st.caption("💡 Click 🔄 Refresh button to fetch fresh data")


# ── Tab: Date Range Query ─────────────────────────────────────────────────────

def tab_date_range(year, service, spreadsheet, spreadsheet_id):
    """Query availability across a date range."""

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        start_str = st.text_input("Start (MM-DD)", placeholder="06-01", key="range_start")
    with col2:
        end_str = st.text_input("End (MM-DD)", placeholder="09-30", key="range_end")
    with col3:
        day_filter = st.selectbox("Day Filter", ["All Days", "Saturday", "Sunday", "Weekend", "Weekday"], key="range_filter")
    with col4:
        st.write("")  # spacer
        st.write("")
        search = st.button("Search", type="primary", key="range_search")

    if search and start_str and end_str:
        try:
            start_date = datetime.strptime(f"{year}-{start_str}", "%Y-%m-%d")
            end_date = datetime.strptime(f"{year}-{end_str}", "%Y-%m-%d")
        except ValueError:
            st.error("Invalid date format. Use MM-DD (e.g., 06-01).")
            return

        if start_date > end_date:
            st.error("Start date must be before end date.")
            return

        df = day_filter if day_filter != "All Days" else None

        with st.spinner('Fetching data...'):
            all_data = get_bulk_availability_data(year, service, spreadsheet, spreadsheet_id, start_date, end_date)

        if all_data is None:
            st.error(f"Error fetching data from {year} sheet.")
            return

        results = []
        for date_info in all_data:
            date_obj = date_info['date_obj']
            day_name = calendar.day_name[date_obj.weekday()]
            include = True

            if df:
                df_lower = df.lower()
                if df_lower == "weekend":
                    include = date_obj.weekday() >= 5
                elif df_lower == "weekday":
                    include = date_obj.weekday() < 5
                else:
                    include = day_name.lower() == df_lower

            if include:
                avail_spots = date_info['availability']['available_spots']
                available_djs = list(date_info['availability']['available_booking'])
                # Add Stefano MAYBE
                sv = date_info['selected_data'].get('Stefano', '')
                sc = str(sv).replace(" (BOLD)", "").strip() if sv else ""
                if not sc and 'Stefano' not in available_djs:
                    available_djs.append('Stefano [MAYBE]')
                results.append({
                    'date': date_info['date'],
                    'spots': avail_spots,
                    'djs': available_djs,
                })

        st.markdown("---")
        st.markdown(f"**{len(results)} dates** in range {start_str} to {end_str}")

        if not results:
            st.info("No dates found matching criteria.")
        else:
            for r in results:
                dj_list = f" ({', '.join(r['djs'])})" if r['djs'] else ""
                if r['spots'] == 0:
                    st.markdown(f":red[{r['date']}: {r['spots']} spot(s) available{dj_list}]")
                elif r['spots'] == 1:
                    st.markdown(f":orange[{r['date']}: {r['spots']} spot(s) available{dj_list}]")
                else:
                    st.markdown(f":green[{r['date']}: {r['spots']} spot(s) available{dj_list}]")


# ── Tab: Min Availability ─────────────────────────────────────────────────────

def tab_min_availability(year, service, spreadsheet, spreadsheet_id):
    """Find dates with minimum available spots."""

    col1, col2, col3, col4, col5 = st.columns([1, 1, 0.7, 1, 1])
    with col1:
        start_str = st.text_input("Start (MM-DD)", placeholder="06-01", key="min_start")
    with col2:
        end_str = st.text_input("End (MM-DD)", placeholder="09-30", key="min_end")
    with col3:
        min_spots = st.number_input("Min Spots", min_value=0, max_value=5, value=1, key="min_spots")
    with col4:
        day_filter = st.selectbox("Day Filter", ["All Days", "Saturday", "Sunday", "Weekend", "Weekday"], key="min_filter")
    with col5:
        st.write("")
        st.write("")
        search = st.button("Search", type="primary", key="min_search")

    if search and start_str and end_str:
        try:
            start_date = datetime.strptime(f"{year}-{start_str}", "%Y-%m-%d")
            end_date = datetime.strptime(f"{year}-{end_str}", "%Y-%m-%d")
        except ValueError:
            st.error("Invalid date format. Use MM-DD (e.g., 06-01).")
            return

        if start_date > end_date:
            st.error("Start date must be before end date.")
            return

        df = day_filter if day_filter != "All Days" else None

        with st.spinner('Fetching data...'):
            all_data = get_bulk_availability_data(year, service, spreadsheet, spreadsheet_id, start_date, end_date)

        if all_data is None:
            st.error(f"Error fetching data from {year} sheet.")
            return

        results = []
        for date_info in all_data:
            date_obj = date_info['date_obj']
            day_name = calendar.day_name[date_obj.weekday()]
            include = True

            if df:
                df_lower = df.lower()
                if df_lower == "weekend":
                    include = date_obj.weekday() >= 5
                elif df_lower == "weekday":
                    include = date_obj.weekday() < 5
                else:
                    include = day_name.lower() == df_lower

            if include:
                avail_spots = date_info['availability']['available_spots']
                if avail_spots >= min_spots:
                    available_djs = list(date_info['availability']['available_booking'])
                    sv = date_info['selected_data'].get('Stefano', '')
                    sc = str(sv).replace(" (BOLD)", "").strip() if sv else ""
                    if not sc and 'Stefano' not in available_djs:
                        available_djs.append('Stefano [MAYBE]')
                    results.append({
                        'date': date_info['date'],
                        'spots': avail_spots,
                        'djs': available_djs,
                    })

        st.markdown("---")
        st.markdown(f"**{len(results)} dates** with {min_spots}+ spot(s) in range {start_str} to {end_str}")

        if not results:
            st.info("No dates found matching criteria.")
        else:
            for r in results:
                dj_list = f" ({', '.join(r['djs'])})" if r['djs'] else ""
                if r['spots'] == 1:
                    st.markdown(f":orange[{r['date']}: {r['spots']} spot(s) available{dj_list}]")
                else:
                    st.markdown(f":green[{r['date']}: {r['spots']} spot(s) available{dj_list}]")


# ── Tab: DJ Availability ──────────────────────────────────────────────────────

def tab_dj_availability(year, service, spreadsheet, spreadsheet_id):
    """Check a specific DJ's availability across a date range."""

    dj_names = ["Henry", "Woody", "Paul", "Stefano", "Felipe"]
    if int(year) >= 2027:
        dj_names.append("Stephanie")

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        dj_name = st.selectbox("DJ", dj_names, key="dj_select")
    with col2:
        start_str = st.text_input("Start (MM-DD)", placeholder="06-01", key="dj_start")
    with col3:
        end_str = st.text_input("End (MM-DD)", placeholder="09-30", key="dj_end")
    with col4:
        st.write("")
        st.write("")
        search = st.button("Search", type="primary", key="dj_search")

    if search and start_str and end_str:
        auto_clear_stale_cache(60)

        try:
            start_date = datetime.strptime(f"{year}-{start_str}", "%Y-%m-%d")
            end_date = datetime.strptime(f"{year}-{end_str}", "%Y-%m-%d")
        except ValueError:
            st.error("Invalid date format. Use MM-DD (e.g., 06-01).")
            return

        if start_date > end_date:
            st.error("Start date must be before end date.")
            return

        with st.spinner(f'Checking {dj_name} availability...'):
            all_data = get_bulk_availability_data(year, service, spreadsheet, spreadsheet_id, start_date, end_date)

        if all_data is None:
            st.error(f"Error fetching data from {year} sheet.")
            return

        available_dates = []
        booked_date_infos = []
        backup_dates = []

        for date_info in all_data:
            if dj_name not in date_info['selected_data']:
                continue
            value = date_info['selected_data'][dj_name]
            is_bold = date_info['bold_status'].get(dj_name, False)
            clean_value = str(value).replace(" (BOLD)", "") if value else ""
            vl = clean_value.lower()

            if "booked" in vl or vl == "stanford" or vl == "reserved":
                booked_date_infos.append(date_info)
            elif "backup" in vl:
                backup_dates.append(date_info['date'])
            else:
                if dj_name == "Stefano" and (not clean_value or clean_value == ""):
                    available_dates.append(f"{date_info['date']} [MAYBE]")
                else:
                    can_book, can_backup = check_dj_availability(
                        dj_name, clean_value, date_info['date_obj'], is_bold, year, warn=False
                    )
                    if can_book:
                        available_dates.append(date_info['date'])

        # Look up venues for booked dates
        booked_dates = []
        if booked_date_infos:
            for date_info in booked_date_infos:
                month_day = date_info['date_obj'].strftime("%m-%d")
                gig_bk = get_gig_database_bookings(year, month_day)
                assigned = gig_bk.get('assigned', {})
                if dj_name in assigned:
                    venue = assigned[dj_name].get('venue', '')
                    booked_dates.append(f"{date_info['date']} ({venue})" if venue else date_info['date'])
                else:
                    booked_dates.append(date_info['date'])

        st.markdown("---")
        st.subheader(f"🎧 {dj_name} — {year}")
        st.markdown(f"Date range: {start_str} to {end_str}")

        st.markdown("---")
        st.markdown(f":green[**AVAILABLE FOR BOOKING ({len(available_dates)} dates):**]")
        if available_dates:
            for d in available_dates:
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{d}")
        else:
            st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;*None*")

        st.markdown(f":red[**BOOKED ({len(booked_dates)} dates):**]")
        if booked_dates:
            for d in booked_dates:
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{d}")
        else:
            st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;*None*")

        st.markdown(f":blue[**BACKUP ({len(backup_dates)} dates):**]")
        if backup_dates:
            for d in backup_dates:
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{d}")
        else:
            st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;*None*")


# ── Tab: Fully Booked Dates ──────────────────────────────────────────────────

def tab_fully_booked(year, service, spreadsheet, spreadsheet_id):
    """List all fully booked dates in a range."""

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        start_str = st.text_input("Start (MM-DD)", value="01-01", key="booked_start")
    with col2:
        end_str = st.text_input("End (MM-DD)", value="12-31", key="booked_end")
    with col3:
        st.write("")
        st.write("")
        search = st.button("Search", type="primary", key="booked_search")

    if search and start_str and end_str:
        try:
            start_date = datetime.strptime(f"{year}-{start_str}", "%Y-%m-%d")
            end_date = datetime.strptime(f"{year}-{end_str}", "%Y-%m-%d")
        except ValueError:
            st.error("Invalid date format. Use MM-DD (e.g., 01-01).")
            return

        if start_date > end_date:
            st.error("Start date must be before end date.")
            return

        with st.spinner('Scanning for fully booked dates...'):
            fully_booked = get_fully_booked_dates(year, service, spreadsheet, spreadsheet_id, start_date, end_date)

        if fully_booked is None:
            st.error(f"Error fetching data from {year} sheet.")
            return

        st.markdown("---")

        if not fully_booked:
            st.success("No fully booked dates found in this range!")
            return

        st.markdown(f":red[**Found {len(fully_booked)} fully booked date(s):**]")

        for booking in fully_booked:
            with st.expander(f"🚫 {booking['date']}", expanded=True):
                if booking.get('booked_djs'):
                    st.markdown(f":red[**Booked:** {', '.join(booking['booked_djs'])}]")

                tba = booking['availability']['tba_bookings']
                if tba > 0:
                    st.markdown(f":red[**TBA Bookings:** {tba}]")

                if booking.get('aag_status'):
                    aag = booking['aag_status']
                    if 'reserved' in aag.lower():
                        st.markdown(f":red[**AAG:** {aag}]")
                    else:
                        st.markdown(f"**AAG:** {aag}")

                if booking.get('backup_assigned'):
                    st.markdown(f":blue[**Backup Assigned:** {', '.join(booking['backup_assigned'])}]")

                if booking.get('available_to_book'):
                    st.markdown(f":green[**Available to Book:** {', '.join(booking['available_to_book'])}]")

                if not booking.get('backup_assigned') and booking.get('available_to_backup'):
                    st.markdown(f"**Available to Backup:** {', '.join(booking['available_to_backup'])}")

        st.markdown("---")
        st.caption("💡 Review your open inquiries for these dates to notify couples.")
        st.caption("[MAYBE] = Stefano blank cell — may be available if asked.")


def tab_turned_away(year, client):
    """Tab 6: Turned-away inquiries for a specific date."""
    st.subheader("Turned-Away Inquiries")
    st.caption("Search for inquiries where we were full on a specific date.")

    col1, col2 = st.columns([1, 3])
    with col1:
        date_input = st.text_input("Date (MM-DD)", key="turned_away_date", placeholder="07-05")

    if st.button("Search", key="turned_away_btn"):
        if not date_input:
            st.warning("Please enter a date.")
            return

        # Validate date
        try:
            datetime.strptime(f"{year}-{date_input}", "%Y-%m-%d")
        except ValueError:
            st.error("Invalid date format. Use MM-DD (e.g., 07-05).")
            return

        with st.spinner("Searching inquiry tracker..."):
            results = get_full_inquiries_for_date(date_input, client, year=int(year))

        if results:
            st.markdown(f"Found **{len(results)}** turned-away inquiry(ies) for {date_input}:")
            for i, r in enumerate(results, 1):
                tier = r.get('tier', 3)
                age = r.get('inquiry_age_label', '')
                age_str = f" ({age})" if age else ""

                if tier == 1:
                    tag = ":green[REACH OUT]"
                    venue_color = f":green[**{i}. {r['venue']}**]"
                elif tier == 2:
                    tag = ":orange[MAYBE]"
                    venue_color = f":orange[**{i}. {r['venue']}**]"
                else:
                    tag = "STALE"
                    venue_color = f"~~{i}. {r['venue']}~~"

                with st.container():
                    st.markdown(f"{venue_color} {tag}")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.caption(f"Inquiry: {r['inquiry_date']}{age_str}")
                    with col_b:
                        st.caption(f"Decision: {r['decision_date']}")
                    st.divider()
        else:
            st.info(f"No turned-away inquiries found for {date_input}.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.title("🎵 DJ Availability Checker")

    # Year selection in sidebar
    with st.sidebar:
        year = st.selectbox("Year", ["2026", "2027"], index=0)

        st.markdown("---")
        st.markdown("### 🎨 Status Colors")
        st.markdown("""
        - :red[**Red**] = Booked / Unavailable
        - :blue[**Blue**] = Backup assigned
        - :green[**Green**] = Available
        - :orange[**Orange**] = Maybe / Unknown
        """)

        st.markdown("---")
        st.markdown("### ✨ Features")
        st.markdown("""
        - **Venue Names** from gig database
        - **Nearby Bookings** (±3 days)
        - **Venue Inquiries** tracking
        - **AAG Reserved** spots
        - **Stefano [MAYBE]** indicators
        - **Unknown status** warnings
        """)

    # Get sheets connection
    service, spreadsheet, spreadsheet_id, client = get_sheets_connection()

    # Tabs for each query type
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📅 Check Date",
        "📊 Date Range",
        "🔍 Min. Availability",
        "🎧 DJ Availability",
        "🚫 Fully Booked",
        "📋 Turned Away",
    ])

    with tab1:
        tab_check_date(year, service, spreadsheet, spreadsheet_id, client)

    with tab2:
        tab_date_range(year, service, spreadsheet, spreadsheet_id)

    with tab3:
        tab_min_availability(year, service, spreadsheet, spreadsheet_id)

    with tab4:
        tab_dj_availability(year, service, spreadsheet, spreadsheet_id)

    with tab5:
        tab_fully_booked(year, service, spreadsheet, spreadsheet_id)

    with tab6:
        tab_turned_away(year, client)


if __name__ == "__main__":
    main()
