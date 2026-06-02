import subprocess
import time
from datetime import datetime
import shutil
import os

# ---------------- CONFIG ----------------
REPO_PATH = r"C:\Users\Administrator\OneDrive\Accessory_Contest_Dashboard"
FILES_TO_TRACK = [
    "Accessory_Contest.csv",
    "Accessory_Contest_Dashboard.py",
    "IDM_User_Codes.xlsx",
    "requirements.txt",
    "IDM_User_Codes.xlsx",
    "Login_Selection.py",
    "cookie.py"  # <-- track the copied cookie.py
]
CHECK_INTERVAL_SECONDS = 60  # 1 minute
COOKIE_SOURCE_PATH = r"C:\Users\Administrator\OneDrive\BDI_Scraper\cookie.py"
# ---------------------------------------

def copy_cookie():
    """Copy cookie.py from external folder into the repo before syncing."""
    dest_path = os.path.join(REPO_PATH, "cookie.py")
    try:
        shutil.copy2(COOKIE_SOURCE_PATH, dest_path)
        print(f"[{datetime.now()}] cookie.py copied to repo.")
    except Exception as e:
        print(f"[ERROR] Failed to copy cookie.py: {e}")

def run_git_command(command):
    """Run a git command in the repo folder and return the result."""
    return subprocess.run(
        command,
        cwd=REPO_PATH,
        shell=True,
        capture_output=True,
        text=True
    )

def has_changes():
    """Check if any of the tracked files have changes."""
    result = run_git_command("git status --porcelain")
    if result.returncode != 0:
        print(f"[ERROR] git status failed: {result.stderr}")
        return False

    changed_files = result.stdout.splitlines()
    for line in changed_files:
        file_path = line[3:].strip()  # Remove status prefix
        if file_path in FILES_TO_TRACK:
            return True
    return False

def sync_changes():
    """Add, commit, pull, and push changes for tracked files."""
    for file in FILES_TO_TRACK:
        run_git_command(f'git add "{file}"')

    commit_message = f"Auto-sync update {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"
    commit_result = run_git_command(f'git commit -m "{commit_message}"')

    if "nothing to commit" in commit_result.stdout.lower():
        print(f"[{datetime.now()}] Nothing to commit.")
        return

    # Pull remote changes first
    pull_result = run_git_command("git pull --rebase origin main")
    if pull_result.returncode != 0:
        print(f"[ERROR] git pull failed: {pull_result.stderr}")
        return

    # Push changes
    push_result = run_git_command("git push origin main")
    if push_result.returncode == 0:
        print(f"[{datetime.now()}] Changes committed and pushed successfully.")
    else:
        print(f"[ERROR] git push failed: {push_result.stderr}")

def main():
    print("Auto Git Sync Service Started")
    print("Monitoring files...")

    while True:
        try:
            # Copy cookie.py before checking for changes
            copy_cookie()

            if has_changes():
                sync_changes()
            else:
                print(f"[{datetime.now()}] No changes detected.")

        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
