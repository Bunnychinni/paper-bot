# Paper bot -- setup (one time, ~15 min)

1. Create a PRIVATE GitHub repo, e.g. `paper-bot`.
2. Upload the entire pkg folder contents (or push via git).
3. Repo Settings -> Secrets and variables -> Actions:
   - Secrets: APCA_API_KEY_ID, APCA_API_SECRET_KEY (PAPER keys), SEC_UA
   - Variables: TARGET = 2.5, STOP = 2.0
4. Actions tab -> enable workflows -> run "paper bot" once manually
   (workflow_dispatch) to verify. Check the log for "prereg" line.
5. Done. It runs ~9:35 ET (entries) and ~16:30 ET (protect/exit) every
   trading day and commits logbook.db back to the repo.

Kill switch: add a file named STOP to the repo root. Next run flattens
everything and refuses entries. Delete STOP to resume.

Weekly: open logbook.db (or run `python -c "import logbook,sqlite3;
logbook.print_progress(sqlite3.connect('logbook.db'))"`).
Look at fills vs intentions. Do NOT compute expectancy before 300
resolved trades -- section 5 of preregistration.md.
