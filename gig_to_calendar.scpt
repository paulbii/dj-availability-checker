(*
    Gig to Calendar
    
    Opens the current Safari page, extracts FileMaker booking data,
    and calls the Python script to check for conflicts and create
    a calendar event.
    
    Usage: 
    1. Open a booking record in Safari
    2. Run this script (double-click, or assign to keyboard shortcut/Stream Deck)
    
    Flags:
    --test    Route invites to paul@bigfundj.com
*)

on run argv
    -- Check for flags
    set testMode to false
    if (count of argv) > 0 then
        repeat with arg in argv
            if arg as text is "--test" then set testMode to true
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
    end tell
    
    -- Check if we got data
    if jsonResult is "" or jsonResult is "{}" then
        display alert "Could not extract booking data" message "Make sure you're on a FileMaker booking record page."
        return
    end if
    
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
    set cmd to "/Users/paulburchfield/miniconda3/bin/python3 " & quoted form of pythonScript & " " & quoted form of tempFile
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
