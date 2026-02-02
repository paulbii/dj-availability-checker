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
				MailCoordinator: typeof MailCoordinator !== 'undefined' ? MailCoordinator : ''
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
	
	-- Path to Python script (same directory as this AppleScript)
	set scriptDir to "/Users/paulburchfield/Documents/projects/dj-availability-checker"
	set pythonScript to scriptDir & "/gig_booking_manager.py"
	
	-- Run the Python script
	try
		set shellCmd to "cd " & quoted form of scriptDir & " && python3 " & quoted form of pythonScript & " " & quoted form of jsonPath & extraFlags & " 2>&1"
		set scriptOutput to do shell script shellCmd
		
		-- Log output (visible in Console.app)
		log scriptOutput
		
	on error errMsg number errNum
		display dialog "Booking Manager encountered an error:" & return & return & errMsg with title "⚠️ Booking Manager Error" buttons {"OK"} with icon stop
	end try
end run
