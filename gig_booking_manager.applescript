-- gig_booking_manager.scpt
--
-- Entry point for the Gig Booking Manager.
-- Extracts booking data from the current FileMaker page in Safari,
-- writes it to a temp JSON file, and calls the Python script.
--
-- Usage:
--   Production:  osascript gig_booking_manager.scpt
--   Test mode:   osascript gig_booking_manager.scpt --dry-run
--
-- Stream Deck / Keyboard Maestro:
--   osascript osascript /Users/paulburchfield/Documents/projects/dj-availability-checker/gig_booking_manager.scpt

on run argv
	set startedAt to current date
	-- Determine flags from command-line arguments
	set extraFlags to ""
	repeat with arg in argv
		if arg as text is "--dry-run" then
			set extraFlags to extraFlags & " --dry-run"
		else if arg as text is "--test" then
			set extraFlags to extraFlags & " --test"
		end if
	end repeat
	
	-- Extract booking data from Safari
	tell application "Safari"
		if (count of documents) is 0 then
			display dialog "No Safari window is open." with title "Booking Manager" buttons {"OK"} with icon stop
			return
		end if
		
		set pageSource to do JavaScript "
			JSON.stringify({
				FMeventDate: typeof FMeventDate !== 'undefined' ? FMeventDate : '',
				FMstartTime: typeof FMstartTime !== 'undefined' ? FMstartTime : '',
				FMendTime: typeof FMendTime !== 'undefined' ? FMendTime : '',
				FMclient: typeof FMclient !== 'undefined' ? FMclient : '',
				FMvenue: typeof FMvenue !== 'undefined' ? FMvenue : '',
				FMvenueAddress: typeof FMvenueAddress !== 'undefined' ? FMvenueAddress : '',
				FMDJ1: typeof FMDJ1 !== 'undefined' ? FMDJ1 : '',
				FMDJ2: typeof FMDJ2 !== 'undefined' ? FMDJ2 : '',
				FMsound: typeof FMsound !== 'undefined' ? FMsound : '',
				FMcersound: typeof FMcersound !== 'undefined' ? FMcersound : '',
				MailCoordinator: typeof MailCoordinator !== 'undefined' ? MailCoordinator : '',
				FMemail1: (function() { var el = document.editform ? document.editform['BookingContact1::IDEmail'] : null; return el ? el.value : ''; })(),
				FMeventType: (function() { var el = document.editform ? document.editform['eventType'] : null; return el ? el.options[el.selectedIndex].text : ''; })()
			})
		" in document 1
	end tell
	
	-- Validate we got data
	if pageSource is "" or pageSource is missing value then
		display dialog "Could not extract booking data from the current Safari page. Make sure a FileMaker booking record is open." with title "Booking Manager" buttons {"OK"} with icon stop
		return
	end if
	
	-- Write JSON to temp file
	set jsonPath to "/tmp/gig_booking.json"
	set fileRef to open for access POSIX file jsonPath with write permission
	set eof of fileRef to 0
	write pageSource to fileRef as «class utf8»
	close access fileRef

	-- The whole page too, for dj-prep's music link (the same read the DJ Prep
	-- Music link button does). A failed read only skips the music step.
	set fmHtmlPath to "/tmp/gig_booking_fm.html"
	set fmHtmlFlag to ""
	try
		tell application "Safari" to set fmHTML to do JavaScript "document.documentElement.outerHTML" in document 1
		set htmlRef to open for access POSIX file fmHtmlPath with write permission
		set eof of htmlRef to 0
		write fmHTML to htmlRef as «class utf8»
		close access htmlRef
		set fmHtmlFlag to " --fm-html " & quoted form of fmHtmlPath
	end try
	
	-- Path to Python script (same directory as this AppleScript)
	set scriptDir to "/Users/paulburchfield/Documents/projects/dj-availability-checker"
	set pythonScript to scriptDir & "/gig_booking_manager.py"
	
	-- Run the Python script headless (no Terminal window).
	-- The script surfaces its own results: a macOS notification on success
	-- and native dialogs for conflicts/errors. Full output is logged for review.
	set logPath to "/tmp/bigfun-gig-booking.log"
	-- One line per phase, each stamped with the clock time, so a slow run shows where
	-- the time went (tail -f the log). -u keeps Python unbuffered through the pipe;
	-- pipefail keeps Python's exit status so the failure notification still fires.
	do shell script "echo \"$(date +%T) Button pressed; Safari extraction took " & (round ((current date) - startedAt)) & "s; starting Python\" > " & quoted form of logPath
	set shellCmd to "cd " & quoted form of scriptDir & " && set -o pipefail; /Users/paulburchfield/Documents/projects/dj-availability-checker/.venv/bin/python -u " & quoted form of pythonScript & " " & quoted form of jsonPath & extraFlags & fmHtmlFlag & " 2>&1 | while IFS= read -r line; do printf '%s %s\n' \"$(date +%T)\" \"$line\"; done >> " & quoted form of logPath
	try
		do shell script shellCmd
	on error
		-- Non-zero exit. The Python script usually shows its own error dialog;
		-- this is a fallback so a silent failure never goes unnoticed.
		display notification "Booking did not complete. See " & logPath with title "⚠️ Booking Manager"
	end try
end run


