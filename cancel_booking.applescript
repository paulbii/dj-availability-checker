-- cancel_booking.scpt
--
-- Entry point for the Booking Cancellation script.
-- Extracts booking data from the current FileMaker page in Safari,
-- writes it to a temp JSON file, and calls cancel_booking.py.
--
-- Usage:
--   Production:  osascript cancel_booking.scpt
--   Dry run:     osascript cancel_booking.scpt --dry-run
--
-- Stream Deck:
--   osascript /Users/paulburchfield/Documents/projects/dj-availability-checker/cancel_booking.scpt

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
			display dialog "No Safari window is open." with title "Cancel Booking" buttons {"OK"} with icon stop
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
				MailCoordinator: typeof MailCoordinator !== 'undefined' ? MailCoordinator : ''
			})
		" in document 1
	end tell
	
	-- Validate we got data
	if pageSource is "" or pageSource is missing value then
		display dialog "Could not extract booking data from the current Safari page. Make sure a FileMaker booking record is open." with title "Cancel Booking" buttons {"OK"} with icon stop
		return
	end if
	
	-- Write JSON to temp file
	set jsonPath to "/tmp/gig_booking.json"
	set fileRef to open for access POSIX file jsonPath with write permission
	set eof of fileRef to 0
	write pageSource to fileRef as «class utf8»
	close access fileRef
	
	-- Path to Python script (same directory as this AppleScript)
	set scriptDir to "/Users/paulburchfield/Documents/projects/dj-availability-checker"
	set pythonScript to scriptDir & "/cancel_booking.py"
	
	-- Run the Python script headless (no Terminal window).
	-- The script surfaces its own results: a macOS notification on success
	-- and native dialogs for errors. Full output is logged for review.
	set logPath to "/tmp/bigfun-cancel-booking.log"
	-- One line per phase, each stamped with the clock time, so a slow run shows where
	-- the time went (tail -f the log). -u keeps Python unbuffered through the pipe;
	-- pipefail keeps Python's exit status so the failure notification still fires.
	do shell script "echo \"$(date +%T) Button pressed; Safari extraction took " & (round ((current date) - startedAt)) & "s; starting Python\" > " & quoted form of logPath
	set shellCmd to "cd " & quoted form of scriptDir & " && set -o pipefail; /Users/paulburchfield/Documents/projects/dj-availability-checker/.venv/bin/python -u " & quoted form of pythonScript & " " & quoted form of jsonPath & extraFlags & " 2>&1 | while IFS= read -r line; do printf '%s %s\n' \"$(date +%T)\" \"$line\"; done >> " & quoted form of logPath
	try
		do shell script shellCmd
	on error
		-- Non-zero exit. The Python script usually shows its own error dialog;
		-- this is a fallback so a silent failure never goes unnoticed.
		display notification "Cancellation did not complete. See " & logPath with title "⚠️ Cancel Booking"
	end try
end run


