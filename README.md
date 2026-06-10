# Time Tracker

A lightweight desktop time-tracking application built for **ServiceNow** reporting at BitHawk AG.  
No external dependencies — only Python 3 and its built-in `tkinter` library are required.

---

## Features

- **Start / stop timers** per category with a single click
- **Category management** — custom colours, optional ServiceNow task numbers, drag-free reorder
- **Category archiving** — hide finished projects from the start list without losing their history
- **Manual entries** — forgot the timer? Add a past entry via **Eintraege → + Nachtragen**
- **Daily target** — progress display in the header (default 8.2 h, configurable)
- **Tracking reminder** — a hint appears if no timer is running for a while during work hours
- **List and grid view** — toggle between a compact list and a 2-column card grid
- **Mini-bar mode** — collapses to a slim always-on-top strip so it stays out of the way
- **Always-on-top pin** — keep the window above all other applications
- **Idle detection** — prompts you on return after 10 minutes of inactivity, letting you decide what to do with the idle time
- **HTML report** — generates a filterable, searchable journal report for a chosen date range
- **Configurable data location** — store your data on OneDrive or a network share for automatic sync; change it at any time via the **📁 Daten** menu
- **Atomic JSON persistence** with a rolling `.bak` backup — safe against sudden power loss or crashes

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.8 or newer |
| tkinter | Included with the standard Python installer on Windows |

> **Note:** On some minimal Linux installations, `tkinter` must be installed separately  
> (e.g. `sudo apt install python3-tk`). On macOS, use the official python.org installer  
> which bundles `tkinter`; the Homebrew version may not include it.

---

## Running from source

### Windows — double-click launcher

Double-click **`start.bat`**. It checks that Python is available and launches the application.  
If Python is not found you will be prompted to install it from <https://www.python.org/downloads/>.

### Any platform — command line

```bash
python timetracker.py
```

### First start

On the very first run a folder-picker dialog appears.  
Choose where `timetracker_data.json` should be stored.  
**Tip:** pick a OneDrive or network folder to get automatic synchronisation across machines.  
This choice is saved to `~/.timetracker_config.json` and is not asked again.

---

## Building a standalone `.exe` (Windows)

The included `TimeTracker.spec` file configures [PyInstaller](https://pyinstaller.org) to produce a  
single-file executable that requires no Python installation on the target machine.

1. Install PyInstaller (one-time):
   ```bash
   pip install pyinstaller
   ```

2. Build the executable from the project root:
   ```bash
   pyinstaller TimeTracker.spec
   ```

3. The finished binary is placed at:
   ```
   dist\TimeTracker.exe
   ```

> The `.exe` bundles `stopwatch.ico` and all required standard-library modules.  
> `build\` and `dist\` are excluded from version control via `.gitignore`.

---

## Usage guide

### Main window

| Area | Description |
|---|---|
| **Status / timer** | Top bar — shows the running category name and an HH:MM:SS elapsed timer. "Heute: …" below it shows today's total tracked time. |
| **Category list / grid** | Click any category row (or card) to start tracking it. The active entry is highlighted in blue. Clicking the currently active category while it is running stops and immediately restarts it (useful for adding a new work description). |
| **Stop** | Stops the running timer. Disabled (greyed out) when nothing is running. |
| **Kategorien** | Opens the category manager — add, edit, reorder, or delete categories. |
| **Eintraege** | Opens the entry manager — browse, edit, or delete individual time entries. |
| **Report** | Opens a date-range picker and generates an HTML report in your default browser. |
| **📁 Daten** | Shows the current data file path. Options: open the folder in Explorer, copy the path to the clipboard, or move the data file to a new location. |
| **⊞ Raster** | Toggles between list view and 2-column card grid view. Preference is saved. |
| **📌 Pin** | Keeps the window above all other windows (always on top). |
| **⊟ Mini** | Collapses the window to a slim bar. The mini-bar can be dragged anywhere on screen. |

### Category manager

- **+ Neue Kategorie** — add a category. Pick a name, an optional ServiceNow task number, and a colour swatch.
- **↑ / ↓** — reorder categories; the order is reflected in the main window.
- **🗃 / ♻** — archive a category to hide it from the start list (its entries stay in reports); reactivate it any time. Archiving the currently running category stops the timer.
- Archived categories are hidden in the manager too — **Archivierte anzeigen (n)** in the footer toggles them.
- **✏** — edit an existing category.
- **🗑** — delete a category. Time entries are preserved even after deletion.

> Row action buttons are icon-only; hovering shows a tooltip with the action name.

### Entry manager

- Browse entries by range (today / week / month / all) with free-text search.
- **+ Nachtragen** — manually add a past entry (defaults to the last hour).
- **✏ / 🗑** — edit or delete individual entries.

### Daily target & reminder

The header shows today's total against a daily target (default **8.2 h**) with a slim progress
bar that turns green when the target is reached. If no timer is running for **30 minutes**
during work hours (Mon–Fri, 08:00–17:00), a reminder dialog appears.
Both can be tuned (or disabled with `0`) in `.timetracker_config.json`:

```json
{
  "daily_target_hours": 8.2,
  "remind_no_tracking_min": 30,
  "remind_from_hour": 8,
  "remind_to_hour": 17
}
```

### Work descriptions

After stopping a timer you will be asked for a short work description. This text appears in the HTML report beneath the corresponding entry. The prompt appears every time — press **Enter** or click **OK** to skip it.

### Idle detection

If your machine is idle for **10 minutes** while a timer is running, a dialog appears when you return. You can choose to:

- **Weiterrechnen** — count the idle time as work (no change).
- **Jetzt stoppen** — stop the timer at the moment you returned.
- **Um … gestoppt** — stop the timer at the point when you went idle.

### HTML report

Click **Report**, choose a date range, and an HTML file is opened in your browser. The report includes:

- A filterable summary table per category with hours and percentage share
- A day-by-day journal with time ranges, durations, task numbers, and work descriptions
- Filter chips to show/hide individual categories
- Day buttons to focus on a single day
- A free-text search box
- Copy buttons on task numbers and descriptions

---

## Data & configuration

| File | Location | Purpose |
|---|---|---|
| `timetracker_data.json` | Folder chosen on first run | All categories and time entries |
| `timetracker_data.json.bak` | Same folder | Automatic backup of the previous save |
| `timetracker_data.json.corrupt-…` | Same folder | An unreadable data file is moved aside (never deleted) before the app falls back to the backup |
| `timetracker_data.json.conflict-…` | Same folder | If the data file was changed externally (e.g. OneDrive sync from another machine), the external version is preserved here before saving |
| `.timetracker_config.json` | `~` (home directory) | App preferences: data path, window size/position, pin/mini/grid state, daily target, reminder settings |

---

## Project structure

```
timetracker/
├── timetracker.py      # Complete application — single file, no dependencies
├── start.bat           # Windows launcher (checks for Python, then runs the script)
├── TimeTracker.spec    # PyInstaller build configuration
├── stopwatch.ico       # Application icon (bundled into the .exe)
└── .gitignore
```
