-- stefano_maxed_enforcer.scpt
--
-- Runs the Stefano MAXED Enforcer for 2026.
-- Scans Stefano's availability column, applies booking rules,
-- and suggests dates to mark as MAXED.
--
-- Usage:
--   osascript stefano_maxed_enforcer.scpt
--
-- Stream Deck:
--   osascript /Users/paulburchfield/Documents/projects/dj-availability-checker/stefano_maxed_enforcer.scpt

on run argv
	set scriptDir to "/Users/paulburchfield/Documents/projects/dj-availability-checker"
	set pythonScript to scriptDir & "/stefano_maxed_enforcer.py"

	try
		set shellCmd to "cd " & quoted form of scriptDir & " && /Users/paulburchfield/miniconda3/bin/python3 " & quoted form of pythonScript & " --year 2026"

		tell application "Terminal"
			activate
			do script shellCmd
		end tell

	on error errMsg number errNum
		display dialog "Stefano MAXED Enforcer encountered an error:" & return & return & errMsg with title "⚠️ Stefano Enforcer Error" buttons {"OK"} with icon stop
	end try
end run
