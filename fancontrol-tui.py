#!/usr/bin/env python3
import os
import curses
import glob
import time

# Reduce the default 1-second ESC key delay down to 25ms
os.environ.setdefault('ESCDELAY', '25')

def is_root():
    return os.geteuid() == 0

def get_fans():
    fans = []
    for hwmon in sorted(glob.glob('/sys/class/hwmon/hwmon*')):
        for pwm_path in sorted(glob.glob(f'{hwmon}/pwm[1-9]')):
            base_pwm = os.path.basename(pwm_path)
            enable_path = f"{hwmon}/{base_pwm}_enable"
            
            name_file = f'{hwmon}/name'
            name = "Unknown"
            if os.path.exists(name_file):
                try:
                    with open(name_file, 'r') as f:
                        name = f.read().strip()
                except PermissionError:
                    pass
            
            fans.append({
                'hwmon': os.path.basename(hwmon),
                'name': name,
                'pwm_id': base_pwm,
                'pwm_path': pwm_path,
                'enable_path': enable_path if os.path.exists(enable_path) else None
            })
    return fans

def read_sysfs(path):
    if not path or not os.path.exists(path):
        return "N/A"
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except Exception:
        return "Err"

def write_sysfs(path, value):
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, 'w') as f:
            f.write(str(value))
        return True
    except Exception:
        return False

def get_mode_name(mode):
    mapping = {
        "0": "Full Spd (0)",
        "1": "Manual (1)",
        "2": "Target (2)",
        "5": "Curve (5)"
    }
    if mode == "N/A": return "No Control"
    return mapping.get(mode, f"Other ({mode})")

def show_mode_dropdown(stdscr, parent_h, parent_w):
    options = [
        ("0", "Full Speed (0)"),
        ("1", "Manual Control (1)"),
        ("2", "Target Temp (Thermal Cruise) (2)"),
        ("5", "Custom Curve (Smart Fan IV) (5)")
    ]
    
    pop_h, pop_w = 8, 40
    start_y = parent_h // 2 - pop_h // 2
    start_x = parent_w // 2 - pop_w // 2
    
    # Draw Dropdown Shadow
    stdscr.attron(curses.color_pair(4))
    for i in range(pop_h):
        stdscr.addstr(start_y + i + 1, start_x + 2, " " * pop_w)
    stdscr.attroff(curses.color_pair(4))
    stdscr.refresh()
    
    # Create Dropdown Window
    popup = curses.newwin(pop_h, pop_w, start_y, start_x)
    popup.bkgd(' ', curses.color_pair(1))
    popup.keypad(True)
    
    current_selection = 0
    
    while True:
        popup.erase()
        popup.box()
        popup.addstr(0, 2, " Select Fan Mode ", curses.A_BOLD)
        
        for idx, (val, text) in enumerate(options):
            padded_text = text.ljust(pop_w - 4) # Full width selection bar
            if idx == current_selection:
                popup.addstr(2 + idx, 2, padded_text, curses.color_pair(3))
            else:
                popup.addstr(2 + idx, 2, padded_text)
                
        popup.refresh()
        key = popup.getch()
        
        if key == curses.KEY_UP and current_selection > 0:
            current_selection -= 1
        elif key == curses.KEY_DOWN and current_selection < len(options) - 1:
            current_selection += 1
        elif key in [10, 13]: 
            return options[current_selection][0]
        elif key in [27, ord('q'), ord('Q')]: 
            return None

def draw_menu(stdscr):
    # --- UI & Color Setup ---
    curses.curs_set(0) 
    stdscr.nodelay(True) 
    stdscr.timeout(1000) 
    
    curses.start_color()
    curses.use_default_colors()
    # Pair 1: Dialog Box (Black text on White/Grey bg)
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
    # Pair 2: Desktop (White text on Blue bg)
    curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLUE)
    # Pair 3: Selection Highlight (White text on Black bg)
    curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)
    # Pair 4: Drop Shadow (Black text on Black bg)
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_BLACK)

    current_row = 0
    root_mode = is_root()
    fans = get_fans()
    
    if not fans:
        stdscr.bkgd(' ', curses.color_pair(2))
        stdscr.erase()
        stdscr.addstr(0, 0, "No PWM-controllable fans found in /sys/class/hwmon/.")
        stdscr.addstr(2, 0, "Press any key to exit.")
        stdscr.refresh()
        stdscr.nodelay(False)
        stdscr.getch()
        return

    while True:
        # 1. Draw the Blue Background
        stdscr.bkgd(' ', curses.color_pair(2))
        stdscr.erase()
        
        h, w = stdscr.getmaxyx()
        
        # Calculate sizing for the main dialog box
        box_h = min(20, h - 2)
        box_w = min(80, w - 4)
        start_y = (h - box_h) // 2
        start_x = (w - box_w) // 2

        # 2. Draw the Black Drop Shadow
        stdscr.attron(curses.color_pair(4))
        for i in range(box_h):
            # Offset the shadow by +1 y and +2 x
            stdscr.addstr(start_y + i + 1, start_x + 2, " " * box_w)
        stdscr.attroff(curses.color_pair(4))
        
        # We use noutrefresh to stage the background without flickering
        stdscr.noutrefresh()

        # 3. Draw the Main Grey Dialog Window
        dialog = curses.newwin(box_h, box_w, start_y, start_x)
        dialog.bkgd(' ', curses.color_pair(1))
        dialog.box()
        
        # Header
        title = " fan_tui v1.0 "
        mode_text = " [ ROOT / WRITE MODE ] " if root_mode else " [ READ ONLY MODE - Run with sudo to edit ] "
        dialog.addstr(0, (box_w - len(title)) // 2, title, curses.A_BOLD)
        dialog.addstr(box_h - 1, (box_w - len(mode_text)) // 2, mode_text, curses.A_BOLD)

        # Table Header
        header = f"{'Device':<15} | {'PWM ID':<8} | {'Mode':<14} | {'Speed (%)':<9} | {'Raw'}"
        header_padded = header.ljust(box_w - 4)
        # Using a simple line instead of A_REVERSE looks better in this theme
        dialog.addstr(2, 2, header_padded, curses.color_pair(1) | curses.A_UNDERLINE)

        # Draw fan list
        for idx, fan in enumerate(fans):
            if idx >= box_h - 7: 
                break
                
            raw_pwm = read_sysfs(fan['pwm_path'])
            mode = read_sysfs(fan['enable_path'])
            
            try:
                pct = round((int(raw_pwm) / 255) * 100)
                pct_str = f"{pct}%"
            except ValueError:
                pct_str = "N/A"
                
            mode_str = get_mode_name(mode)

            row = f"{fan['name'][:14]:<15} | {fan['pwm_id']:<8} | {mode_str:<14} | {pct_str:<9} | {raw_pwm}"
            
            # Pad the row to the full width of the inner box
            row_padded = row.ljust(box_w - 4)
            
            if idx == current_row:
                dialog.addstr(4 + idx, 2, row_padded, curses.color_pair(3))
            else:
                dialog.addstr(4 + idx, 2, row_padded)

        # Footer / Instructions
        dialog.addstr(box_h - 4, 0, "├" + "─" * (box_w - 2) + "┤")
        dialog.addstr(box_h - 3, 2, "CONTROLS: [\u2191/\u2193] Select Fan | [Q]uit")
        if root_mode:
            dialog.addstr(box_h - 2, 2, "[M] Open Mode Menu | [\u2190/\u2192] Adjust Speed (Manual Only)")

        dialog.noutrefresh()
        curses.doupdate() # Renders both stdscr and dialog to the screen cleanly

        key = stdscr.getch()
        
        if key == curses.KEY_UP and current_row > 0:
            current_row -= 1
        elif key == curses.KEY_DOWN and current_row < len(fans) - 1:
            current_row += 1
        elif key in [ord('q'), ord('Q')]:
            break
            
        # Write actions (Root only)
        if root_mode:
            selected_fan = fans[current_row]
            
            # Open Dropdown Mode Menu
            if key in [ord('m'), ord('M')] and selected_fan['enable_path']:
                stdscr.timeout(-1) 
                new_mode = show_mode_dropdown(stdscr, h, w)
                if new_mode is not None:
                    write_sysfs(selected_fan['enable_path'], new_mode)
                    time.sleep(0.2)
                stdscr.timeout(1000)  
            
            # Adjust Speed with 5% snapping
            if key in [curses.KEY_LEFT, curses.KEY_RIGHT]:
                curr_pwm = read_sysfs(selected_fan['pwm_path'])
                try:
                    curr_val = int(curr_pwm)
                    curr_pct = round((curr_val / 255) * 100)
                    
                    if key == curses.KEY_LEFT:
                        if curr_pct % 5 == 0: target_pct = curr_pct - 5
                        else: target_pct = (curr_pct // 5) * 5 
                    else: # KEY_RIGHT
                        if curr_pct % 5 == 0: target_pct = curr_pct + 5
                        else: target_pct = ((curr_pct // 5) + 1) * 5
                    
                    target_pct = max(0, min(100, target_pct))
                    new_val = round((target_pct / 100) * 255)
                    write_sysfs(selected_fan['pwm_path'], new_val)
                    time.sleep(0.1)
                except ValueError:
                    pass

if __name__ == "__main__":
    try:
        curses.wrapper(draw_menu)
    except KeyboardInterrupt:
        pass

