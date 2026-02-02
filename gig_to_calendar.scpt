#!/usr/bin/osascript
(*
    Gig to Calendar - Safari Version (with Conflict Check)
    
    Opens the current Safari page, extracts FileMaker booking data,
    checks for DJ scheduling conflicts in the Gigs calendar,
    and creates a calendar event.
    
    Usage: 
    1. Open a booking record in Safari
    2. Run this script (double-click, or assign to keyboard shortcut/Stream Deck)
    
    Flags:
    --test    Route invites to paul@bigfundj.com
    --force   Skip conflict check and create event directly
*)

on run argv
    -- Check for flags
    set testMode to false
    set forceCreate to false
    if (count of argv) > 0 then
        repeat with arg in argv
            if arg as text is "--test" then set testMode to true
            if arg as text is "--force" then set forceCreate to true
        end repeat
    end if
    
    -- Extract FM variables from Safari via JavaScript
    tell application "Safari"
        if (count of windows) is 0 then
            display alert "No Safari window open"
            return
        end if
        
        set currentTab to current tab of front window
        
        -- Extract full JSON for Python
        set jsCode to "
            (function() {
                var data = {
                    FMeventDate: typeof FMeventDate !== 'undefined' ? FMeventDate : '',
                    FMstartTime: typeof FMstartTime !== 'undefined' ? FMstartTime : '',
                    FMendTime: typeof FMendTime !== 'undefined' ? FMendTime : '',
                    FMclient: typeof FMclient !== 'undefined' ? FMclient : '',
                    FMvenue: typeof FMvenue !== 'undefined' ? FMvenue : '',
                    FMvenueAddress: typeof FMvenueAddress !== 'undefined' ? FMvenueAddress : '',
                    FMDJ1: typeof FMDJ1 !== 'undefined' ? FMDJ1 : '',
                    FMDJ2: typeof FMDJ2 !== 'undefined' ? FMDJ2 : '',
                    FMsound: typeof FMsound !== 'undefined' ? FMsound : '',
                    FMcersound: typeof FMcersound !== 'undefined' ? FMcersound : '0',
                    MailCoordinator: typeof MailCoordinator !== 'undefined' ? MailCoordinator : ''
                };
                return JSON.stringify(data);
            })();
        "
        set jsonResult to do JavaScript jsCode in currentTab
        
        -- Extract DJ name and event date separately for conflict check
        set djFullName to do JavaScript "typeof FMDJ1 !== 'undefined' ? FMDJ1 : ''" in currentTab
        set eventDateStr to do JavaScript "typeof FMeventDate !== 'undefined' ? FMeventDate : ''" in currentTab
    end tell
    
    -- Check if we got data
    if jsonResult is "" or jsonResult is "{}" then
        display alert "Could not extract booking data" message "Make sure you're on a FileMaker booking record page."
        return
    end if
    
    -- === CONFLICT CHECK ===
    
    -- Determine DJ first name (safely handle empty string)
    if djFullName is "" or djFullName is "Unknown" then
        set djFirstName to "Unknown"
    else if djFullName is "Unassigned" then
        set djFirstName to "Unassigned"
    else
        set djFirstName to first word of djFullName
    end if
    
    -- Map DJ name to initials (mirrors DJ_INITIALS in gig_to_calendar.py)
    set djInitials to "??"
    if djFirstName is "Henry" then
        set djInitials to "HK"
    else if djFirstName is "Woody" then
        set djInitials to "WM"
    else if djFirstName is "Paul" then
        set djInitials to "PB"
    else if djFirstName is "Stefano" then
        set djInitials to "SB"
    else if djFirstName is "Felipe" then
        set djInitials to "FS"
    else if djFirstName is "Stephanie" then
        set djInitials to "SD"
    end if
    
    -- Skip conflict check for unassigned/unknown DJs (multiple unassigned
    -- events on the same date is normal) or when --force is used
    set skipConflictCheck to false
    if djFirstName is "Unknown" or djFirstName is "Unassigned" then
        set skipConflictCheck to true
    end if
    
    if not skipConflictCheck and not forceCreate and eventDateStr is not "" then
        set searchPrefix to "[" & djInitials & "]"
        
        -- Parse event date and set to midnight for day-boundary comparison
        set eventDate to date eventDateStr
        set time of eventDate to 0
        set dayEnd to eventDate + 86400 -- +24 hours (seconds)
        
        -- Query Gigs calendar for events on this date with matching DJ prefix
        set conflictEvents to {}
        tell application "Calendar"
            tell calendar "Gigs"
                set dayEvents to (every event whose start date ≥ eventDate and start date < dayEnd)
                repeat with evt in dayEvents
                    set evtTitle to summary of evt
                    if evtTitle starts with searchPrefix then
                        set evtStart to start date of evt
                        set evtEnd to end date of evt
                        
                        -- Format time display
                        if (time of evtStart) is 0 and (evtEnd - evtStart) ≥ 86400 then
                            -- All-day event
                            set timeDisplay to "All Day"
                        else
                            -- Timed event — format as "4:00 PM – 11:00 PM"
                            set timeDisplay to my formatTime(evtStart) & " – " & my formatTime(evtEnd)
                        end if
                        
                        set end of conflictEvents to {evtTitle, timeDisplay}
                    end if
                end repeat
            end tell
        end tell
        
        -- Show warning dialog if conflicts found
        if (count of conflictEvents) > 0 then
            set conflictCount to count of conflictEvents
            if conflictCount is 1 then
                set countWord to "1 existing event"
            else
                set countWord to (conflictCount as text) & " existing events"
            end if
            
            set warningMsg to "⚠️ " & djFirstName & " has " & countWord & " on this date:" & return & return
            repeat with conflict in conflictEvents
                set warningMsg to warningMsg & "  • " & item 1 of conflict & return
                set warningMsg to warningMsg & "    " & item 2 of conflict & return & return
            end repeat
            set warningMsg to warningMsg & "Create the new event anyway?"
            
            tell application "System Events" to set frontmost of process "osascript" to true
            set userChoice to display dialog warningMsg buttons {"Cancel", "Create Anyway"} default button "Cancel" with icon caution with title "DJ Calendar Conflict"
            if button returned of userChoice is "Cancel" then
                display notification "Event creation cancelled" with title "Gig to Calendar"
                return
            end if
        end if
    end if
    
    -- === CREATE EVENT (existing flow, unchanged) ===
    
    -- Write JSON to temp file
    set tempFile to "/tmp/gig_booking.json"
    do shell script "echo " & quoted form of jsonResult & " > " & tempFile
    
    -- Find Python script
    set scriptPaths to {¬
        "/Users/paulburchfield/Documents/projects/dj-availability-checker/gig_to_calendar.py", ¬
        "~/scripts/gig_to_calendar.py", ¬
        "~/gig_to_calendar.py", ¬
        "./gig_to_calendar.py"¬
    }
    
    set pythonScript to ""
    repeat with scriptPath in scriptPaths
        set expandedPath to do shell script "echo " & scriptPath
        try
            do shell script "test -f " & quoted form of expandedPath
            set pythonScript to expandedPath
            exit repeat
        end try
    end repeat
    
    if pythonScript is "" then
        display alert "Python script not found" message "Place gig_to_calendar.py in ~/scripts/ or ~/"
        return
    end if
    
    -- Build and run command
    set cmd to "python3 " & quoted form of pythonScript & " " & quoted form of tempFile
    if testMode then
        set cmd to cmd & " --test"
    end if
    
    try
        set output to do shell script cmd
        display notification output with title "Calendar Event Created"
    on error errMsg
        display alert "Failed to create event" message errMsg
    end try
    
end run


-- Helper: format an AppleScript date's time as "4:00 PM"
on formatTime(d)
    set h to (time of d) div 3600
    set m to ((time of d) mod 3600) div 60
    
    if h > 12 then
        set h to h - 12
        set p to "PM"
    else if h is 12 then
        set p to "PM"
    else if h is 0 then
        set h to 12
        set p to "AM"
    else
        set p to "AM"
    end if
    
    if m < 10 then
        set mStr to "0" & (m as text)
    else
        set mStr to m as text
    end if
    
    return (h as text) & ":" & mStr & " " & p
end formatTime
