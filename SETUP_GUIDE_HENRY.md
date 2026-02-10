# DJ Availability Checker — Setup Guide for Henry

This guide walks you through setting up and running the DJ Availability Checker terminal tool on your Mac. It takes about 10 minutes.

---

## What You'll Be Able to Do

Once set up, you'll have two commands you can run in Terminal:

- `python3 check_2026.py` — check DJ availability for 2026
- `python3 check_2027.py` — check DJ availability for 2027

Each one gives you an interactive menu where you can:

1. Check a specific date
2. Query a date range
3. Find dates with minimum available spots
4. Check a specific DJ's availability over a range
5. List all fully booked dates

The tool pulls live data from our Google Sheets availability matrix and the FileMaker gig database.

---

## Step 1: Check That Python 3 Is Installed

Open **Terminal** (search for "Terminal" in Spotlight, or find it in Applications → Utilities).

Type this and press Enter:

```
python3 --version
```

You should see something like `Python 3.12.4` or similar. Any version 3.9 or higher is fine.

**If you get "command not found":** Go to https://www.python.org/downloads/ and download the latest Python for macOS. Run the installer, then try the command again.

---

## Step 2: Get the Project Files

Paul will send you a folder (or zip file) containing these files:

```
dj-availability-checker/
├── check_2026.py          ← entry point for 2026
├── check_2027.py          ← entry point for 2027
├── check_dj.py            ← terminal interface
├── dj_core.py             ← core logic
├── your-credentials.json  ← Google Sheets access (see below)
└── requirements.txt       ← list of dependencies
```

Put this folder somewhere convenient, like:

```
~/Documents/dj-availability-checker/
```

(That's your Documents folder → a subfolder called `dj-availability-checker`.)

---

## Step 3: The Credentials File

The file `your-credentials.json` is what allows the tool to read our Google Sheets. Paul will include a copy in the folder he sends you.

**Important:** This file only grants access to the two specific DJ spreadsheets (the availability matrix and the inquiry tracker). It does not have access to anyone's personal Google account or other files.

Keep this file in the same folder as the Python scripts. Don't share it outside the team.

---

## Step 4: Install Dependencies

In Terminal, navigate to the folder and install the required packages:

```
cd ~/Documents/dj-availability-checker
pip3 install gspread oauth2client google-api-python-client colorama requests
```

If you get a permissions error, try:

```
pip3 install --user gspread oauth2client google-api-python-client colorama requests
```

Or if your Mac uses a newer Python that's more strict:

```
pip3 install --break-system-packages gspread oauth2client google-api-python-client colorama requests
```

Only one of these needs to work — try them in order.

---

## Step 5: Run It

Still in Terminal, from the project folder:

```
cd ~/Documents/dj-availability-checker
python3 check_2026.py
```

You should see:

```
DJ Availability Checker - 2026

==================================================
DJ AVAILABILITY CHECKER
==================================================
1. Check specific date
2. Query date range
3. Find dates with minimum availability
4. Check DJ availability in range
5. List fully booked dates
6. Exit
==================================================

Select an option (1-6):
```

To check 2027 instead, run `python3 check_2027.py`.

---

## Quick Usage Examples

**Check a specific date:**
- Select option 1
- Enter a date like `09-20` (that's September 20)
- You'll see each DJ's status with color coding: green = available, red = booked, blue = backup, yellow = maybe

**See all availability for a month of Saturdays:**
- Select option 2
- Start date: `10-01`
- End date: `10-31`
- Filter: `Saturday`

**Check when a specific DJ is free:**
- Select option 4
- Enter the DJ name (e.g., `Woody`)
- Enter a date range

**Find fully booked dates:**
- Select option 5
- Enter a date range (or press Enter twice to check the whole year)

---

## Troubleshooting

**"ModuleNotFoundError: No module named 'gspread'"**
The packages didn't install correctly. Re-run the pip3 install command from Step 4.

**"FileNotFoundError: your-credentials.json"**
Make sure you're running the command from inside the project folder (`cd ~/Documents/dj-availability-checker` first), and that the credentials file is in that folder.

**"gspread.exceptions.SpreadsheetNotFound"**
The credentials file may be wrong or the Google Sheets haven't been shared with the service account. Let Paul know.

**Colors look weird or show escape codes**
Your Terminal should handle colors fine by default on macOS. If you see codes like `[32m` instead of colors, try using the default Terminal app rather than a third-party one.

**"python3: command not found"**
Python 3 isn't installed. See Step 1.

---

## Day-to-Day Use

Once everything is set up, your daily workflow is just:

```
cd ~/Documents/dj-availability-checker
python3 check_2026.py
```

That's it. The tool reads live data each time you run it, so you're always seeing the current state of the availability matrix and gig database.
