# Desktop live sync (Windows)

## One-time setup

1. In your existing checkout, run `tools\SETUP-DESKTOP-KLIMAECO.cmd`.
2. The script creates `%USERPROFILE%\Desktop\KlimaEco` (or the Windows Desktop path) without overwriting an existing folder.
3. It uses Git Credential Manager/GitHub authentication already configured on Windows. Never put a password or token into the script.
4. A PowerShell window starts the sync watcher.

## How it works

- Edit files inside the Desktop `KlimaEco` folder.
- After edits settle, the watcher commits them and pushes to GitHub branch `desktop-sync` about every 15 seconds.
- The watcher periodically merges `master` and `desktop-sync` into the working branch, then pushes the result to `desktop-sync`.
- It never runs `git reset --hard`, `git clean`, or force-push.
- If a merge conflict, GitHub auth issue, or network failure occurs, it logs the error and retries. Resolve conflicts before continuing if they persist.
- Review changes in GitHub: https://github.com/klimatst/anviklimat/tree/desktop-sync

## Local site

- Full PHP/XAMPP package: `%USERPROFILE%\Desktop\KlimaEco\shared_hosting_php\START-LOCAL.cmd` (PHP engine uses port 4173).
- Lightweight Node preview: `%USERPROFILE%\Desktop\KlimaEco\local-site\START-LOCAL.cmd` (uses port 4173 unless the port-fix change is merged).
- The lightweight preview is not the full Anvil app/admin/CRM. It is for the demo UI only.
- XAMPP and PHP/MariaDB must be installed and configured locally.

## Safety

The watcher pushes only to `desktop-sync`, not directly to `master`. That keeps work visible in GitHub while preserving a review gate before changes become the primary branch. Never keep passwords, database dumps, real customer data, `.anvil-data`, or local secrets in tracked files.
