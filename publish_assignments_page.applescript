-- Stream Deck: rebuild and upload the DJ assignments page (bigfundj.com/CLIENTS/assignments/2027/).
-- Run through ~/bin/dj-checker-button publish_assignments_page.scpt
set wrapper to "/Users/paulburchfield/EA/projects/dj-capacity-2027/run_assignments_page.sh"
try
	set output to do shell script wrapper
	set lastLine to last paragraph of output
	display dialog "Assignments page updated." & return & return & lastLine with title "DJ Assignments" buttons {"OK"} default button 1 giving up after 20
on error errMsg
	display dialog "Assignments page NOT updated." & return & return & errMsg with title "DJ Assignments" buttons {"OK"} default button 1 with icon stop
	error number -128
end try
