import tkinter as tk
from tkinter import ttk
import requests
import serial
import threading
import time
import serial.tools.list_ports
import configparser
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.ini"
DEFAULT_START_TABLE = 1
DEFAULT_END_TABLE = 16


def build_default_table_columns(start_table, end_table):
    total_tables = end_table - start_table + 1
    if total_tables <= 0:
        raise ValueError("end_table must be >= start_table")
    
    if total_tables == 1:
        return [[start_table]]

    first_count = (total_tables + 1) // 2
    first_col = list(range(start_table, start_table + first_count))[::-1]
    second_col = list(range(start_table + first_count, end_table + 1))

    columns = [first_col, second_col]
    return columns


def parse_table_layout(layout, start_table, end_table):
    if not layout:
        return None

    columns = []
    for segment in layout.split(","):
        segment = segment.strip()
        if not segment:
            continue

        if "-" not in segment:
            raise ValueError(f"Invalid layout segment: {segment}")

        start_str, end_str = segment.split("-", 1)
        try:
            start_num = int(start_str)
            end_num = int(end_str)
        except ValueError:
            raise ValueError(f"Invalid numbers in layout segment: {segment}")

        if not (start_table <= start_num <= end_table) or not (start_table <= end_num <= end_table):
            raise ValueError(f"Table numbers in layout segment must be between {start_table} and {end_table}: {segment}")

        step = 1 if end_num >= start_num else -1
        columns.append(list(range(start_num, end_num + step, step)))

    return columns


def load_config():
    config = configparser.ConfigParser()
    if not config.read(CONFIG_PATH):
        print(f"Warning: Missing config file {CONFIG_PATH}, server communication will be disabled.")
        return None, None, DEFAULT_START_TABLE, DEFAULT_END_TABLE, build_default_table_columns(DEFAULT_START_TABLE, DEFAULT_END_TABLE)

    if not config.has_section("classroom"):
        raise SystemExit("Missing [classroom] section in config.ini")

    start_table = config.getint("classroom", "start_table", fallback=DEFAULT_START_TABLE)
    end_table = config.getint("classroom", "end_table", fallback=DEFAULT_END_TABLE)

    table_layout = config.get("classroom", "table_layout", fallback="").strip()
    if table_layout:
        try:
            table_columns = parse_table_layout(table_layout, start_table, end_table)
        except ValueError as e:
            raise SystemExit(f"Invalid classroom.table_layout: {e}")
    else:
        table_columns = build_default_table_columns(start_table, end_table)

    submit_to_server = config.getboolean("classroom", "submit_to_server", fallback=False)
    if not submit_to_server:
        print("submit_to_server is set to false, skipping server configuration")
        return None, None, start_table, end_table, table_columns
    server_url = config.get("classroom", "server_url", fallback="").strip()
    event_password = config.get("classroom", "event_password", fallback="").strip()

    if not server_url:
        raise SystemExit("Missing required config key: classroom.server_url")
    if server_url and not event_password:
        raise SystemExit("Missing required config key: classroom.event_password")

    return server_url, event_password, start_table, end_table, table_columns


SERVER_URL, EVENT_PASSWORD, CONFIG_START_TABLE, CONFIG_END_TABLE, CONFIG_TABLE_COLUMNS = load_config()

def send_to_server(table, color):
    if not SERVER_URL:
        return
    try:
        headers = {
            "X-Event-Password": EVENT_PASSWORD
        }
        requests.post(SERVER_URL, json={
            "table": table,
            "color": color
        }, headers=headers, timeout=0.2)
    except:
        pass

def process_serial_data():
    global ser
    while True:
        if ser is None:
            time.sleep(0.1)  # Add a small delay to prevent CPU overload
            continue
        try:
            line = ser.readline().decode('utf-8').strip()  # Wait for a full linefeed (\r\n)
            if not line:
                continue

            print(f"Received: {line}")  # Debug: print the raw input
            parts = line.split(',')

            if len(parts) != 3:
                print("Invalid message format")
                continue

            role, table_str, color_str = parts
            #print(type(room))
            #room = room[1:] if room.startswith('R') else room

            # Check if the room is selected
            #if not room_filters[room].get():
            #    print(f"Room {room} is not selected, ignoring message.")
            #    continue

            if ((start_table > int(table_str)) or (int(table_str) > end_table)):
                print("Table number outside of selected range, ignoring")
                continue

            if role == 'RT':
                print("repeat of own message, ignoring")
                continue

            try:
                table_number = int(table_str)
                color_id = int(color_str)

                if table_number not in canvas_by_table:
                    print(f"Table number {table_number} is not shown in current layout, ignoring")
                    continue

                root.after(0, update_table_color_from_serial, table_number, color_id)  # Use after() for safe updates

            except ValueError:
                print("Non-integer TableNr or ColorID")

        except Exception as e:
            print(f"Error reading serial data: {e}")

def update_table_color_from_serial(table_number, color_id):
    colors = {0: 'green', 1: 'orange', 2: 'red'}
    new_color = colors.get(color_id, None)

    if new_color:
        print(f"Updating table {table_number} to color {new_color}")  # Debug statement
        current_color = color_by_table[table_number]

        if new_color == current_color:
            return

        if new_color == 'red' and current_color != 'red':
            red_start_time_by_table[table_number] = time.time()
        elif new_color != 'red':
            red_start_time_by_table[table_number] = None

        canvas_by_table[table_number].itemconfig('table', fill=new_color)
        color_by_table[table_number] = new_color
        send_to_server(table_number, new_color)
    else:
        print(f"Invalid ColorID: {color_id}")

def cycle_table_color(table_number):
    global ser
    current_color = color_by_table[table_number]
    next_color = {'green': 'orange', 'orange': 'red', 'red': 'green'}.get(current_color, 'green')
    print(f"Table {table_number} clicked! Changing color from {current_color} to {next_color}")
    if next_color == 'red' and current_color != 'red':
        red_start_time_by_table[table_number] = time.time()
    elif next_color != 'red':
        red_start_time_by_table[table_number] = None

    canvas_by_table[table_number].itemconfig('table', fill=next_color)
    color_by_table[table_number] = next_color
    send_to_server(table_number, next_color)

    # Send over serial if connected
    if ser and ser.is_open:
        try:
            colorCode = {'green': '0', 'orange': '1', 'red': '2'}.get(next_color)
            msg = "T," + str(table_number) + "," + str(colorCode) + "\n"
            ser.write(msg.encode())
            print("Sent " + msg + " over serial")
        except Exception as e:
            print(f"Error sending data: {e}")

def reset_all_green():
    global ser
    for table_number, canvas in canvas_by_table.items():
        canvas.itemconfig('table', fill='green')
        color_by_table[table_number] = 'green'
        red_start_time_by_table[table_number] = None
        send_to_server(table_number, 'green')

    if ser and ser.is_open:
        msg = "T,-1,0\n"
        try:
            ser.write(msg.encode())
            print("Sent " + msg + " over serial")
        except Exception as e:
            print(f"Error sending data: {e}")
        time.sleep(0.01) #sleep 10 milliseconds to not flood the airwaves



def update_longest_red_list():
    current_time = time.time()
    durations = [(table_number, int(current_time - start_time) if start_time else 0) 
                 for table_number, start_time in red_start_time_by_table.items()]
    durations.sort(key=lambda x: x[1], reverse=True)

    red_list.delete(0, tk.END)
    for table_number, duration in durations:
        if duration > 0:
            red_list.insert(tk.END, f"Table {table_number}: {duration}s")

    # Schedule the function to run again
    root.after(1000, update_longest_red_list)

def refresh_ports():
    ports = serial.tools.list_ports.comports()
    port_list = [port.device for port in ports]
    port_selector['values'] = port_list
    print(f"Available ports: {port_list}")  # Debug statement

def connect_to_port():
    global ser
    selected_port = port_selector.get()
    if ser is not None:
        ser.close()
    try:
        ser = serial.Serial(selected_port, 115200, timeout=1)  # Updated baudrate
        # wake up the microbit(?) otherwise no data is received until a button is pressed
        ser.write(b"\n")
        print(f"Connected to {selected_port}")
    except Exception as e:
        print(f"Error connecting to port {selected_port}: {e}")
        ser = None


def render_table_grid(columns):
    global canvas_by_table, red_start_time_by_table, color_by_table

    # Calculate current grid dimensions from existing canvases
    if canvas_by_table:
        current_cols = max(canvas.grid_info()['column'] for canvas in canvas_by_table.values()) + 1
        current_rows = max(canvas.grid_info()['row'] for canvas in canvas_by_table.values()) + 1
    else:
        current_cols = 0
        current_rows = 0

    # Destroy old canvases
    for canvas in canvas_by_table.values():
        canvas.destroy()

    # Clear previous grid configuration
    for c in range(current_cols):
        tables_frame.grid_columnconfigure(c, weight=0, uniform='')
    for r in range(current_rows):
        tables_frame.grid_rowconfigure(r, weight=0, uniform='')

    canvas_by_table.clear()
    color_by_table.clear()
    red_start_time_by_table.clear()

    max_rows = 0
    for col, col_tables in enumerate(columns):
        max_rows = max(max_rows, len(col_tables))
        for row, table_number in enumerate(col_tables):
            canvas = tk.Canvas(tables_frame, bg='grey', highlightthickness=0, bd=0)
            canvas.create_rectangle(3, 3, 0, 0, fill='green', tags='table')
            canvas.create_text(0, 0, text=f"{table_number}", fill="white", font=("Helvetica", 12), tags="table_text")

            canvas.tag_bind('table', '<Button-1>', lambda e, t=table_number: cycle_table_color(t))
            canvas.tag_bind('table_text', '<Button-1>', lambda e, t=table_number: cycle_table_color(t))

            def redraw_canvas(event, c=canvas):
                w, h = event.width, event.height
                c.coords('table', 3, 3, w - 3, h - 3)
                c.coords('table_text', w // 2, h // 2)

            canvas.bind('<Configure>', redraw_canvas)
            canvas.grid(row=row, column=col, padx=40, pady=3, sticky='nsew')
            canvas.config(width=80, height=30)
            canvas_by_table[table_number] = canvas
            color_by_table[table_number] = 'green'
            red_start_time_by_table[table_number] = None

    for c in range(len(columns)):
        tables_frame.grid_columnconfigure(c, weight=1, uniform='table_col')
    for r in range(max_rows):
        tables_frame.grid_rowconfigure(r, weight=1, uniform='table_row')


def update_table_range():
    global start_table, end_table
    try:
        start_table = int(start_table_entry.get())
        end_table = int(end_table_entry.get())
        if start_table > end_table:
            print("Start table must be less than or equal to end table.")
            return

        # reset to default 2-column layout
        columns = build_default_table_columns(start_table, end_table)
        render_table_grid(columns)

    except ValueError:
        print("Invalid start or end table number.")

# Initialize table range
start_table = CONFIG_START_TABLE
end_table = CONFIG_END_TABLE
canvas_by_table = {}
color_by_table = {}
red_start_time_by_table = {}
ser = None  # Serial connection object

# Set up the tkinter GUI
root = tk.Tk()
root.title("Classroom Map")
root.geometry('1200x1000')  # Adjusted size to fit all widgets

# Make the window expand to fill available space
for i in range(2, 12):  # rows 2-11 for table grid
    root.rowconfigure(i, weight=1)
root.columnconfigure(0, weight=1)

# Dropdown for serial port selection
port_selector = ttk.Combobox(root, state='readonly', width=30)
port_selector.grid(row=0, column=0, padx=10, pady=10, sticky='w')
refresh_ports_button = tk.Button(root, text="Refresh Ports", command=refresh_ports)
refresh_ports_button.grid(row=0, column=1, padx=10, pady=10, sticky='w')
connect_button = tk.Button(root, text="Connect", command=connect_to_port)
connect_button.grid(row=0, column=2, padx=10, pady=10, sticky='w')

reset_button = tk.Button(root, text="Reset", command=reset_all_green)
reset_button.grid(row=1, column=3, padx=10, pady=10, sticky='w')


# Table range inputs
table_range_frame = tk.Frame(root)
table_range_frame.grid(row=0, column=3, padx=10, pady=10, sticky='w')
tk.Label(table_range_frame, text="Start Table:").pack()
start_table_entry = tk.Entry(table_range_frame, width=5)
start_table_entry.insert(0, str(CONFIG_START_TABLE))
start_table_entry.pack(pady=5)
tk.Label(table_range_frame, text="End Table:").pack()
end_table_entry = tk.Entry(table_range_frame, width=5)
end_table_entry.insert(0, str(CONFIG_END_TABLE))
end_table_entry.pack(pady=5)
update_table_button = tk.Button(table_range_frame, text="Update Tables", command=update_table_range)
update_table_button.pack(pady=5)

# Dedicated frame to keep table spacing consistent
tables_frame = tk.Frame(root)
tables_frame.grid(row=2, column=0, columnspan=3, rowspan=10, padx=10, pady=5, sticky='nsew')

# Create canvas objects for tables using config layout
render_table_grid(CONFIG_TABLE_COLUMNS)

# Listbox to display tables longest on red
red_list = tk.Listbox(root, height=16, width=25)
red_list.grid(row=2, column=3, rowspan=10, padx=10, pady=5, sticky='ns')

# Start the serial processing in a separate thread
thread = threading.Thread(target=process_serial_data)
thread.daemon = True
thread.start()

refresh_ports()  # Populate the dropdown with available ports on startup

# Start updating the red list
update_longest_red_list()

root.mainloop()
