#!/usr/bin/env python3
"""
Time Tracker - Zeiterfassung fuer ServiceNow
Kein pip install noetig (nur Python 3)
"""

import tkinter as tk
from tkinter import messagebox, filedialog
import json, uuid, webbrowser, tempfile, os, shutil, socket, csv, sys
import html as html_mod
import subprocess
from datetime import datetime, date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Config  —  Speicherpfad
# ---------------------------------------------------------------------------
def resource_path(relative):
    """Resolve a bundled resource path — works both in dev and as a PyInstaller .exe."""
    try:
        base = sys._MEIPASS          # PyInstaller extracts files here at runtime
    except AttributeError:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)

def _enable_high_dpi():
    """Opt in to system-DPI awareness on Windows so text renders sharply
    instead of being bitmap-scaled on high-DPI displays."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # system DPI aware
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()        # pre-Win8.1 fallback
    except Exception:
        pass

_enable_high_dpi()

CONFIG_FILE = Path.home() / ".timetracker_config.json"

# Idle threshold (seconds) — after this much inactivity, prompt user on return
IDLE_THRESHOLD_SEC = 600   # 10 minutes

def _atomic_write_text(path: Path, payload: str):
    """Write text atomically: temp file in the same directory, then os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.',
                               suffix='.tmp',
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(payload)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_config(cfg):
    _atomic_write_text(CONFIG_FILE, json.dumps(cfg, indent=2))

def resolve_data_file():
    """Return the data file path, asking the user on first run."""
    cfg = load_config()
    if 'data_dir' in cfg:
        return Path(cfg['data_dir']) / "timetracker_data.json"

    # First run: show folder picker before the main window exists
    root = tk.Tk()
    root.withdraw()

    messagebox.showinfo(
        "Time Tracker – Erster Start",
        "Bitte waehle einen Ordner, in dem die Zeiterfassungsdaten gespeichert werden sollen.\n\n"
        "Tipp: Waehle einen OneDrive- oder Netzwerkordner fuer automatische Synchronisation.",
        parent=root,
    )
    chosen = filedialog.askdirectory(
        title="Speicherort fuer timetracker_data.json",
        parent=root,
    )
    root.destroy()

    if not chosen:
        # User cancelled – fall back to home directory
        chosen = str(Path.home())

    cfg['data_dir'] = chosen
    save_config(cfg)
    return Path(chosen) / "timetracker_data.json"

DATA_FILE = resolve_data_file()
# Default swatches for new categories (existing ones keep their stored colour)
COLORS = ['#4da3ff', '#34d399', '#ffa94d', '#ff6b6b',
          '#b197fc', '#22d3ee', '#fcc419', '#f783ac']

BG       = '#151a23'
BG_PANEL = '#1b2230'
BG_ROW   = '#232c3d'
BG_HOVER = '#2b374c'   # hover state for rows/cards
BG_ACT   = '#173a5e'
BG_ACT_HOVER = '#1d4570'
BG_SEP   = '#0a0e15'   # very-dark separator line
FG       = '#e6ebf2'
FG_DIM   = '#7d8aa0'
FG_MUTED = '#aab8cc'   # inactive category names
ACCENT   = '#4da3ff'
GREEN    = '#34d399'
RED      = '#f0655a'
BTN_GREEN  = '#21a366'
BTN_PURPLE = '#8a63c9'

# Reusable button style helpers
BTN_NEUTRAL  = {'bg': '#33415a', 'fg': '#cdd9e8', 'activebackground': '#3e4f6d', 'activeforeground': '#ffffff'}
BTN_ACCENT   = {'bg': ACCENT,    'fg': '#ffffff', 'activebackground': '#2f7fd6', 'activeforeground': '#ffffff'}
BTN_ACTIVE   = {'bg': '#1d5c96', 'fg': '#ffffff', 'activebackground': '#1d5c96', 'activeforeground': '#ffffff'}
BTN_DANGER   = {'bg': RED,       'fg': '#ffffff', 'activebackground': '#d64a40', 'activeforeground': '#ffffff'}

def _lighten(color, factor=1.18):
    """Slightly brighter shade of a #rrggbb colour — used for hover states."""
    color = color.lstrip('#')
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return '#%02x%02x%02x' % tuple(min(255, int(c * factor) + 10) for c in (r, g, b))

def apply_dark_title_bar(window):
    """Dark window title bar on Windows 10/11 (no-op elsewhere)."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            return
        value = ctypes.c_int(1)
        for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (19 on older builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass

def flatbtn(parent, text, bg, cmd, *, fg=FG, padx=12, pady=6):
    """Flat-style button used throughout all dialogs."""
    return tk.Button(parent, text=text, bg=bg, fg=fg, relief='flat',
                     font=('Segoe UI', 9), padx=padx, pady=pady,
                     cursor='hand2', activebackground=_lighten(bg),
                     activeforeground=fg, command=cmd)

class Tooltip:
    """Minimal hover tooltip — used for icon-only buttons."""
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text   = text
        self.delay  = delay
        self._id    = None
        self._tip   = None
        widget.bind('<Enter>',    self._schedule, add='+')
        widget.bind('<Leave>',    self._hide,     add='+')
        widget.bind('<Button-1>', self._hide,     add='+')

    def _schedule(self, _e=None):
        self._cancel()
        self._id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None

    def _show(self):
        if self._tip or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        tip = tk.Toplevel(self.widget)
        tip.overrideredirect(True)
        tip.attributes('-topmost', True)
        tk.Label(tip, text=self.text, bg=BG_SEP, fg=FG,
                 font=('Segoe UI', 8), padx=8, pady=3).pack()
        tip.geometry(f'+{x}+{y}')
        self._tip = tip

    def _hide(self, _e=None):
        self._cancel()
        if self._tip:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

def iconbtn(parent, icon, tooltip, bg, cmd, *, fg=FG):
    """Small icon-only action button with a hover tooltip."""
    b = tk.Button(parent, text=icon, bg=bg, fg=fg, relief='flat',
                  font=('Segoe UI', 9), padx=7, pady=3,
                  cursor='hand2', activebackground=_lighten(bg),
                  activeforeground=fg, command=cmd)
    b._keep_bg = True   # protect from _set_bg_tree on row hover
    Tooltip(b, tooltip)
    return b

def swatch(parent, color, **kw):
    """Category colour bar — keeps its colour when the row hover repaints."""
    f = tk.Frame(parent, bg=color, **kw)
    f._keep_bg = True
    return f

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

# mtime of DATA_FILE at last load/save — used to detect external changes
# (e.g. OneDrive sync from another machine) before overwriting.
_DATA_MTIME = None

def _stat_data_mtime():
    try:
        return DATA_FILE.stat().st_mtime_ns
    except OSError:
        return None

def load_data():
    """Load data, falling back to .bak on JSON decode error.

    A corrupt main file is renamed aside (quarantined) instead of being left
    in place — otherwise the next save would copy the corrupt file over a
    possibly good .bak.
    """
    global _DATA_MTIME
    d = None
    if DATA_FILE.exists():
        corrupt = None
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
        except (json.JSONDecodeError, OSError) as ex:
            if isinstance(ex, json.JSONDecodeError):
                ts = datetime.now().strftime('%Y%m%d-%H%M%S')
                corrupt = DATA_FILE.with_name(DATA_FILE.name + f'.corrupt-{ts}')
                try:
                    os.replace(DATA_FILE, corrupt)
                except OSError:
                    corrupt = None
            bak = DATA_FILE.with_suffix(DATA_FILE.suffix + '.bak')
            if bak.exists():
                try:
                    with open(bak, 'r', encoding='utf-8') as f:
                        d = json.load(f)
                    messagebox.showwarning(
                        "Time Tracker",
                        f"Hauptdatei beschaedigt - aus Backup wiederhergestellt:\n{bak}",
                    )
                except (json.JSONDecodeError, OSError):
                    d = None
            if d is None:
                msg = ("Datendatei nicht lesbar und kein brauchbares Backup gefunden - "
                       "starte mit leeren Daten.")
                if corrupt is not None:
                    msg += f"\n\nDie beschaedigte Datei wurde gesichert als:\n{corrupt}"
                messagebox.showwarning("Time Tracker", msg)
    if d is None:
        d = {}
    d.setdefault('categories', [])
    d.setdefault('entries', [])
    _DATA_MTIME = _stat_data_mtime()
    return d

def save_data(data):
    """Atomically write data file, keeping a rolling .bak of the previous version."""
    global _DATA_MTIME
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    cur_mtime = _stat_data_mtime()
    if _DATA_MTIME is not None and cur_mtime is not None and cur_mtime != _DATA_MTIME:
        # File changed on disk behind our back (e.g. OneDrive sync from another
        # machine). Preserve the external version before overwriting it.
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        conflict = DATA_FILE.with_name(DATA_FILE.name + f'.conflict-{ts}')
        try:
            shutil.copy2(DATA_FILE, conflict)
            messagebox.showwarning(
                "Time Tracker",
                "Die Datendatei wurde ausserhalb dieser Instanz geaendert "
                "(z.B. OneDrive-Sync von einem anderen Geraet).\n\n"
                "Die externe Version wurde gesichert als:\n"
                f"{conflict}\n\n"
                "Die Daten dieser Instanz werden jetzt gespeichert.",
            )
        except OSError:
            pass
    if DATA_FILE.exists():
        try:
            shutil.copy2(DATA_FILE, DATA_FILE.with_suffix(DATA_FILE.suffix + '.bak'))
        except OSError:
            pass  # backup is best-effort
    _atomic_write_text(DATA_FILE, payload)
    _DATA_MTIME = _stat_data_mtime()

# ---------------------------------------------------------------------------
# Single-instance lock (binds a localhost TCP port keyed by data file path)
# ---------------------------------------------------------------------------
_SINGLETON_SOCK = None

def acquire_singleton():
    """Return True if we're the only instance for this data file, False if another is running."""
    global _SINGLETON_SOCK
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Deterministic port keyed off DATA_FILE so different data dirs can run in parallel
    h = 0
    for ch in str(DATA_FILE).lower():
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    port = 49152 + (h % 8192)   # 49152..57343 (dynamic/private range)
    try:
        s.bind(('127.0.0.1', port))
        s.listen(1)
        _SINGLETON_SOCK = s
        return True
    except OSError:
        s.close()
        return False

# ---------------------------------------------------------------------------
# Idle detection (Windows only — returns 0 elsewhere)
# ---------------------------------------------------------------------------

def get_idle_seconds():
    """Seconds since last user input (Windows). Returns 0 on other platforms or on error."""
    if sys.platform != 'win32':
        return 0
    try:
        import ctypes
        from ctypes import wintypes
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return max(0, millis / 1000.0)
    except Exception:
        return 0

def running_entry(data):
    for e in data['entries']:
        if not e.get('end'):
            return e
    return None

def active_categories(data):
    """Categories not archived. Archived ones keep their entries and still
    appear in reports/history, but are hidden from the start list."""
    return [c for c in data['categories'] if not c.get('archived')]

def _bind_tree(widget, event, handler):
    """Bind an event on a widget and all its descendants."""
    widget.bind(event, handler)
    for child in widget.winfo_children():
        _bind_tree(child, event, handler)

def _set_bg_tree(widget, color):
    """Set background colour on a widget and all its descendants,
    skipping widgets marked with _keep_bg (colour swatches, icon buttons)."""
    if getattr(widget, '_keep_bg', False):
        return
    try:
        widget.config(bg=color)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        _set_bg_tree(child, color)

def fmt_hms(sec):
    h, r = divmod(int(sec), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def fmt_h(sec):
    return f"{sec / 3600:.2f} h"

def fmt_hm(sec):
    """Short duration: 1:30 h or 45 min."""
    h, r = divmod(int(round(sec)), 3600)
    m    = r // 60
    if h == 0:
        return f"{m} min"
    return f"{h}:{m:02d} h"

# ---------------------------------------------------------------------------
# HTML Report  —  Journal style
# ---------------------------------------------------------------------------

def generate_report(data, from_date, to_date):
    esc = html_mod.escape
    cat_map = {c['id']: c for c in data['categories']}
    now = datetime.now()

    by_day = {}
    for e in data['entries']:
        try:
            s   = datetime.fromisoformat(e['start'])
            end = datetime.fromisoformat(e['end']) if e.get('end') else now
        except (ValueError, TypeError):
            continue
        # Entries are attributed entirely to their start day (no midnight split)
        d = s.date()
        if not (from_date <= d <= to_date):
            continue
        dur = (end - s).total_seconds()
        if dur < 1:
            continue
        desc = e.get('description') or ''
        by_day.setdefault(d, []).append((s, end, e['category_id'], dur, desc))

    for d in by_day:
        by_day[d].sort(key=lambda x: x[0])

    totals = {}
    for entries in by_day.values():
        for _, _, cid, dur, _ in entries:
            totals[cid] = totals.get(cid, 0) + dur
    grand = sum(totals.values())

    sum_rows = ''
    for cid, sec in sorted(totals.items(), key=lambda x: -x[1]):
        c   = cat_map.get(cid, {'name': '?', 'task_number': '-', 'color': '#999'})
        pct = sec / grand * 100 if grand else 0
        sum_rows += f"""
        <tr>
          <td><span class="dot" style="background:{esc(c['color'])}"></span>{esc(c['name'])}</td>
          <td class="mono">{esc(c.get('task_number') or '–')}</td>
          <td class="r">{fmt_h(sec)}</td>
          <td class="r">{pct:.1f}&thinsp;%</td>
        </tr>"""

    seen_cids = []
    for entries in [by_day[d] for d in sorted(by_day.keys())]:
        for _, _, cid, _, _ in entries:
            if cid not in seen_cids:
                seen_cids.append(cid)

    WEEKDAYS_SHORT = ['Mo','Di','Mi','Do','Fr','Sa','So']

    cat_checkboxes = ''
    for cid in seen_cids:
        c = cat_map.get(cid, {'name': '?', 'color': '#999'})
        cat_checkboxes += f"""
        <label class="cat-label">
          <input type="checkbox" class="cat-cb" value="{esc(cid)}" checked>
          <span class="dot" style="background:{esc(c['color'])}"></span>{esc(c['name'])}
        </label>"""

    day_buttons = '<button class="day-btn active" data-date="all">Alle</button>'
    for d in sorted(by_day.keys()):
        wd = WEEKDAYS_SHORT[d.weekday()]
        day_buttons += f'<button class="day-btn" data-date="{d.isoformat()}">{wd}&nbsp;{d.strftime("%d.%m")}</button>'

    WEEKDAYS = ['Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag','Sonntag']
    PAUSE_THRESHOLD = 5 * 60

    journal_html = ''
    for d in sorted(by_day.keys()):
        entries   = by_day[d]
        day_total = sum(e[3] for e in entries)
        wd        = WEEKDAYS[d.weekday()]

        rows = ''
        prev_end = None
        for s, end, cid, dur, desc in entries:
            cat  = cat_map.get(cid, {'name': '?', 'task_number': '–', 'color': '#999'})
            task = cat.get('task_number') or '–'

            if prev_end is not None:
                gap = (s - prev_end).total_seconds()
                if gap >= PAUSE_THRESHOLD:
                    rows += f"""
              <tr class="pause-row">
                <td colspan="4">
                  <span class="pause-icon">&#9646;</span>
                  Pause&nbsp;<span class="pause-dur">{fmt_hm(gap)}</span>
                </td>
              </tr>"""

            rows += f"""
              <tr class="entry-row" data-cat="{esc(cid)}" data-dur="{int(dur)}" data-desc="{esc(desc.lower())}" data-date="{d.isoformat()}">
                <td class="time-range">{s.strftime('%H:%M')}&nbsp;–&nbsp;{end.strftime('%H:%M')}</td>
                <td class="dur">{fmt_hm(dur)}</td>
                <td class="cat-cell">
                  <span class="dot" style="background:{esc(cat['color'])}"></span>{esc(cat['name'])}
                </td>
                <td class="mono task-col">{esc(task)}<button class="copy-btn" data-copy="{esc(task)}" title="Kopieren">&#128203;</button></td>
              </tr>"""

            if desc:
                rows += f"""
              <tr class="desc-row">
                <td colspan="4" class="desc-cell">&#8627;&nbsp;{esc(desc)}<button class="copy-btn" data-copy="{esc(desc)}" title="Kopieren">&#128203;</button></td>
              </tr>"""

            prev_end = end

        d_iso = d.isoformat()
        day_label = d.strftime('%d. %B %Y').lstrip('0')
        journal_html += f"""
      <div class="day-card" data-date="{d_iso}">
        <div class="day-header">
          <span class="day-name">{wd}, {day_label}</span>
          <span class="day-total" id="total-{d_iso}">{fmt_h(day_total)}</span>
        </div>
        <table class="journal">
          <thead>
            <tr><th>Zeitraum</th><th>Dauer</th><th>Kategorie</th><th>Task-Nummer</th></tr>
          </thead>
          <tbody>{rows}
          </tbody>
        </table>
      </div>"""

    lbl = f"{from_date.strftime('%d.%m.%Y')} – {to_date.strftime('%d.%m.%Y')}"
    gen = datetime.now().strftime('%d.%m.%Y %H:%M')

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Time Report {lbl}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #eef2f7; color: #2d3748; padding: 32px 40px;
    max-width: 960px; margin: 0 auto;
  }}
  h1   {{ font-size: 1.8em; color: #1a202c; margin-bottom: 4px; }}
  .sub {{ color: #718096; margin-bottom: 28px; font-size: .95em; }}
  h2   {{
    font-size: .8em; font-weight: 700; color: #4a5568;
    text-transform: uppercase; letter-spacing: .1em;
    margin: 28px 0 10px; border-left: 3px solid #3498db; padding-left: 9px;
  }}

  /* ---- Filter bar ---- */
  .filter-bar {{
    position: sticky; top: 0; z-index: 100;
    background: #2d3748; border-radius: 10px;
    padding: 12px 16px; margin-bottom: 28px;
    box-shadow: 0 2px 8px rgba(0,0,0,.2);
    display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
  }}
  .filter-section {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
  .filter-divider {{ width: 1px; background: #4a5568; align-self: stretch; margin: 0 2px; }}
  .filter-label-hd {{ font-size: .72em; color: #718096; text-transform: uppercase;
                      letter-spacing: .08em; white-space: nowrap; }}

  .cat-label {{
    display: inline-flex; align-items: center; gap: 4px;
    background: #3d4f5c; color: #e2e8f0; font-size: .82em;
    padding: 4px 10px; border-radius: 20px; cursor: pointer;
    user-select: none; transition: background .15s;
  }}
  .cat-label:hover {{ background: #4a6070; }}
  .cat-label input {{ display: none; }}
  .cat-label.off {{ background: #1e2a35; color: #718096; }}
  .cat-label.off .dot {{ opacity: .35; }}

  .day-btn {{
    background: #3d4f5c; color: #a0aec0; border: none; cursor: pointer;
    font-size: .82em; padding: 4px 10px; border-radius: 20px;
    font-family: inherit; transition: background .15s;
  }}
  .day-btn:hover {{ background: #4a6070; color: #e2e8f0; }}
  .day-btn.active {{ background: #3498db; color: #fff; font-weight: 600; }}

  #searchInput {{
    background: #3d4f5c; border: none; color: #e2e8f0;
    font-size: .85em; padding: 5px 12px; border-radius: 20px;
    font-family: inherit; outline: none; width: 180px;
  }}
  #searchInput::placeholder {{ color: #718096; }}
  #searchInput:focus {{ background: #4a6070; }}

  .filter-counter {{
    margin-left: auto; font-size: .8em; color: #a0aec0; white-space: nowrap;
  }}
  .filter-counter strong {{ color: #e2e8f0; }}

  #resetBtn {{
    background: none; border: 1px solid #4a5568; color: #718096;
    font-size: .78em; padding: 3px 10px; border-radius: 20px;
    cursor: pointer; font-family: inherit;
  }}
  #resetBtn:hover {{ border-color: #718096; color: #a0aec0; }}

  /* ---- Summary table ---- */
  table.sum {{
    width: 100%; border-collapse: collapse; background: #fff;
    border-radius: 10px; overflow: hidden;
    box-shadow: 0 1px 5px rgba(0,0,0,.09); margin-bottom: 32px;
  }}
  table.sum th {{
    background: #3498db; color: #fff; padding: 10px 16px;
    text-align: left; font-size: .82em; letter-spacing: .05em;
  }}
  table.sum td {{
    padding: 9px 16px; border-bottom: 1px solid #edf2f7; font-size: .9em;
  }}
  table.sum tr:last-child td {{ border-bottom: none; }}
  .total-row td {{ background: #2d3748; color: #fff; font-weight: 700; }}

  /* ---- Journal cards ---- */
  .day-card {{
    background: #fff; border-radius: 10px;
    box-shadow: 0 1px 5px rgba(0,0,0,.09); margin-bottom: 20px;
    overflow: hidden;
  }}
  .day-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 18px; background: #2d3748; color: #e2e8f0;
  }}
  .day-name  {{ font-weight: 700; font-size: 1em; }}
  .day-total {{ font-variant-numeric: tabular-nums; font-size: .9em;
                background: #3498db; padding: 2px 10px; border-radius: 20px;
                color: #fff; font-weight: 600; }}

  table.journal {{ width: 100%; border-collapse: collapse; }}
  table.journal th {{
    background: #f7fafc; color: #718096; font-size: .75em;
    font-weight: 600; text-transform: uppercase; letter-spacing: .06em;
    padding: 7px 16px; text-align: left; border-bottom: 1px solid #edf2f7;
  }}
  table.journal td {{
    padding: 9px 16px; border-bottom: 1px solid #f0f4f8;
    font-size: .9em; vertical-align: middle;
  }}
  table.journal tr:last-child td {{ border-bottom: none; }}
  table.journal tr:hover td {{ background: #f7fafc; }}

  .time-range {{
    font-variant-numeric: tabular-nums; white-space: nowrap;
    font-family: 'Consolas', monospace; color: #4a5568; font-size: .88em;
  }}
  .dur {{ font-variant-numeric: tabular-nums; white-space: nowrap;
          color: #718096; font-size: .85em; min-width: 56px; }}
  .cat-cell {{ font-weight: 500; }}
  .task-col {{ color: #718096; font-family: monospace; font-size: .85em; }}
  .copy-btn {{
    display: inline-block; opacity: 0; margin-left: 7px;
    background: none; border: 1px solid #cbd5e0; border-radius: 4px;
    color: #718096; font-size: .75em; padding: 1px 6px; cursor: pointer;
    vertical-align: middle; transition: opacity .15s, background .15s;
    font-family: inherit; line-height: 1.5;
  }}
  .copy-btn.copied {{
    background: #c6f6d5; border-color: #68d391; color: #276749;
  }}
  tr:hover .copy-btn, td:hover .copy-btn {{ opacity: 1; }}

  .pause-row td {{
    background: #fffbeb; color: #92400e; font-size: .8em;
    padding: 5px 16px; border-bottom: 1px solid #fef3c7;
  }}
  .pause-icon {{ margin-right: 6px; opacity: .5; }}
  .pause-dur  {{ font-weight: 600; }}
  .desc-row td {{ border-bottom: 1px solid #edf2f7; padding: 0; }}
  .desc-cell {{
    padding: 3px 16px 9px 32px !important;
    font-size: .83em; color: #718096; font-style: italic;
  }}

  .dot  {{ display: inline-block; width: 9px; height: 9px;
           border-radius: 50%; margin-right: 8px; flex-shrink: 0; }}
  .r    {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .mono {{ font-family: monospace; color: #718096; }}
  .footer {{ font-size: .78em; color: #a0aec0; margin-top: 20px; text-align: center; }}
  .no-results {{ color: #718096; font-size: .9em; padding: 20px 0; text-align: center; display: none; }}

  @media print {{
    .filter-bar {{ display: none; }}
    body {{ background: white; padding: 16px; }}
    .day-card {{ box-shadow: none; border: 1px solid #e2e8f0; page-break-inside: avoid; }}
  }}
</style>
</head>
<body>
<h1>&#128337;&nbsp; Time Report</h1>
<p class="sub">Zeitraum: <strong>{lbl}</strong></p>

<!-- ===== FILTER BAR ===== -->
<div class="filter-bar">
  <div class="filter-section">
    <span class="filter-label-hd">Kategorie</span>
    {cat_checkboxes}
  </div>
  <div class="filter-divider"></div>
  <div class="filter-section">
    <span class="filter-label-hd">Tag</span>
    {day_buttons}
  </div>
  <div class="filter-divider"></div>
  <input type="text" id="searchInput" placeholder="&#128269; Beschreibung...">
  <span class="filter-counter" id="counter"></span>
  <button id="resetBtn">Zuruecksetzen</button>
</div>

<h2>Zusammenfassung</h2>
<table class="sum">
  <thead>
    <tr>
      <th>Kategorie</th><th>Task-Nummer (ServiceNow)</th>
      <th style="text-align:right">Stunden</th><th style="text-align:right">Anteil</th>
    </tr>
  </thead>
  <tbody>
    {sum_rows}
    <tr class="total-row">
      <td colspan="2">Gesamt</td>
      <td class="r">{fmt_h(grand)}</td>
      <td class="r">100&thinsp;%</td>
    </tr>
  </tbody>
</table>

<h2>Tagesjournal</h2>
<p class="no-results" id="noResults">Keine Eintraege entsprechen dem Filter.</p>
{journal_html if journal_html else '<p style="color:#718096;font-size:.9em">Keine Eintraege im gewaehlten Zeitraum.</p>'}

<p class="footer">Generiert am {gen}&nbsp;&nbsp;|&nbsp;&nbsp;Quelldatei: {esc(str(DATA_FILE))}</p>

<script>
(function () {{
  // ── state ──────────────────────────────────────────────────────────────
  let activeCats = new Set(
    [...document.querySelectorAll('.cat-cb')].map(el => el.value)
  );
  let activeDay  = 'all';
  let searchTerm = '';

  // ── helpers ────────────────────────────────────────────────────────────
  function fmtH(sec) {{
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return h + ':' + String(m).padStart(2, '0') + ' h';
  }}

  // ── main filter ────────────────────────────────────────────────────────
  function apply() {{
    let totalVisible = 0, totalSec = 0;

    document.querySelectorAll('.day-card').forEach(card => {{
      const cardDate    = card.dataset.date;
      const dayMatches  = activeDay === 'all' || activeDay === cardDate;
      const entryRows   = card.querySelectorAll('.entry-row');
      let   dayVisible  = 0, daySec = 0;

      entryRows.forEach(row => {{
        const catOk  = activeCats.has(row.dataset.cat);
        const dayOk  = dayMatches;
        const srchOk = !searchTerm || row.dataset.desc.includes(searchTerm);
        const show   = catOk && dayOk && srchOk;

        row.style.display = show ? '' : 'none';

        // keep desc-row in sync
        let sib = row.nextElementSibling;
        if (sib && sib.classList.contains('desc-row'))
          sib.style.display = show ? '' : 'none';

        if (show) {{ dayVisible++; daySec += parseInt(row.dataset.dur, 10); }}
      }});

      // hide pause rows whenever any filter is active (avoids misleading gaps)
      const filtering = activeCats.size < document.querySelectorAll('.cat-cb').length
                        || activeDay !== 'all' || searchTerm;
      card.querySelectorAll('.pause-row').forEach(pr => {{
        pr.style.display = filtering ? 'none' : '';
      }});

      card.style.display = dayVisible > 0 ? '' : 'none';

      // update per-day total badge
      const badge = document.getElementById('total-' + cardDate);
      if (badge) badge.textContent = fmtH(daySec);

      totalVisible += dayVisible;
      totalSec     += daySec;
    }});

    // counter
    document.getElementById('counter').innerHTML =
      '<strong>' + totalVisible + '</strong> Eintr\u00e4ge\u2002\u00b7\u2002<strong>'
      + fmtH(totalSec) + '</strong>';

    document.getElementById('noResults').style.display =
      totalVisible === 0 ? 'block' : 'none';
  }}

  // ── category checkboxes ────────────────────────────────────────────────
  document.querySelectorAll('.cat-cb').forEach(cb => {{
    cb.closest('.cat-label').classList.toggle('off', !cb.checked);
    cb.addEventListener('change', () => {{
      if (cb.checked) activeCats.add(cb.value);
      else            activeCats.delete(cb.value);
      cb.closest('.cat-label').classList.toggle('off', !cb.checked);
      apply();
    }});
  }});

  // ── day buttons ────────────────────────────────────────────────────────
  document.querySelectorAll('.day-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      document.querySelectorAll('.day-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeDay = btn.dataset.date;
      apply();
    }});
  }});

  // ── search ─────────────────────────────────────────────────────────────
  document.getElementById('searchInput').addEventListener('input', function () {{
    searchTerm = this.value.toLowerCase().trim();
    apply();
  }});

  // ── reset ──────────────────────────────────────────────────────────────
  document.getElementById('resetBtn').addEventListener('click', () => {{
    document.querySelectorAll('.cat-cb').forEach(cb => {{
      cb.checked = true;
      cb.closest('.cat-label').classList.remove('off');
      activeCats.add(cb.value);
    }});
    document.querySelectorAll('.day-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.day-btn[data-date="all"]').classList.add('active');
    activeDay  = 'all';
    searchTerm = '';
    document.getElementById('searchInput').value = '';
    apply();
  }});

  // ── copy buttons ───────────────────────────────────────────────────────
  document.addEventListener('click', function (e) {{
    const btn = e.target.closest('.copy-btn');
    if (!btn) return;
    const text = btn.dataset.copy;
    navigator.clipboard.writeText(text).then(() => {{
      btn.textContent = '\u2713';
      btn.classList.add('copied');
      setTimeout(() => {{
        btn.textContent = '📋';
        btn.classList.remove('copied');
      }}, 1500);
    }});
  }});

  // ── init ───────────────────────────────────────────────────────────────
  apply();
}})();
</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# Category Form Dialog  (add / edit single category)
# ---------------------------------------------------------------------------

class CategoryDialog(tk.Toplevel):
    def __init__(self, parent, category=None):
        super().__init__(parent)
        self.configure(bg=BG_PANEL)
        self.title("Kategorie bearbeiten" if category else "Neue Kategorie")
        self.resizable(False, False)
        self.result = None
        self.transient(parent)
        self.grab_set()
        apply_dark_title_bar(self)
        self.geometry(f"+{parent.winfo_rootx()+60}+{parent.winfo_rooty()+60}")

        pad = tk.Frame(self, bg=BG_PANEL, padx=22, pady=18)
        pad.pack(fill='both', expand=True)

        def lbl(text, row):
            tk.Label(pad, text=text, bg=BG_PANEL, fg=FG_DIM,
                     font=('Segoe UI', 9)).grid(row=row, column=0, sticky='w', pady=5)

        def mkentry(var, row):
            e = tk.Entry(pad, textvariable=var, width=28,
                         bg=BG_ROW, fg=FG, insertbackground=FG,
                         relief='flat', font=('Segoe UI', 10), bd=4)
            e.grid(row=row, column=1, padx=(10, 0), pady=5)
            return e

        lbl("Name:", 0)
        self.name_var = tk.StringVar(value=category['name'] if category else '')
        mkentry(self.name_var, 0).focus_set()

        lbl("Task-Nr. (ServiceNow):", 1)
        self.task_var = tk.StringVar(value=(category or {}).get('task_number', ''))
        mkentry(self.task_var, 1)

        lbl("Farbe:", 2)
        self.color_var = tk.StringVar(value=(category or {}).get('color', COLORS[0]))
        cf = tk.Frame(pad, bg=BG_PANEL)
        cf.grid(row=2, column=1, padx=(10, 0), sticky='w', pady=5)
        self._color_rings = {}
        for c in COLORS:
            ring = tk.Frame(cf, bg=BG_PANEL, padx=2, pady=2)
            ring.pack(side='left', padx=1)
            tk.Button(ring, bg=c, width=2, height=1, relief='flat', cursor='hand2',
                      activebackground=c,
                      command=lambda col=c: self.color_var.set(col)).pack()
            self._color_rings[c] = ring

        def _sync_ring(*_):
            sel = self.color_var.get()
            for col, ring in self._color_rings.items():
                ring.config(bg=FG if col == sel else BG_PANEL)
        self.color_var.trace_add('write', _sync_ring)
        _sync_ring()   # highlight the initially selected colour

        bf = tk.Frame(pad, bg=BG_PANEL)
        bf.grid(row=3, column=0, columnspan=2, pady=(16, 0))
        flatbtn(bf, "Speichern", ACCENT, self._ok, padx=14).pack(side='left', padx=4)
        flatbtn(bf, "Abbrechen", BG_ROW,  self.destroy, padx=14).pack(side='left', padx=4)

        self.bind('<Return>', lambda _: self._ok())
        self.bind('<Escape>', lambda _: self.destroy())
        self.wait_window()

    def _ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Fehler", "Bitte einen Namen eingeben.", parent=self)
            return
        self.result = {'name': name,
                       'task_number': self.task_var.get().strip(),
                       'color': self.color_var.get()}
        self.destroy()

# ---------------------------------------------------------------------------
# Manage Categories Dialog  (list with edit / delete per row)
# ---------------------------------------------------------------------------

class ManageCategoriesDialog(tk.Toplevel):
    def __init__(self, parent, data, on_change):
        super().__init__(parent)
        self.configure(bg=BG_PANEL)
        self.title("Kategorien verwalten")
        self.resizable(True, True)
        self.minsize(420, 200)
        self.data      = data
        self.on_change = on_change
        self._show_archived = False
        self.transient(parent)
        self.grab_set()
        apply_dark_title_bar(self)
        self.geometry(f"520x400+{parent.winfo_rootx()+40}+{parent.winfo_rooty()+40}")

        self._build()
        self.bind('<Escape>', lambda _: self.destroy())
        self.wait_window()

    def _build(self):
        for w in self.winfo_children():
            w.destroy()

        # Header
        hdr = tk.Frame(self, bg=BG_PANEL, padx=16, pady=12)
        hdr.pack(fill='x')
        tk.Label(hdr, text="Kategorien", bg=BG_PANEL, fg=FG,
                 font=('Segoe UI', 11, 'bold')).pack(side='left')
        n_arch = sum(1 for c in self.data['categories'] if c.get('archived'))
        count_txt = (f"{len(self.data['categories']) - n_arch} aktiv · {n_arch} archiviert"
                     if n_arch else f"{len(self.data['categories'])} gespeichert")
        tk.Label(hdr, text=count_txt,
                 bg=BG_PANEL, fg=FG_DIM, font=('Segoe UI', 9)).pack(side='right')

        tk.Frame(self, bg=BG_SEP, height=1).pack(fill='x')

        # Scrollable list
        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill='both', expand=True)

        canvas = tk.Canvas(body, bg=BG_PANEL, highlightthickness=0, bd=0)
        canvas.pack(side='left', fill='both', expand=True)
        sb = tk.Scrollbar(body, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=lambda f, l: self._scrollset(canvas, sb, f, l))

        inner = tk.Frame(canvas, bg=BG_PANEL, padx=10, pady=6)
        win   = canvas.create_window((0, 0), window=inner, anchor='nw')

        inner.bind('<Configure>', lambda _: canvas.configure(
            scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(win, width=e.width))

        def _wheel(e):
            canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units')
        canvas.bind('<MouseWheel>', _wheel)

        self._list_canvas = canvas
        self._list_sb     = sb
        self._wheel_fn    = _wheel

        n_arch  = sum(1 for c in self.data['categories'] if c.get('archived'))
        visible = [c for c in self.data['categories']
                   if self._show_archived or not c.get('archived')]

        if not visible:
            text = ("Noch keine Kategorien vorhanden."
                    if not self.data['categories']
                    else f"{n_arch} archivierte Kategorie(n) ausgeblendet.")
            tk.Label(inner, text=text,
                     bg=BG_PANEL, fg=FG_DIM, font=('Segoe UI', 9),
                     pady=16).pack()
        else:
            for cat in visible:
                self._cat_row(inner, cat, visible)
            _bind_tree(inner, '<MouseWheel>', _wheel)

        # Footer
        tk.Frame(self, bg=BG_SEP, height=1).pack(fill='x')
        ft = tk.Frame(self, bg=BG_PANEL, padx=16, pady=10)
        ft.pack(fill='x')
        flatbtn(ft, "+ Neue Kategorie", BTN_GREEN, self._add).pack(side='left')
        if n_arch:
            txt = ("Archivierte ausblenden" if self._show_archived
                   else f"Archivierte anzeigen ({n_arch})")
            flatbtn(ft, txt, BG_ROW, self._toggle_show_archived,
                    fg=FG_DIM).pack(side='left', padx=(6, 0))
        flatbtn(ft, "Schliessen",       BG_ROW,    self.destroy).pack(side='right')

    def _toggle_show_archived(self):
        self._show_archived = not self._show_archived
        self._build()

    @staticmethod
    def _scrollset(canvas, sb, first, last):
        """Show scrollbar only when list overflows."""
        canvas.configure(yscrollcommand=sb.set)
        sb.set(first, last)
        try:
            f, l = float(first), float(last)
        except ValueError:
            return
        if (l - f) < 0.999 and not sb.winfo_ismapped():
            sb.pack(side='right', fill='y')
        elif (l - f) >= 0.999 and sb.winfo_ismapped():
            sb.pack_forget()

    def _cat_row(self, parent, cat, visible):
        archived = bool(cat.get('archived'))
        row = tk.Frame(parent, bg=BG_ROW)
        row.pack(fill='x', pady=2)

        # Colour swatch
        swatch(row, cat['color'], width=5).pack(side='left', fill='y')

        # Name + task number on one line
        mid = tk.Frame(row, bg=BG_ROW, padx=10)
        mid.pack(side='left', fill='both', expand=True)

        tk.Label(mid, text=cat['name'], bg=BG_ROW, fg=FG_DIM if archived else FG,
                 font=('Segoe UI', 10, 'bold'), anchor='w').pack(side='left', pady=7)
        task = cat.get('task_number') or ''
        if task:
            tk.Label(mid, text=f'· {task}', bg=BG_ROW, fg=FG_DIM,
                     font=('Segoe UI', 9), anchor='w').pack(side='left', padx=(6, 0), pady=7)
        if archived:
            tk.Label(mid, text='(archiviert)', bg=BG_ROW, fg=FG_DIM,
                     font=('Segoe UI', 8, 'italic'), anchor='w').pack(side='left', padx=(6, 0), pady=7)

        # Action buttons — arrows move within the *visible* list so a swap
        # with a hidden archived neighbour never looks like a no-op
        idx  = visible.index(cat)
        btns = tk.Frame(row, bg=BG_ROW, padx=6)
        btns.pack(side='right', fill='y')
        for symbol, delta in (("↑", -1), ("↓", 1)):
            at_edge = (idx == 0 and delta == -1) or (idx == len(visible) - 1 and delta == 1)
            tk.Button(btns, text=symbol, bg=BG_PANEL, fg=FG_DIM if at_edge else FG,
                      relief='flat', font=('Segoe UI', 9), padx=5, pady=3,
                      cursor='hand2', activebackground=BG_PANEL,
                      state='disabled' if at_edge else 'normal',
                      command=lambda c=cat, d=delta: self._move(c, d),
                      ).pack(side='left', padx=1, pady=6)
        iconbtn(btns, "♻" if archived else "🗃",
                "Reaktivieren" if archived else "Archivieren",
                BTN_NEUTRAL['bg'], lambda c=cat: self._toggle_archive(c)
                ).pack(side='left', padx=(4, 2), pady=6)
        iconbtn(btns, "✏", "Bearbeiten",
                ACCENT, lambda c=cat: self._edit(c)).pack(side='left', padx=2, pady=6)
        iconbtn(btns, "🗑", "Loeschen",
                RED, lambda c=cat: self._delete(c)).pack(side='left', padx=2, pady=6)

    def _toggle_archive(self, cat):
        if cat.get('archived'):
            cat.pop('archived', None)
        else:
            # Archiving the category of the running entry stops it (like delete)
            run = running_entry(self.data)
            if run and run['category_id'] == cat['id']:
                run['end'] = datetime.now().isoformat(timespec='seconds')
            cat['archived'] = True
        save_data(self.data)
        self.on_change()
        self._build()

    def _add(self):
        dlg = CategoryDialog(self)
        if dlg.result:
            dlg.result['id'] = str(uuid.uuid4())
            self.data['categories'].append(dlg.result)
            save_data(self.data)
            self.on_change()
            self._build()

    def _edit(self, cat):
        dlg = CategoryDialog(self, cat)
        if dlg.result:
            cat.update(dlg.result)
            save_data(self.data)
            self.on_change()
            self._build()

    def _delete(self, cat):
        if not messagebox.askyesno(
                "Loeschen",
                f"Kategorie \"{cat['name']}\" loeschen?\n"
                "Bereits erfasste Zeiteintraege bleiben erhalten.",
                parent=self):
            return
        run = running_entry(self.data)
        if run and run['category_id'] == cat['id']:
            run['end'] = datetime.now().isoformat(timespec='seconds')
        self.data['categories'].remove(cat)
        save_data(self.data)
        self.on_change()
        self._build()

    def _move(self, cat, direction):
        cats    = self.data['categories']
        visible = [c for c in cats if self._show_archived or not c.get('archived')]
        vidx    = visible.index(cat)
        new_v   = vidx + direction
        if not (0 <= new_v < len(visible)):
            return
        # Swap with the visible neighbour's position in the full list
        i, j = cats.index(cat), cats.index(visible[new_v])
        cats[i], cats[j] = cats[j], cats[i]
        save_data(self.data)
        self.on_change()
        self._build()

# ---------------------------------------------------------------------------
# Edit Entry Dialog (single entry)
# ---------------------------------------------------------------------------

class EditEntryDialog(tk.Toplevel):
    """Edit start/end/description of a single time entry."""
    FMT = '%d.%m.%Y %H:%M:%S'

    def __init__(self, parent, entry, data, title="Eintrag bearbeiten"):
        super().__init__(parent)
        self.configure(bg=BG_PANEL)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        apply_dark_title_bar(self)
        self.geometry(f"+{parent.winfo_rootx()+50}+{parent.winfo_rooty()+50}")
        self.entry      = entry
        self.data       = data
        self.categories = data['categories']
        categories      = self.categories
        self.result     = None

        pad = tk.Frame(self, bg=BG_PANEL, padx=22, pady=18)
        pad.pack(fill='both', expand=True)

        def lbl(text, r):
            tk.Label(pad, text=text, bg=BG_PANEL, fg=FG_DIM,
                     font=('Segoe UI', 9)).grid(row=r, column=0, sticky='w', pady=5)

        def ent(var, w=22):
            return tk.Entry(pad, textvariable=var, width=w,
                            bg=BG_ROW, fg=FG, insertbackground=FG,
                            relief='flat', font=('Segoe UI', 10), bd=4)

        lbl("Kategorie:", 0)
        cat_names = [c['name'] for c in categories]
        cur_cat   = next((c for c in categories if c['id'] == entry['category_id']), None)
        self.cat_var = tk.StringVar(value=cur_cat['name'] if cur_cat else (cat_names[0] if cat_names else ''))
        om = tk.OptionMenu(pad, self.cat_var, *(cat_names or ['']))
        om.config(bg=BG_ROW, fg=FG, activebackground=BG_ROW, activeforeground=FG,
                  relief='flat', font=('Segoe UI', 10), highlightthickness=0,
                  width=20, anchor='w')
        om['menu'].config(bg=BG_ROW, fg=FG)
        om.grid(row=0, column=1, sticky='w', padx=(10, 0), pady=5)

        lbl("Start (TT.MM.JJJJ HH:MM:SS):", 1)
        s_dt = datetime.fromisoformat(entry['start'])
        self.start_var = tk.StringVar(value=s_dt.strftime(self.FMT))
        ent(self.start_var).grid(row=1, column=1, padx=(10, 0), pady=5)

        lbl("Ende (leer = laeuft):", 2)
        end_str = ''
        if entry.get('end'):
            end_str = datetime.fromisoformat(entry['end']).strftime(self.FMT)
        self.end_var = tk.StringVar(value=end_str)
        ent(self.end_var).grid(row=2, column=1, padx=(10, 0), pady=5)

        lbl("Beschreibung:", 3)
        self.desc_txt = tk.Text(pad, width=32, height=4,
                                bg=BG_ROW, fg=FG, insertbackground=FG,
                                relief='flat', font=('Segoe UI', 10), bd=4, wrap='word')
        self.desc_txt.insert('1.0', entry.get('description') or '')
        self.desc_txt.grid(row=3, column=1, padx=(10, 0), pady=5, sticky='w')

        bf = tk.Frame(pad, bg=BG_PANEL)
        bf.grid(row=4, column=0, columnspan=2, pady=(14, 0))
        tk.Button(bf, text="Speichern", relief='flat',
                  font=('Segoe UI', 9), padx=14, pady=6, cursor='hand2',
                  command=self._save, **BTN_ACCENT).pack(side='left', padx=4)
        tk.Button(bf, text="Abbrechen", relief='flat',
                  font=('Segoe UI', 9), padx=14, pady=6, cursor='hand2',
                  command=self.destroy, **BTN_NEUTRAL).pack(side='left', padx=4)

        self.bind('<Escape>', lambda _: self.destroy())
        self.wait_window()

    def _save(self):
        try:
            s_dt = datetime.strptime(self.start_var.get().strip(), self.FMT)
        except ValueError:
            messagebox.showwarning("Fehler", "Start ungueltig (TT.MM.JJJJ HH:MM:SS).", parent=self)
            return
        end_str = self.end_var.get().strip()
        e_dt = None
        if end_str:
            try:
                e_dt = datetime.strptime(end_str, self.FMT)
            except ValueError:
                messagebox.showwarning("Fehler", "Ende ungueltig (TT.MM.JJJJ HH:MM:SS).", parent=self)
                return
            if e_dt <= s_dt:
                messagebox.showwarning("Fehler", "Ende muss nach Start liegen.", parent=self)
                return
        else:
            # Open end requested — make sure no other entry is already running
            other_open = next((x for x in self.data['entries']
                               if x is not self.entry and not x.get('end')), None)
            if other_open:
                messagebox.showwarning(
                    "Fehler",
                    "Es laeuft bereits ein anderer Eintrag - "
                    "es kann nur ein Eintrag offen sein.",
                    parent=self)
                return
        cat = next((c for c in self.categories if c['name'] == self.cat_var.get()), None)
        if not cat:
            messagebox.showwarning("Fehler", "Kategorie ungueltig.", parent=self)
            return

        self.result = {
            'category_id': cat['id'],
            'start':       s_dt.isoformat(timespec='seconds'),
            'end':         e_dt.isoformat(timespec='seconds') if e_dt else None,
            'description': self.desc_txt.get('1.0', 'end').strip(),
        }
        self.destroy()

# ---------------------------------------------------------------------------
# Manage Entries Dialog (browse / edit / delete)
# ---------------------------------------------------------------------------

class ManageEntriesDialog(tk.Toplevel):
    def __init__(self, parent, data, on_change):
        super().__init__(parent)
        self.configure(bg=BG_PANEL)
        self.title("Eintraege verwalten")
        self.resizable(True, True)
        self.minsize(700, 420)
        self.data = data
        self.on_change = on_change
        self.transient(parent)
        self.grab_set()
        apply_dark_title_bar(self)
        self.geometry(f"760x500+{parent.winfo_rootx()+30}+{parent.winfo_rooty()+30}")

        top = tk.Frame(self, bg=BG_PANEL, padx=14, pady=10)
        top.pack(fill='x')

        tk.Label(top, text="Zeitraum:", bg=BG_PANEL, fg=FG_DIM,
                 font=('Segoe UI', 9)).pack(side='left')
        self.range_var = tk.StringVar(value='Heute')
        for label in ('Heute', 'Diese Woche', 'Diesen Monat', 'Alle'):
            tk.Radiobutton(
                top, text=label, value=label, variable=self.range_var,
                bg=BG_PANEL, fg=FG, selectcolor=BG_ROW,
                activebackground=BG_PANEL, activeforeground=FG,
                font=('Segoe UI', 9), command=self._refresh,
            ).pack(side='left', padx=4)

        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *_: self._refresh())
        tk.Label(top, text="  Suche:", bg=BG_PANEL, fg=FG_DIM,
                 font=('Segoe UI', 9)).pack(side='left', padx=(12, 4))
        tk.Entry(top, textvariable=self.search_var, width=20,
                 bg=BG_ROW, fg=FG, insertbackground=FG,
                 relief='flat', font=('Segoe UI', 9), bd=3).pack(side='left')

        hdr = tk.Frame(self, bg=BG, padx=14, pady=6)
        hdr.pack(fill='x')
        for text, w, anchor in [
            ('Datum',        12, 'w'),
            ('Start',         9, 'w'),
            ('Ende',          9, 'w'),
            ('Dauer',         8, 'w'),
            ('Kategorie',    18, 'w'),
            ('Beschreibung',  0, 'w'),
        ]:
            tk.Label(hdr, text=text, bg=BG, fg=FG_DIM,
                     font=('Segoe UI', 9, 'bold'),
                     width=w if w else None, anchor=anchor).pack(side='left', padx=4)

        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill='both', expand=True)
        self._canvas = tk.Canvas(body, bg=BG_PANEL, highlightthickness=0, bd=0)
        self._canvas.pack(side='left', fill='both', expand=True)
        sb = tk.Scrollbar(body, orient='vertical', command=self._canvas.yview)
        sb.pack(side='right', fill='y')
        self._canvas.configure(yscrollcommand=sb.set)
        self._inner = tk.Frame(self._canvas, bg=BG_PANEL)
        self._win = self._canvas.create_window((0, 0), window=self._inner, anchor='nw')
        self._inner.bind('<Configure>', lambda _e: self._canvas.configure(
            scrollregion=self._canvas.bbox('all')))
        self._canvas.bind('<Configure>', lambda e: self._canvas.itemconfigure(self._win, width=e.width))

        def _wheel(e):
            self._canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units')
        self._wheel_fn = _wheel
        # Bind directly to canvas; _refresh re-binds to child widgets after each rebuild
        self._canvas.bind('<MouseWheel>', _wheel)

        ft = tk.Frame(self, bg=BG_PANEL, padx=14, pady=10)
        ft.pack(fill='x')
        self.summary_lbl = tk.Label(ft, text="", bg=BG_PANEL, fg=FG_DIM,
                                    font=('Segoe UI', 9))
        self.summary_lbl.pack(side='left')
        tk.Button(ft, text="Schliessen", relief='flat',
                  font=('Segoe UI', 9), padx=14, pady=6, cursor='hand2',
                  command=self.destroy, **BTN_NEUTRAL).pack(side='right')
        flatbtn(ft, "+ Nachtragen", BTN_GREEN, self._add,
                pady=6).pack(side='right', padx=(0, 6))

        self._refresh()
        self.bind('<Escape>', lambda _: self.destroy())
        self.wait_window()

    def _filtered_entries(self):
        today = date.today()
        rng = self.range_var.get()
        if rng == 'Heute':
            from_d = today
        elif rng == 'Diese Woche':
            from_d = today - timedelta(days=today.weekday())
        elif rng == 'Diesen Monat':
            from_d = today.replace(day=1)
        else:
            from_d = None

        q = (self.search_var.get() or '').strip().lower()
        cat_by_id = {c['id']: c for c in self.data['categories']}

        rows = []
        for e in self.data['entries']:
            try:
                s_dt = datetime.fromisoformat(e['start'])
            except ValueError:
                continue
            if from_d and s_dt.date() < from_d:
                continue
            cat = cat_by_id.get(e['category_id'])
            cat_name = cat['name'] if cat else '?'
            if q:
                desc = (e.get('description') or '').lower()
                if q not in desc and q not in cat_name.lower():
                    continue
            rows.append((s_dt, e, cat))
        rows.sort(key=lambda r: r[0], reverse=True)
        return rows

    def _refresh(self):
        for w in self._inner.winfo_children():
            w.destroy()

        rows = self._filtered_entries()
        total_sec = 0

        if not rows:
            tk.Label(self._inner,
                     text="Keine Eintraege im gewaehlten Zeitraum.",
                     bg=BG_PANEL, fg=FG_DIM, font=('Segoe UI', 10),
                     pady=20).pack()
        else:
            for s_dt, e, cat in rows:
                try:
                    end_dt = datetime.fromisoformat(e['end']) if e.get('end') else None
                except (ValueError, TypeError):
                    end_dt = None
                dur = ((end_dt or datetime.now()) - s_dt).total_seconds()
                total_sec += dur
                self._row(e, cat, s_dt, end_dt, dur)

        self.summary_lbl.config(
            text=f"{len(rows)} Eintrag(e) – Gesamt: {fmt_hm(total_sec)}"
        )
        _bind_tree(self._inner, '<MouseWheel>', self._wheel_fn)

    def _row(self, e, cat, s_dt, end_dt, dur):
        bg = BG_ROW
        row = tk.Frame(self._inner, bg=bg)
        row.pack(fill='x', pady=1, padx=2)

        color = cat['color'] if cat else FG_DIM
        swatch(row, color, width=4).pack(side='left', fill='y')

        def cell(text, w, anchor='w'):
            tk.Label(row, text=text, bg=bg, fg=FG,
                     font=('Segoe UI', 9), width=w if w else None,
                     anchor=anchor, padx=4, pady=6).pack(side='left', padx=4)

        cell(s_dt.strftime('%d.%m.%Y'), 12)
        cell(s_dt.strftime('%H:%M:%S'), 9)
        cell(end_dt.strftime('%H:%M:%S') if end_dt else '— laeuft', 9)
        cell(fmt_hm(dur), 8)
        cell((cat['name'] if cat else '?'), 18)

        desc = (e.get('description') or '').replace('\n', ' ')
        if len(desc) > 60:
            desc = desc[:57] + '...'
        tk.Label(row, text=desc, bg=bg, fg=FG_DIM,
                 font=('Segoe UI', 9), anchor='w',
                 padx=4, pady=6).pack(side='left', fill='x', expand=True)

        btns = tk.Frame(row, bg=bg)
        btns.pack(side='right', padx=4)
        iconbtn(btns, "✏", "Bearbeiten",
                ACCENT, lambda ent=e: self._edit(ent)).pack(side='left', padx=2)
        iconbtn(btns, "🗑", "Loeschen",
                RED, lambda ent=e: self._delete(ent)).pack(side='left', padx=2)

    def _add(self):
        """Manually add a past entry ("nachtragen")."""
        if not self.data['categories']:
            messagebox.showwarning("Fehler", "Bitte zuerst eine Kategorie anlegen.",
                                   parent=self)
            return
        now  = datetime.now().replace(microsecond=0)
        cats = active_categories(self.data) or self.data['categories']
        template = {
            'id':          str(uuid.uuid4()),
            'category_id': cats[0]['id'],
            'start':       (now - timedelta(hours=1)).isoformat(timespec='seconds'),
            'end':         now.isoformat(timespec='seconds'),
            'description': '',
        }
        dlg = EditEntryDialog(self, template, self.data, title="Eintrag nachtragen")
        if dlg.result:
            template.update(dlg.result)
            self.data['entries'].append(template)
            save_data(self.data)
            self.on_change()
            self._refresh()

    def _edit(self, entry):
        dlg = EditEntryDialog(self, entry, self.data)
        if dlg.result:
            entry.update(dlg.result)
            save_data(self.data)
            self.on_change()
            self._refresh()

    def _delete(self, entry):
        if not messagebox.askyesno(
                "Loeschen",
                "Diesen Eintrag wirklich loeschen?",
                parent=self):
            return
        try:
            self.data['entries'].remove(entry)
        except ValueError:
            return
        save_data(self.data)
        self.on_change()
        self._refresh()

# ---------------------------------------------------------------------------
# Report Dialog
# ---------------------------------------------------------------------------

class ReportDialog(tk.Toplevel):
    def __init__(self, parent, data):
        super().__init__(parent)
        self.configure(bg=BG_PANEL)
        self.title("Report generieren")
        self.resizable(False, False)
        self.data = data
        self.transient(parent)
        self.grab_set()
        apply_dark_title_bar(self)
        self.geometry(f"+{parent.winfo_rootx()+60}+{parent.winfo_rooty()+60}")

        today = date.today()
        first = today.replace(day=1)

        pad = tk.Frame(self, bg=BG_PANEL, padx=22, pady=18)
        pad.pack(fill='both', expand=True)

        def row_lbl(text, r):
            tk.Label(pad, text=text, bg=BG_PANEL, fg=FG_DIM,
                     font=('Segoe UI', 9)).grid(row=r, column=0, sticky='w', pady=5)

        def row_entry(var):
            return tk.Entry(pad, textvariable=var, width=14,
                            bg=BG_ROW, fg=FG, insertbackground=FG,
                            relief='flat', font=('Segoe UI', 10), bd=4)

        row_lbl("Von (TT.MM.JJJJ):", 0)
        self.from_var = tk.StringVar(value=first.strftime('%d.%m.%Y'))
        row_entry(self.from_var).grid(row=0, column=1, padx=(10, 0), pady=5)

        row_lbl("Bis (TT.MM.JJJJ):", 1)
        self.to_var = tk.StringVar(value=today.strftime('%d.%m.%Y'))
        row_entry(self.to_var).grid(row=1, column=1, padx=(10, 0), pady=5)

        qf = tk.Frame(pad, bg=BG_PANEL)
        qf.grid(row=2, column=0, columnspan=2, pady=8, sticky='w')
        for label, cmd in [("Diese Woche", self._this_week),
                           ("Letzte Woche", self._last_week),
                           ("Diesen Monat", self._this_month)]:
            tk.Button(qf, text=label, bg=BG_ROW, fg=FG_DIM, relief='flat',
                      font=('Segoe UI', 8), padx=8, pady=4, cursor='hand2',
                      activebackground=BG_ROW, command=cmd).pack(side='left', padx=2)

        bf = tk.Frame(pad, bg=BG_PANEL)
        bf.grid(row=3, column=0, columnspan=2, pady=(12, 0))
        tk.Button(bf, text="Report im Browser oeffnen", bg=ACCENT, fg=FG, relief='flat',
                  font=('Segoe UI', 9), padx=14, pady=6, cursor='hand2',
                  activebackground=ACCENT, command=self._generate).pack(side='left', padx=4)
        tk.Button(bf, text="CSV exportieren", bg=GREEN, fg=FG, relief='flat',
                  font=('Segoe UI', 9), padx=14, pady=6, cursor='hand2',
                  activebackground=GREEN, command=self._export_csv).pack(side='left', padx=4)
        tk.Button(bf, text="Schliessen", bg=BG_ROW, fg=FG, relief='flat',
                  font=('Segoe UI', 9), padx=14, pady=6, cursor='hand2',
                  activebackground=BG_ROW, command=self.destroy).pack(side='left', padx=4)

        self.bind('<Return>', lambda _: self._generate())
        self.bind('<Escape>', lambda _: self.destroy())
        self.wait_window()

    def _parse_range(self):
        try:
            fd = datetime.strptime(self.from_var.get().strip(), '%d.%m.%Y').date()
            td = datetime.strptime(self.to_var.get().strip(), '%d.%m.%Y').date()
            return fd, td
        except ValueError:
            messagebox.showwarning("Fehler", "Ungueltige Eingabe – Format: TT.MM.JJJJ", parent=self)
            return None

    def _export_csv(self):
        rng = self._parse_range()
        if not rng:
            return
        fd, td = rng
        default_name = f"timetracker_{fd.isoformat()}_{td.isoformat()}.csv"
        path = filedialog.asksaveasfilename(
            parent=self,
            title="CSV speichern",
            defaultextension='.csv',
            initialfile=default_name,
            filetypes=[('CSV (Excel)', '*.csv'), ('Alle Dateien', '*.*')],
        )
        if not path:
            return

        cat_by_id = {c['id']: c for c in self.data['categories']}
        rows = []
        for e in self.data['entries']:
            try:
                s_dt = datetime.fromisoformat(e['start'])
            except ValueError:
                continue
            if not (fd <= s_dt.date() <= td):
                continue
            try:
                end_dt = datetime.fromisoformat(e['end']) if e.get('end') else None
            except (ValueError, TypeError):
                end_dt = None
            dur_sec = ((end_dt or datetime.now()) - s_dt).total_seconds()
            cat = cat_by_id.get(e['category_id'])
            rows.append((s_dt, end_dt, dur_sec, cat, e))
        rows.sort(key=lambda r: r[0])

        try:
            # Excel opens UTF-8 with BOM correctly; semicolon delimiter for German locale
            with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f, delimiter=';')
                w.writerow(['Datum', 'Start', 'Ende', 'Dauer (h)',
                            'Kategorie', 'Task-Nr.', 'Beschreibung', 'Laeuft'])
                for s_dt, end_dt, dur_sec, cat, e in rows:
                    w.writerow([
                        s_dt.strftime('%d.%m.%Y'),
                        s_dt.strftime('%H:%M:%S'),
                        end_dt.strftime('%H:%M:%S') if end_dt else '',
                        f"{dur_sec / 3600:.2f}".replace('.', ','),
                        cat['name'] if cat else '',
                        (cat.get('task_number') if cat else '') or '',
                        (e.get('description') or '').replace('\r\n', ' ').replace('\n', ' '),
                        '' if end_dt else 'ja',
                    ])
        except OSError as ex:
            messagebox.showerror("Fehler", f"CSV konnte nicht geschrieben werden:\n{ex}", parent=self)
            return

        if messagebox.askyesno("Export erfolgreich",
                               f"{len(rows)} Eintrag(e) exportiert nach:\n{path}\n\nDatei oeffnen?",
                               parent=self):
            try:
                if sys.platform == 'win32':
                    os.startfile(path)  # type: ignore[attr-defined]
                else:
                    webbrowser.open('file:///' + path.replace(os.sep, '/'))
            except OSError:
                pass

    def _set(self, fd, td):
        self.from_var.set(fd.strftime('%d.%m.%Y'))
        self.to_var.set(td.strftime('%d.%m.%Y'))

    def _this_week(self):
        t = date.today(); self._set(t - timedelta(days=t.weekday()), t)

    def _last_week(self):
        t = date.today(); lm = t - timedelta(days=t.weekday() + 7)
        self._set(lm, lm + timedelta(days=6))

    def _this_month(self):
        t = date.today(); self._set(t.replace(day=1), t)

    def _generate(self):
        rng = self._parse_range()
        if not rng:
            return
        fd, td = rng
        html_doc = generate_report(self.data, fd, td)
        # Fixed filename so old reports don't accumulate in %TEMP%
        out = Path(tempfile.gettempdir()) / 'timetracker_report.html'
        try:
            out.write_text(html_doc, encoding='utf-8')
        except OSError:
            tmp = tempfile.NamedTemporaryFile('w', suffix='.html',
                                              delete=False, encoding='utf-8')
            tmp.write(html_doc)
            tmp.close()
            out = Path(tmp.name)
        webbrowser.open(out.as_uri())
        self.destroy()

# ---------------------------------------------------------------------------
# Work Description Dialog
# ---------------------------------------------------------------------------

class WorkDescriptionDialog(tk.Toplevel):
    def __init__(self, parent, cat_name, cat_color, duration_sec):
        super().__init__(parent)
        self.configure(bg=BG_PANEL)
        self.title("Was hast du gemacht?")
        self.resizable(False, False)
        self.result = None          # None = skipped, str = description
        self.transient(parent)
        self.grab_set()
        apply_dark_title_bar(self)
        self.geometry(f"+{parent.winfo_rootx()+60}+{parent.winfo_rooty()+80}")

        outer = tk.Frame(self, bg=BG_PANEL, padx=22, pady=18)
        outer.pack(fill='both', expand=True)

        # Category + duration context
        ctx = tk.Frame(outer, bg=BG_ROW, padx=12, pady=8)
        ctx.pack(fill='x', pady=(0, 14))
        swatch(ctx, cat_color, width=4).pack(side='left', fill='y')
        info = tk.Frame(ctx, bg=BG_ROW, padx=10)
        info.pack(side='left')
        tk.Label(info, text=cat_name, bg=BG_ROW, fg=FG,
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        tk.Label(info, text=f"Dauer: {fmt_hm(duration_sec)}", bg=BG_ROW, fg=FG_DIM,
                 font=('Segoe UI', 8)).pack(anchor='w')

        # Prompt
        tk.Label(outer, text="Kurze Beschreibung der Taetigkeit:",
                 bg=BG_PANEL, fg=FG_DIM,
                 font=('Segoe UI', 9)).pack(anchor='w', pady=(0, 5))

        self.text = tk.Text(outer, width=42, height=3,
                            bg=BG_ROW, fg=FG, insertbackground=FG,
                            relief='flat', font=('Segoe UI', 10),
                            padx=8, pady=6, wrap='word')
        self.text.pack(fill='x')
        self.after(50, lambda: (self.focus_force(), self.text.focus_set()))

        # Buttons
        bf = tk.Frame(outer, bg=BG_PANEL)
        bf.pack(fill='x', pady=(14, 0))
        tk.Button(bf, text="Speichern", bg=ACCENT, fg=FG, relief='flat',
                  font=('Segoe UI', 9), padx=14, pady=6, cursor='hand2',
                  activebackground=ACCENT,
                  command=self._save).pack(side='left', padx=(0, 6))
        tk.Button(bf, text="Ueberspringen", bg=BG_ROW, fg=FG_DIM, relief='flat',
                  font=('Segoe UI', 9), padx=14, pady=6, cursor='hand2',
                  activebackground=BG_ROW,
                  command=self.destroy).pack(side='left')

        # Enter saves, Escape skips
        self.text.bind('<Return>',         lambda _: self._save())
        self.text.bind('<Control-Return>', lambda e: self.text.insert('insert', '\n'))
        self.bind('<Escape>',              lambda _: self.destroy())
        self.wait_window()

    def _save(self):
        text = self.text.get('1.0', 'end').strip()
        self.result = text if text else None
        self.destroy()


# ---------------------------------------------------------------------------
# Info Dialog
# ---------------------------------------------------------------------------

class InfoDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.configure(bg=BG_PANEL)
        self.title("Time Tracker – Info")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        apply_dark_title_bar(self)
        self.geometry(f"+{parent.winfo_rootx()+40}+{parent.winfo_rooty()+40}")

        outer = tk.Frame(self, bg=BG_PANEL, padx=24, pady=20)
        outer.pack(fill='both', expand=True)

        # Title
        tk.Label(outer, text="Time Tracker", bg=BG_PANEL, fg=FG,
                 font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        tk.Label(outer, text="Zeiterfassung fuer ServiceNow-Rapportierung",
                 bg=BG_PANEL, fg=FG_DIM,
                 font=('Segoe UI', 9)).pack(anchor='w', pady=(2, 14))

        def section(title):
            tk.Frame(outer, bg=ACCENT, height=1).pack(fill='x', pady=(6, 6))
            tk.Label(outer, text=title, bg=BG_PANEL, fg=ACCENT,
                     font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(0, 4))

        def line(text, indent=False):
            tk.Label(outer, text=("    " if indent else "") + text,
                     bg=BG_PANEL, fg=FG if not indent else FG_DIM,
                     font=('Segoe UI', 9), justify='left', anchor='w',
                     wraplength=400).pack(anchor='w', pady=1)

        # --- Bedienung ---
        section("Bedienung")
        line("Klick auf eine Kategorie  →  startet die Zeiterfassung")
        line("Nochmals auf dieselbe klicken  →  kein Wechsel (laeuft weiter)")
        line("Klick auf andere Kategorie  →  stoppt die alte, startet die neue")
        line("Stop-Button  →  beendet die laufende Erfassung")

        # --- Kategorien ---
        section("Kategorien")
        line("'Kategorien'-Button  →  Kategorien anlegen, bearbeiten, loeschen")
        line("Jede Kategorie hat einen Namen, eine ServiceNow Task-Nummer und eine Farbe")
        line("Die Task-Nummer erscheint im Report und kann direkt in ServiceNow eingetragen werden")

        # --- Report ---
        section("Report")
        line("'Report'-Button  →  Zeitraum waehlen, HTML-Report im Browser oeffnen")
        line("Der Report enthaelt:")
        line("Zusammenfassung: Gesamtstunden pro Kategorie / Task", indent=True)
        line("Tagesjournal: alle Eintraege chronologisch mit Start- und Stoppzeit", indent=True)
        line("Pausen >= 5 Minuten werden im Journal automatisch markiert", indent=True)

        # --- Speicherorte ---
        section("Speicherorte")
        line("Datendatei (Kategorien + Zeiteintraege):")
        line(str(DATA_FILE), indent=True)
        line("Konfigurationsdatei (gespeicherter Pfad):")
        line(str(CONFIG_FILE), indent=True)
        line("Format: JSON – direkt lesbar und sicherbar")

        # --- Pfad aendern ---
        section("Speicherort aendern")
        line("'Daten'-Button unten rechts  →  Menue mit Pfad, Explorer-Link und Aendern-Option")
        line("Tipp: OneDrive- oder Netzwerkordner waehlen fuer automatische Synchronisation")
        line("Vorhandene Daten muessen manuell in den neuen Ordner kopiert werden")

        tk.Frame(outer, bg=BG_ROW, height=1).pack(fill='x', pady=(14, 10))
        tk.Button(outer, text="Schliessen", bg=BG_ROW, fg=FG, relief='flat',
                  font=('Segoe UI', 9), padx=16, pady=6, cursor='hand2',
                  activebackground=BG_ROW, command=self.destroy).pack(anchor='e')

        self.bind('<Escape>', lambda _: self.destroy())
        self.bind('<Return>', lambda _: self.destroy())
        self.wait_window()


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Time Tracker")
        self.configure(bg=BG)
        try:
            self.iconbitmap(resource_path('stopwatch.ico'))
        except tk.TclError:
            pass  # icon file missing — use default
        apply_dark_title_bar(self)
        self.resizable(True, True)
        self.minsize(380, 260)

        self.data             = load_data()
        self._after           = None
        self._cat_time_labels = {}

        # Cache of today's completed-entry totals (see _today_totals)
        self._totals_cache     = None
        self._totals_cache_day = None

        # Widget / pin state
        self._mini      = False
        self._topmost   = False
        self._flyout    = None
        self._hide_id   = None
        self._save_id   = None
        self._drag_ox   = 0
        self._drag_oy   = 0

        self._last_was_running = False   # used in _tick to detect run→stop transition

        # Idle tracking
        self._idle_began_at    = None   # datetime when threshold first crossed
        self._idle_prompt_open = False

        # Config is kept in memory; _save_window_state writes it back on change
        self._cfg = cfg = load_config()
        if cfg.get('topmost'):
            self._topmost = True
            self.attributes('-topmost', True)
        self._grid_view = cfg.get('grid_view', False)
        self._full_w = cfg.get('win_w', 420)
        self._full_h = cfg.get('win_h', 500)

        def cfg_num(key, default):
            try:
                return float(cfg.get(key, default))
            except (TypeError, ValueError):
                return float(default)

        # Daily target (hours); 0 disables the progress display
        self._daily_target_sec = round(max(0.0, cfg_num('daily_target_hours', 8.2)) * 3600)
        self._progress_frac    = 0.0

        # "Tracking vergessen?" reminder — minutes without a running timer
        # before a hint appears (0 disables), limited to these workday hours
        self._remind_min      = cfg_num('remind_no_tracking_min', 30)
        self._remind_from_h   = int(cfg_num('remind_from_hour', 8))
        self._remind_to_h     = int(cfg_num('remind_to_hour', 17))
        self._remind_open     = False
        self._untracked_since = datetime.now()
        if 'win_x' in cfg and 'win_y' in cfg:
            self.geometry(f"{self._full_w}x{self._full_h}+{cfg['win_x']}+{cfg['win_y']}")
        else:
            self.geometry(f"{self._full_w}x{self._full_h}")

        self._build_ui()
        self._refresh()
        self._tick()
        self.bind('<Configure>', self._on_configure)

        # Enter mini mode after UI is fully drawn
        if cfg.get('mini'):
            self.after(100, self._toggle_mini)

        # Detect an entry left running from a previous day (crash / forgot to stop)
        self.after(300, self._check_stale_running)

    def _check_stale_running(self):
        run = running_entry(self.data)
        if not run:
            return
        try:
            s = datetime.fromisoformat(run['start'])
        except (ValueError, TypeError):
            return
        if s.date() >= date.today():
            return
        cat = next((c for c in self.data['categories']
                    if c['id'] == run['category_id']), None)
        name = cat['name'] if cat else '?'
        stop = messagebox.askyesno(
            "Laufender Eintrag gefunden",
            f"\"{name}\" laeuft noch seit {s.strftime('%d.%m.%Y %H:%M')} "
            "(vor heute gestartet).\n\n"
            "Ja  = Eintrag am Ende des Starttags stoppen (23:59:59)\n"
            "Nein = weiterlaufen lassen",
            parent=self,
        )
        if stop:
            end = s.replace(hour=23, minute=59, second=59, microsecond=0)
            run['end'] = end.isoformat(timespec='seconds')
            save_data(self.data)
            self._refresh()

    def _today_totals(self):
        """Seconds per category for today.

        Totals of *completed* entries are cached (rebuilt on data change via
        _refresh, or on day rollover); only the running entry is computed live,
        so the per-second tick stays O(1) instead of re-parsing every entry.
        Entries are attributed entirely to their start day (no midnight split).
        """
        today_str = date.today().isoformat()
        if self._totals_cache is None or self._totals_cache_day != today_str:
            totals = {}
            for e in self.data['entries']:
                if not e.get('end') or not e['start'].startswith(today_str):
                    continue
                try:
                    s   = datetime.fromisoformat(e['start'])
                    end = datetime.fromisoformat(e['end'])
                except (ValueError, TypeError):
                    continue
                cid = e['category_id']
                totals[cid] = totals.get(cid, 0) + (end - s).total_seconds()
            self._totals_cache     = totals
            self._totals_cache_day = today_str

        totals = dict(self._totals_cache)
        run = running_entry(self.data)
        if run and run['start'].startswith(today_str):
            try:
                s   = datetime.fromisoformat(run['start'])
                cid = run['category_id']
                totals[cid] = totals.get(cid, 0) + max(
                    0, (datetime.now() - s).total_seconds())
            except (ValueError, TypeError):
                pass
        return totals

    # ------------------------------------------------------------------
    def _build_ui(self):
        self._hdr = tk.Frame(self, bg=BG, padx=14, pady=10)
        self._hdr.pack(fill='x')

        self.status_lbl = tk.Label(self._hdr, text="Nicht aktiv",
                                   font=('Segoe UI', 11, 'bold'),
                                   bg=BG, fg=FG, anchor='w')
        self.status_lbl.pack(side='left', fill='x', expand=True)

        # Pack right-to-left so the timer anchors right and buttons sit left of it
        self._mini_btn = tk.Button(self._hdr, text='⊟  Mini',
                                   relief='flat', font=('Segoe UI', 9),
                                   padx=8, pady=3, cursor='hand2',
                                   command=self._toggle_mini, **BTN_NEUTRAL)
        self._mini_btn.pack(side='right', padx=(0, 4))

        _grid_style = BTN_ACTIVE if self._grid_view else {**BTN_NEUTRAL, 'fg': FG_DIM}
        _grid_text  = '⊞  Raster ✓' if self._grid_view else '⊞  Raster'
        self._grid_btn = tk.Button(self._hdr, text=_grid_text,
                                   relief='flat', font=('Segoe UI', 9),
                                   padx=8, pady=3, cursor='hand2',
                                   command=self._toggle_grid, **_grid_style)
        self._grid_btn.pack(side='right', padx=(0, 4))

        self._pin_btn = tk.Button(self._hdr, text='📌  Pin',
                                  relief='flat', font=('Segoe UI', 9),
                                  padx=8, pady=3, cursor='hand2',
                                  command=self._toggle_pin,
                                  **{**BTN_NEUTRAL, 'fg': FG_DIM})
        self._pin_btn.pack(side='right', padx=(0, 4))

        timer_block = tk.Frame(self._hdr, bg=BG)
        timer_block.pack(side='right', padx=(0, 6))

        self.timer_lbl = tk.Label(timer_block, text="00:00:00",
                                  font=('Consolas', 20, 'bold'),
                                  bg=BG, fg=FG_DIM, width=9, anchor='e')
        self.timer_lbl.pack(anchor='e')

        self.total_lbl = tk.Label(timer_block, text="Heute: 00:00:00",
                                  font=('Segoe UI', 8),
                                  bg=BG, fg=FG_DIM, anchor='e')
        self.total_lbl.pack(anchor='e')

        # Slim progress bar towards the daily target
        self._progress_bar = tk.Canvas(self, height=4, bg=BG_ROW,
                                       highlightthickness=0, bd=0)
        if self._daily_target_sec > 0:
            self._progress_bar.pack(fill='x')
        self._progress_bar.bind('<Configure>', lambda _e: self._update_progress_bar())

        self._sep1 = tk.Frame(self, bg=BG_SEP, height=1)
        self._sep1.pack(fill='x')

        # Scrollable category area --------------------------------------
        self._cat_container = tk.Frame(self, bg=BG_PANEL)
        self._cat_container.pack(fill='both', expand=True)

        self._cat_canvas = tk.Canvas(self._cat_container, bg=BG_PANEL,
                                     highlightthickness=0, bd=0)
        self._cat_canvas.pack(side='left', fill='both', expand=True)

        self._cat_scroll = tk.Scrollbar(self._cat_container, orient='vertical',
                                        command=self._cat_canvas.yview)
        self._cat_canvas.configure(yscrollcommand=self._on_cat_scrollset)

        self.cat_outer = tk.Frame(self._cat_canvas, bg=BG_PANEL, padx=8, pady=8)
        self._cat_window = self._cat_canvas.create_window(
            (0, 0), window=self.cat_outer, anchor='nw')

        def _on_inner_configure(_e):
            self._cat_canvas.configure(scrollregion=self._cat_canvas.bbox('all'))
            self._update_cat_scrollbar()
        self.cat_outer.bind('<Configure>', _on_inner_configure)

        def _on_canvas_configure(e):
            self._cat_canvas.itemconfigure(self._cat_window, width=e.width)
        self._cat_canvas.bind('<Configure>', _on_canvas_configure)

        self.bind_all('<MouseWheel>', self._on_cat_wheel)

        self._cat_scroll_active = False
        self._sep2 = tk.Frame(self, bg=BG_SEP, height=1)
        self._sep2.pack(fill='x')

        self._bot = tk.Frame(self, bg=BG, padx=10, pady=8)
        self._bot.pack(fill='x')

        def bot_btn(text, bg, cmd):
            return flatbtn(self._bot, text, bg, cmd, pady=5)

        self._stop_btn = bot_btn("Stop", RED, self._stop)
        self._stop_btn.pack(side='left', padx=3)
        bot_btn("Kategorien",  BTN_GREEN,  self._manage_cats).pack(side='left', padx=3)
        bot_btn("Eintraege",   BTN_PURPLE,  self._manage_entries).pack(side='left', padx=3)
        bot_btn("?",           BG_ROW,     self._show_info).pack(side='left', padx=3)
        bot_btn("Report",      ACCENT,     self._report).pack(side='right', padx=3)
        self._storage_btn = bot_btn("📁  Daten", BG_ROW, self._show_storage_menu)
        self._storage_btn.pack(side='right', padx=3)

    # ------------------------------------------------------------------
    def _update_today_display(self, tots):
        """Header 'Heute' label and progress bar, incl. daily target if set."""
        done = sum(tots.values())
        if self._daily_target_sec > 0:
            self._progress_frac = done / self._daily_target_sec
            reached = done >= self._daily_target_sec
            self.total_lbl.config(
                text=(f"Heute: {fmt_hms(done)} / {fmt_hm(self._daily_target_sec)}"
                      f"  ({min(self._progress_frac, 9.99) * 100:.0f}%)"),
                fg=GREEN if reached else FG_DIM)
            self._update_progress_bar()
        else:
            self.total_lbl.config(text=f"Heute: {fmt_hms(done)}", fg=FG_DIM)

    def _update_progress_bar(self):
        c = self._progress_bar
        c.delete('all')
        w    = c.winfo_width()
        frac = self._progress_frac
        if w > 1 and frac > 0:
            c.create_rectangle(0, 0, int(w * min(1.0, frac)), 6,
                               fill=GREEN if frac >= 1 else ACCENT, width=0)

    def _refresh(self):
        for w in self.cat_outer.winfo_children():
            w.destroy()
        self._cat_time_labels.clear()
        # Every data mutation goes through _refresh — rebuild the totals cache
        self._totals_cache = None

        run  = running_entry(self.data)
        act  = run['category_id'] if run else None
        tots = self._today_totals()

        self._update_today_display(tots)
        self._stop_btn.config(
            state='normal' if run else 'disabled',
            fg=FG if run else '#7a4a44',
        )

        cats = active_categories(self.data)
        if not cats:
            text = ("Noch keine Kategorien.\nKlicke auf 'Kategorien'."
                    if not self.data['categories']
                    else "Alle Kategorien sind archiviert.\nKlicke auf 'Kategorien'.")
            tk.Label(self.cat_outer, text=text,
                     bg=BG_PANEL, fg=FG_DIM, font=('Segoe UI', 10),
                     justify='center', pady=22).pack()
            return

        if self._grid_view:
            self._render_grid(act, tots, cats)
        else:
            self._render_list(act, tots, cats)

        self.update_idletasks()

    def _render_list(self, act, tots, cats):
        for cat in cats:
            is_active = cat['id'] == act
            bg = BG_ACT if is_active else BG_ROW

            row = tk.Frame(self.cat_outer, bg=bg, cursor='hand2')
            row.pack(fill='x', pady=3)

            swatch(row, cat['color'], width=5).pack(side='left', fill='y')

            mid = tk.Frame(row, bg=bg, padx=12, pady=9)
            mid.pack(side='left', fill='both', expand=True)

            tk.Label(mid, text=cat['name'],
                     font=('Segoe UI', 11, 'bold' if is_active else 'normal'),
                     bg=bg, fg=FG if is_active else FG_MUTED,
                     anchor='w').pack(anchor='w')

            task = cat.get('task_number')
            if task:
                tk.Label(mid, text=task,
                         font=('Segoe UI', 8), bg=bg,
                         fg=ACCENT if is_active else FG_DIM,
                         anchor='w').pack(anchor='w')

            right = tk.Frame(row, bg=bg, padx=12)
            right.pack(side='right', fill='y')

            time_lbl = tk.Label(right, text=fmt_hms(tots.get(cat['id'], 0)),
                                font=('Consolas', 10),
                                bg=bg, fg=ACCENT if is_active else FG_DIM)
            time_lbl.pack(anchor='e', pady=(8, 0))
            self._cat_time_labels[cat['id']] = time_lbl

            indicator = "● aktiv" if is_active else ""
            tk.Label(right, text=indicator, font=('Segoe UI', 7),
                     bg=bg, fg=GREEN).pack(anchor='e')

            self._bind_row_interaction(row, cat['id'], bg,
                                       BG_ACT_HOVER if is_active else BG_HOVER)

    def _render_grid(self, act, tots, cats):
        outer = self.cat_outer
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)

        for i, cat in enumerate(cats):
            is_active = cat['id'] == act
            bg = BG_ACT if is_active else BG_ROW
            grid_row, col = divmod(i, 2)

            card = tk.Frame(outer, bg=bg, cursor='hand2')
            card.grid(row=grid_row, column=col, padx=4, pady=4, sticky='nsew')

            # Top colour bar
            swatch(card, cat['color'], height=4).pack(fill='x')

            # Body
            body = tk.Frame(card, bg=bg, padx=10, pady=8)
            body.pack(fill='both', expand=True)

            tk.Label(body, text=cat['name'],
                     font=('Segoe UI', 10, 'bold' if is_active else 'normal'),
                     bg=bg, fg=FG if is_active else FG_MUTED,
                     anchor='w').pack(anchor='w', fill='x')

            task = cat.get('task_number')
            if task:
                tk.Label(body, text=task,
                         font=('Segoe UI', 8), bg=bg,
                         fg=ACCENT if is_active else FG_DIM,
                         anchor='w').pack(anchor='w')

            # Bottom row: active dot + time
            bot = tk.Frame(body, bg=bg)
            bot.pack(fill='x', side='bottom', pady=(6, 0))

            if is_active:
                tk.Label(bot, text="● aktiv", font=('Segoe UI', 7),
                         bg=bg, fg=GREEN).pack(side='left')

            time_lbl = tk.Label(bot, text=fmt_hms(tots.get(cat['id'], 0)),
                                font=('Consolas', 9),
                                bg=bg, fg=ACCENT if is_active else FG_DIM)
            time_lbl.pack(side='right')
            self._cat_time_labels[cat['id']] = time_lbl

            self._bind_row_interaction(card, cat['id'], bg,
                                       BG_ACT_HOVER if is_active else BG_HOVER)

    def _bind_row_interaction(self, row, cat_id, bg, bg_hover):
        """Click-to-start plus hover highlight on a category row/card,
        bound to the row and all its children (labels included)."""
        def _on_click(_e, cid=cat_id):
            self._start(cid)

        def _hover_on(_e):
            _set_bg_tree(row, bg_hover)

        def _hover_off(e):
            x, y   = e.x_root, e.y_root
            rx, ry = row.winfo_rootx(), row.winfo_rooty()
            if not (rx <= x < rx + row.winfo_width() and
                    ry <= y < ry + row.winfo_height()):
                _set_bg_tree(row, bg)

        _bind_tree(row, '<Button-1>', _on_click)
        _bind_tree(row, '<Enter>',    _hover_on)
        _bind_tree(row, '<Leave>',    _hover_off)

    # ------------------------------------------------------------------
    def _tick(self):
        run = running_entry(self.data)

        if run:
            try:
                start   = datetime.fromisoformat(run['start'])
                elapsed = (datetime.now() - start).total_seconds()
            except (ValueError, TypeError):
                elapsed = 0
            cat     = next((c for c in self.data['categories']
                            if c['id'] == run['category_id']), None)
            self.status_lbl.config(text=f"Laeuft: {cat['name']}" if cat else "Laeuft…")
            self.timer_lbl.config(text=fmt_hms(elapsed), fg=ACCENT)
        else:
            elapsed = 0
            cat     = None
            if self._last_was_running:
                # Transitioned to stopped — update labels once with final values
                self.status_lbl.config(text="Nicht aktiv")
                self.timer_lbl.config(text="00:00:00", fg=FG_DIM)

        if self._mini:
            try:
                self._mini_timer_lbl.config(text=fmt_hms(elapsed) if run else "00:00:00")
                name  = cat['name']  if cat else "Nicht aktiv"
                color = cat['color'] if cat else ACCENT
                self._mini_cat_lbl.config(text=name)
                self._mini_color_bar.config(bg=color)
                self._arrow_btn.config(bg=color, activebackground=color)
            except (tk.TclError, AttributeError):
                pass

        # Recalculate per-category totals only while a timer is running or just stopped
        if run or self._last_was_running:
            tots = self._today_totals()
            self._update_today_display(tots)
            for cid, lbl in self._cat_time_labels.items():
                try:
                    lbl.config(text=fmt_hms(tots.get(cid, 0)))
                except tk.TclError:
                    pass

        # Track how long no timer has been running (for the reminder)
        if run:
            self._untracked_since = None
        elif self._untracked_since is None:
            self._untracked_since = datetime.now()
        self._maybe_remind_tracking(run)

        self._last_was_running = bool(run)
        self._check_idle(run)
        self._after = self.after(1000, self._tick)

    def _maybe_remind_tracking(self, run):
        """Hint when no timer has been running for a while during work hours."""
        if run or self._remind_open or self._remind_min <= 0:
            return
        if self._untracked_since is None:
            return
        now = datetime.now()
        if now.weekday() >= 5:                                   # weekend
            return
        if not (self._remind_from_h <= now.hour < self._remind_to_h):
            return
        if get_idle_seconds() > 120:
            return  # user not at the PC — ask once they're back
        gap = (now - self._untracked_since).total_seconds()
        if gap < self._remind_min * 60:
            return
        self._remind_open = True
        try:
            messagebox.showinfo(
                "Zeiterfassung vergessen?",
                f"Seit {fmt_hm(gap)} laeuft keine Zeiterfassung.\n\n"
                "Falls du gearbeitet hast: ueber 'Eintraege' > '+ Nachtragen' "
                "laesst sich die Zeit nachtraeglich erfassen.",
                parent=self)
        finally:
            self._remind_open = False
            self._untracked_since = datetime.now()   # snooze for another interval

    def _check_idle(self, run):
        if self._idle_prompt_open:
            return
        idle = get_idle_seconds()
        if run and idle >= IDLE_THRESHOLD_SEC:
            if self._idle_began_at is None:
                self._idle_began_at = datetime.now() - timedelta(seconds=idle)
        elif self._idle_began_at is not None and idle < 5:
            # User is back at the keyboard
            began = self._idle_began_at
            self._idle_began_at = None
            if run:
                self._prompt_idle(run, began)

    def _prompt_idle(self, run, idle_began):
        """Ask user how to handle time spent idle while a category was running."""
        self._idle_prompt_open = True
        try:
            mins = int((datetime.now() - idle_began).total_seconds() // 60)
            cat = next((c for c in self.data['categories']
                        if c['id'] == run['category_id']), None)
            cat_name = cat['name'] if cat else '?'
            choice = messagebox.askyesnocancel(
                "Inaktivitaet erkannt",
                f"Du warst ca. {mins} Minuten inaktiv waehrend \"{cat_name}\" lief.\n\n"
                f"Inaktivitaet begann: {idle_began.strftime('%H:%M:%S')}\n\n"
                "Ja  = Eintrag bei Pause stoppen (Inaktivitaet abziehen)\n"
                "Nein = Zeit behalten (kein Stop)\n"
                "Abbrechen = Nichts unternehmen",
                parent=self,
            )
            if choice is True:
                # Verify the same entry is still running and end it at idle_began
                cur = running_entry(self.data)
                if cur and cur.get('id') == run.get('id'):
                    started = datetime.fromisoformat(cur['start'])
                    end_at = max(started, idle_began)
                    cur['end'] = end_at.isoformat(timespec='seconds')
                    save_data(self.data)
                    self._refresh()
        finally:
            self._idle_prompt_open = False

    # ------------------------------------------------------------------
    def _ask_description(self, run):
        """Show description dialog for a just-completed entry."""
        cat = next((c for c in self.data['categories']
                    if c['id'] == run['category_id']), None)
        try:
            dur = (datetime.fromisoformat(run['end'])
                   - datetime.fromisoformat(run['start'])).total_seconds()
        except (ValueError, TypeError):
            dur = 0
        dlg = WorkDescriptionDialog(
            self,
            cat_name     = cat['name']  if cat else '?',
            cat_color    = cat['color'] if cat else '#999',
            duration_sec = dur,
        )
        run['description'] = dlg.result or ''

    def _start(self, cat_id):
        run = running_entry(self.data)
        if run and run['category_id'] == cat_id:
            return
        # One shared timestamp: the old entry ends exactly when the new one
        # starts, so the time spent typing the description isn't lost.
        now_iso = datetime.now().isoformat(timespec='seconds')
        if run:
            run['end'] = now_iso
        self.data['entries'].append({
            'id':          str(uuid.uuid4()),
            'category_id': cat_id,
            'start':       now_iso,
            'end':         None,
            'description': '',
        })
        # Persist before the (blocking) description dialog — a crash while
        # typing must not lose the stop/start.
        save_data(self.data)
        self._refresh()
        if run:
            self._ask_description(run)
            save_data(self.data)

    def _stop(self):
        run = running_entry(self.data)
        if not run:
            return
        run['end'] = datetime.now().isoformat(timespec='seconds')
        save_data(self.data)   # persist the stop before the blocking dialog
        self._refresh()
        self._ask_description(run)
        save_data(self.data)

    def _manage_cats(self):
        ManageCategoriesDialog(self, self.data, self._refresh)

    def _manage_entries(self):
        ManageEntriesDialog(self, self.data, self._refresh)

    def _show_info(self):
        InfoDialog(self)

    def _report(self):
        ReportDialog(self, self.data)

    def _show_storage_menu(self):
        """Popup menu anchored to the Daten button."""
        menu = tk.Menu(self, tearoff=0,
                       bg=BG_ROW, fg=FG,
                       activebackground=BG_ACT, activeforeground=FG,
                       font=('Segoe UI', 9), relief='flat', bd=1)

        # Current path — shown greyed-out so the user can immediately see it
        path_str = str(DATA_FILE)
        display  = path_str if len(path_str) <= 54 else '...' + path_str[-51:]
        menu.add_command(label=display, state='disabled',
                         foreground=FG_DIM, background=BG_PANEL)
        menu.add_separator()
        menu.add_command(label='📂  Ordner im Explorer öffnen',
                         command=self._open_data_folder)
        menu.add_command(label='📋  Pfad kopieren',
                         command=self._copy_data_path)
        menu.add_separator()
        menu.add_command(label='📁  Speicherort ändern …',
                         command=self._change_path)

        btn = self._storage_btn
        menu.post(btn.winfo_rootx(),
                  btn.winfo_rooty() + btn.winfo_height() + 2)

    def _open_data_folder(self):
        """Open the folder that contains the data file in the OS file manager."""
        folder = str(DATA_FILE.parent)
        try:
            if sys.platform == 'win32':
                os.startfile(folder)          # type: ignore[attr-defined]
            else:
                webbrowser.open('file:///' + folder.replace(os.sep, '/'))
        except OSError:
            pass

    def _copy_data_path(self):
        """Copy the full data-file path to the clipboard."""
        try:
            self.clipboard_clear()
            self.clipboard_append(str(DATA_FILE))
            self.update()
        except tk.TclError:
            pass

    def _change_path(self):
        """Pick a new folder for the data file and restart to apply."""
        cfg    = self._cfg
        chosen = filedialog.askdirectory(
            title="Neuer Speicherort fuer timetracker_data.json",
            initialdir=cfg.get('data_dir', str(Path.home())),
            parent=self,
        )
        if not chosen:
            return
        if not messagebox.askyesno(
            "Speicherort aendern",
            f"Neuer Ordner:\n{chosen}\n\n"
            "Die App wird neu gestartet, damit die Aenderung wirksam wird.\n"
            "Vorhandene Daten am alten Speicherort bleiben erhalten.",
            parent=self,
        ):
            return
        cfg['data_dir'] = chosen
        save_config(cfg)
        if getattr(sys, 'frozen', False):
            # PyInstaller: sys.executable IS the app; sys.argv[0] would be
            # passed as a bogus file argument
            subprocess.Popen([sys.executable] + sys.argv[1:])
        else:
            subprocess.Popen([sys.executable] + sys.argv)
        self.on_close()

    # ------------------------------------------------------------------
    # Pin / Mini / Flyout
    # ------------------------------------------------------------------

    def _toggle_grid(self):
        self._grid_view = not self._grid_view
        if self._grid_view:
            self._grid_btn.config(**{**BTN_ACTIVE, 'text': '⊞  Raster ✓'})
        else:
            self._grid_btn.config(**{**BTN_NEUTRAL, 'fg': FG_DIM, 'text': '⊞  Raster'})
        self._refresh()
        self._save_window_state()

    def _toggle_pin(self):
        self._topmost = not self._topmost
        self.attributes('-topmost', self._topmost)
        if self._topmost:
            self._pin_btn.config(**{**BTN_ACTIVE, 'text': '📌  Pin ✓'})
        else:
            self._pin_btn.config(**{**BTN_NEUTRAL, 'fg': FG_DIM, 'text': '📌  Pin'})
        try:
            if self._topmost:
                self._mini_pin_btn.config(**BTN_ACTIVE)
            else:
                self._mini_pin_btn.config(**{**BTN_NEUTRAL, 'fg': FG_DIM})
        except AttributeError:
            pass
        self._save_window_state()

    def _set_cat_scroll_visible(self, needed: bool):
        """Show or hide the category scrollbar and keep the active flag in sync."""
        self._cat_scroll_active = needed
        if needed and not self._cat_scroll.winfo_ismapped():
            self._cat_scroll.pack(side='right', fill='y')
        elif not needed and self._cat_scroll.winfo_ismapped():
            self._cat_scroll.pack_forget()

    def _on_cat_scrollset(self, first, last):
        try:
            f = float(first); l = float(last)
        except ValueError:
            return
        self._cat_scroll.set(first, last)
        self._set_cat_scroll_visible((l - f) < 0.999)

    def _update_cat_scrollbar(self):
        bbox = self._cat_canvas.bbox('all')
        if not bbox:
            return
        content_h = bbox[3] - bbox[1]
        self._set_cat_scroll_visible(content_h > self._cat_canvas.winfo_height() + 1)

    def _toggle_mini(self):
        self._mini = not self._mini
        x, y = self.winfo_x(), self.winfo_y()
        if self._mini:
            for w in (self._hdr, self._progress_bar, self._sep1,
                      self._cat_container, self._sep2, self._bot):
                w.pack_forget()
            self._build_mini_bar()
            self.resizable(True, False)
            self.minsize(300, 0)
            # Drop forced height so the window shrinks to the mini bar
            self.geometry('')
            self.update_idletasks()
            self.geometry(f'+{x}+{y}')
        else:
            self._do_hide_flyout()
            if hasattr(self, '_mini_frame'):
                self._mini_frame.destroy()
            self._hdr.pack(fill='x')
            if self._daily_target_sec > 0:
                self._progress_bar.pack(fill='x')
            self._sep1.pack(fill='x')
            self._cat_container.pack(fill='both', expand=True)
            self._sep2.pack(fill='x')
            self._bot.pack(fill='x')
            self.resizable(True, True)
            self.minsize(380, 260)
            self.geometry(f'{self._full_w}x{self._full_h}+{x}+{y}')
        self._save_window_state()

    def _build_mini_bar(self):
        run = running_entry(self.data)
        cat = next((c for c in self.data['categories']
                    if c['id'] == run['category_id']), None) if run else None

        f = tk.Frame(self, bg=BG)
        f.pack(fill='x')
        self._mini_frame = f

        self._mini_color_bar = tk.Frame(f, bg=cat['color'] if cat else FG_DIM, width=6)
        self._mini_color_bar.pack(side='left', fill='y')

        mid = tk.Frame(f, bg=BG, padx=10)
        mid.pack(side='left', fill='both', expand=True)
        self._mini_cat_lbl = tk.Label(
            mid, text=cat['name'] if cat else "Nicht aktiv",
            bg=BG, fg=FG, font=('Segoe UI', 10, 'bold'), anchor='w')
        self._mini_cat_lbl.pack(side='left', pady=8)

        right = tk.Frame(f, bg=BG, padx=4)
        right.pack(side='right', fill='y')

        # ▲ Wechseln — hover reveals category flyout, coloured with active category
        cat_color = cat['color'] if cat else ACCENT
        self._arrow_btn = tk.Button(
            right, text='▲  Wechseln',
            relief='flat', font=('Segoe UI', 9, 'bold'),
            padx=10, pady=4, cursor='hand2',
            bg=cat_color, fg='#ffffff',
            activebackground=cat_color, activeforeground='#ffffff')
        self._arrow_btn.pack(side='right', padx=(4, 2), pady=6)
        self._arrow_btn.bind('<Enter>', lambda _: self._show_flyout())
        self._arrow_btn.bind('<Leave>', lambda _: self._hide_flyout_soon())

        # ⤢ Vollansicht
        tk.Button(right, text='⤢  Vollansicht',
                  relief='flat', font=('Segoe UI', 9),
                  padx=10, pady=4, cursor='hand2',
                  command=self._toggle_mini, **BTN_NEUTRAL
                  ).pack(side='right', padx=2, pady=6)

        pin_style = BTN_ACTIVE if self._topmost else {**BTN_NEUTRAL, 'fg': FG_DIM}
        self._mini_pin_btn = tk.Button(
            right, text='📌  Pin',
            relief='flat', font=('Segoe UI', 9),
            padx=10, pady=4, cursor='hand2',
            command=self._toggle_pin, **pin_style)
        self._mini_pin_btn.pack(side='right', padx=2, pady=6)

        self._mini_timer_lbl = tk.Label(
            right, text="00:00:00",
            font=('Consolas', 13, 'bold'), bg=BG, fg=ACCENT, width=8)
        self._mini_timer_lbl.pack(side='right', padx=(0, 2), pady=6)

        for w in (f, mid, self._mini_cat_lbl):
            w.bind('<Button-1>',  self._drag_start)
            w.bind('<B1-Motion>', self._drag_move)

    def _on_cat_wheel(self, e):
        """MouseWheel handler for the main-window category canvas."""
        if self._mini or not self._cat_scroll_active:
            return
        try:
            cx = self._cat_canvas.winfo_rootx()
            cy = self._cat_canvas.winfo_rooty()
            cw = self._cat_canvas.winfo_width()
            ch = self._cat_canvas.winfo_height()
            if not (cx <= e.x_root < cx + cw and cy <= e.y_root < cy + ch):
                return
        except tk.TclError:
            return
        self._cat_canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units')

    def _show_flyout(self):
        self._cancel_flyout_hide()
        if self._flyout and self._flyout.winfo_exists():
            return

        fw = tk.Toplevel(self)
        fw.overrideredirect(True)
        fw.configure(bg=BG)
        fw.attributes('-topmost', True)
        self._flyout = fw

        fw.bind('<Enter>', lambda _: self._cancel_flyout_hide())
        fw.bind('<Leave>', lambda _: self._hide_flyout_soon())

        run  = running_entry(self.data)
        act  = run['category_id'] if run else None
        tots = self._today_totals()
        fly_cats = active_categories(self.data)

        if not fly_cats:
            tk.Label(fw, text="Keine Kategorien", bg=BG, fg=FG_DIM,
                     font=('Segoe UI', 9), padx=14, pady=10).pack()
        else:
            max_list_h = int(self.winfo_screenheight() * 0.60)  # cap flyout at 60 % of screen

            cat_canvas = tk.Canvas(fw, bg=BG, highlightthickness=0, bd=0)
            cat_sb     = tk.Scrollbar(fw, orient='vertical', command=cat_canvas.yview)
            cat_canvas.configure(yscrollcommand=cat_sb.set)

            cat_inner = tk.Frame(cat_canvas, bg=BG)
            cat_win   = cat_canvas.create_window((0, 0), window=cat_inner, anchor='nw')

            for cat in fly_cats:
                is_active = cat['id'] == act
                bg        = BG_ACT if is_active else BG_ROW
                bg_hover  = BG_ACT_HOVER if is_active else BG_HOVER

                row = tk.Frame(cat_inner, bg=bg, cursor='hand2')
                row.pack(fill='x', padx=4, pady=1)
                swatch(row, cat['color'], width=4).pack(side='left', fill='y')

                mid = tk.Frame(row, bg=bg, padx=10, pady=7)
                mid.pack(side='left', fill='both', expand=True)
                tk.Label(mid, text=cat['name'], bg=bg,
                         fg=FG if is_active else FG_MUTED,
                         font=('Segoe UI', 9, 'bold' if is_active else 'normal')
                         ).pack(anchor='w')

                secs = tots.get(cat['id'], 0)
                tk.Label(row, text=fmt_hms(secs),
                         font=('Consolas', 8), bg=bg,
                         fg=ACCENT if is_active else FG_DIM,
                         padx=8).pack(side='right')

                def _on_click(_, cid=cat['id']):
                    self._do_hide_flyout()
                    self._start(cid)

                def _hover_on(_, r=row, bh=bg_hover):
                    _set_bg_tree(r, bh)

                def _hover_off(event, r=row, b=bg):
                    x, y = event.x_root, event.y_root
                    rx, ry = r.winfo_rootx(), r.winfo_rooty()
                    if not (rx <= x < rx + r.winfo_width() and
                            ry <= y < ry + r.winfo_height()):
                        _set_bg_tree(r, b)

                _bind_tree(row, '<Button-1>', _on_click)
                _bind_tree(row, '<Enter>',    _hover_on)
                _bind_tree(row, '<Leave>',    _hover_off)

            fw.update_idletasks()
            content_h = cat_inner.winfo_reqheight()
            canvas_h  = min(content_h, max_list_h)
            cat_canvas.configure(height=canvas_h,
                                 width=cat_inner.winfo_reqwidth(),
                                 scrollregion=(0, 0, cat_inner.winfo_reqwidth(), content_h))

            # Stretch inner frame to canvas width when scrollbar appears/disappears
            def _on_cat_canvas_cfg(e, cv=cat_canvas, cw=cat_win):
                cv.itemconfigure(cw, width=e.width)
            cat_canvas.bind('<Configure>', _on_cat_canvas_cfg)

            if content_h > max_list_h:
                cat_canvas.pack(side='left', fill='both', expand=True, padx=(4, 0), pady=4)
                cat_sb.pack(side='right', fill='y', pady=4)
            else:
                cat_canvas.pack(side='left', fill='both', expand=True, padx=4, pady=4)

            def _flyout_wheel(e):
                cat_canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units')
            fw.bind_all('<MouseWheel>', _flyout_wheel)
            fw.bind('<Destroy>', lambda _: self.bind_all('<MouseWheel>', self._on_cat_wheel))

        tk.Frame(fw, bg=BG_SEP, height=1).pack(fill='x', padx=4, pady=(2, 0))
        stop = tk.Frame(fw, bg=BG_ROW, cursor='hand2')
        stop.pack(fill='x', padx=4, pady=(0, 4))
        tk.Label(stop, text='■  Stop', bg=BG_ROW, fg=RED,
                 font=('Segoe UI', 9), padx=10, pady=7).pack(anchor='w')

        def _stop_hover_off(event):
            x, y = event.x_root, event.y_root
            if not (stop.winfo_rootx() <= x < stop.winfo_rootx() + stop.winfo_width() and
                    stop.winfo_rooty() <= y < stop.winfo_rooty() + stop.winfo_height()):
                _set_bg_tree(stop, BG_ROW)

        _bind_tree(stop, '<Button-1>', lambda _: [self._do_hide_flyout(), self._stop()])
        _bind_tree(stop, '<Enter>',    lambda _: _set_bg_tree(stop, '#42221d'))
        _bind_tree(stop, '<Leave>',    _stop_hover_off)

        # Position: above the arrow button (fall back to below if no room)
        fw.update_idletasks()
        bx   = self._arrow_btn.winfo_rootx()
        by   = self._arrow_btn.winfo_rooty()
        bh   = self._arrow_btn.winfo_height()
        fh   = fw.winfo_reqheight()
        fw_w = fw.winfo_reqwidth()
        x    = max(0, bx + self._arrow_btn.winfo_width() - fw_w)
        y    = by - fh - 4 if by - fh - 4 > 0 else by + bh + 4
        fw.geometry(f'+{x}+{y}')

    def _hide_flyout_soon(self):
        if self._hide_id:
            self.after_cancel(self._hide_id)
        self._hide_id = self.after(280, self._do_hide_flyout)

    def _cancel_flyout_hide(self):
        if self._hide_id:
            self.after_cancel(self._hide_id)
            self._hide_id = None

    def _do_hide_flyout(self):
        if self._flyout:
            try:
                self._flyout.destroy()
            except tk.TclError:
                pass
            self._flyout = None
        self._hide_id = None

    # ------------------------------------------------------------------
    # Drag (mini mode)
    # ------------------------------------------------------------------

    def _drag_start(self, event):
        self._drag_ox = event.x_root - self.winfo_x()
        self._drag_oy = event.y_root - self.winfo_y()

    def _drag_move(self, event):
        self.geometry(f'+{event.x_root - self._drag_ox}+{event.y_root - self._drag_oy}')

    # ------------------------------------------------------------------
    # Position / state persistence
    # ------------------------------------------------------------------

    def _on_configure(self, event):
        if event.widget is not self:
            return
        if self._save_id:
            self.after_cancel(self._save_id)
        self._save_id = self.after(400, self._save_window_state)

    def _save_window_state(self):
        cfg = self._cfg
        cfg['win_x']   = self.winfo_x()
        cfg['win_y']   = self.winfo_y()
        if not self._mini:
            self._full_w = self.winfo_width()
            self._full_h = self.winfo_height()
            cfg['win_w'] = self._full_w
            cfg['win_h'] = self._full_h
        cfg['mini']      = self._mini
        cfg['topmost']   = self._topmost
        cfg['grid_view'] = self._grid_view
        save_config(cfg)

    # ------------------------------------------------------------------
    def on_close(self):
        self._save_window_state()
        if self._after:
            self.after_cancel(self._after)
        self.destroy()


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    if not acquire_singleton():
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(
            "Time Tracker laeuft bereits",
            "Es laeuft bereits eine Instanz des Time Trackers fuer diese Datendatei.\n\n"
            f"Datei: {DATA_FILE}\n\n"
            "Bitte das vorhandene Fenster benutzen.",
            parent=root,
        )
        root.destroy()
        sys.exit(0)

    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
