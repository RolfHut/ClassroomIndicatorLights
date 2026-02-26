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

def load_config():
    config = configparser.ConfigParser()
    if not config.read(CONFIG_PATH):
        print(f"Warning: Missing config file {CONFIG_PATH}, server communication will be disabled.")
        return None, None

    if not config.has_section("classroom"):
        raise SystemExit("Missing [classroom] section in config.ini")

    submit_to_server = config.getboolean("classroom", "submit_to_server", fallback=False)
    if not submit_to_server:
        print("submit_to_server is set to false, skipping server configuration")
        return None, None
    server_url = config.get("classroom", "server_url", fallback="").strip()
    event_password = config.get("classroom", "event_password", fallback="").strip()

    if not server_url:
        raise SystemExit("Missing required config key: classroom.server_url")
    if server_url and not event_password:
        raise SystemExit("Missing required config key: classroom.event_password")

    return server_url, event_password


SERVER_URL, EVENT_PASSWORD = load_config()

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
                table_index = int(table_str) - start_table  # Adjust for dynamic table range
                color_id = int(color_str)

                if 0 <= table_index < len(canvases):
                    root.after(0, update_table_color_from_serial, table_index, color_id)  # Use after() for safe updates
                else:
                    print(f"Invalid TableNr: {table_str}")

            except ValueError:
                print("Non-integer TableNr or ColorID")

        except Exception as e:
            print(f"Error reading serial data: {e}")

def update_table_color_from_serial(index, color_id):
    colors = {0: 'green', 1: 'orange', 2: 'red'}
    new_color = colors.get(color_id, None)

    if new_color:
        print(f"Updating table {index + start_table} to color {new_color}")  # Debug statement
        current_color = table_colors[index]

        if new_color == 'red' and current_color != 'red':
            red_start_time[index] = time.time()
        elif new_color != 'red':
            red_start_time[index] = None

        canvases[index].itemconfig('table', fill=new_color)
        table_colors[index] = new_color
        send_to_server(index + start_table, new_color)
    else:
        print(f"Invalid ColorID: {color_id}")

def cycle_table_color(index):
    global ser, start_table
    current_color = table_colors[index]
    next_color = {'green': 'orange', 'orange': 'red', 'red': 'green'}.get(current_color, 'green')
    print(f"Table {index + start_table} clicked! Changing color from {current_color} to {next_color}")
    if next_color == 'red' and current_color != 'red':
        red_start_time[index] = time.time()
    elif next_color != 'red':
        red_start_time[index] = None

    canvases[index].itemconfig('table', fill=next_color)
    table_colors[index] = next_color
    send_to_server(index + start_table, next_color)

    # Send "hooray" over serial if connected
    if ser and ser.is_open:
        try:
            colorCode = {'green': '0', 'orange': '1', 'red': '2'}.get(next_color)
            msg = "T," + str(index + start_table) + "," + str(colorCode) + "\n"
            ser.write(msg.encode())  # Send "hooray" followed by a newline
            print("Sent " + msg + " over serial")
        except Exception as e:
            print(f"Error sending data: {e}")

def reset_all_green():
    global ser, start_table, end_table, canvases, table_colors
    if ser and ser.is_open:
        for index in range(start_table, end_table):

            canvases[index - start_table].itemconfig('table', fill='green')
            table_colors[index - start_table] = 'green'
            send_to_server(index, 'green')

        # Send "hooray" over serial if connected
        msg = "T,-1,0\n"
        try:
            ser.write(msg.encode())  # Send "hooray" followed by a newline
            print("Sent " + msg + " over serial")
        except Exception as e:
            print(f"Error sending data: {e}")
        time.sleep(0.01) #sleep 10 milliseconds to not flood the airwaves



def update_longest_red_list():
    current_time = time.time()
    durations = [(i, int(current_time - red_start_time[i]) if red_start_time[i] else 0) for i in range(len(canvases))]
    durations.sort(key=lambda x: x[1], reverse=True)

    #print("Updating red list with durations:", durations)  # Debug statement

    red_list.delete(0, tk.END)
    for index, duration in durations:
        if duration > 0:
            red_list.insert(tk.END, f"Table {index + start_table}: {duration}s")

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
        print(f"Connected to {selected_port}")
    except Exception as e:
        print(f"Error connecting to port {selected_port}: {e}")
        ser = None



def update_table_range():
    global start_table, end_table, canvases, red_start_time, table_colors
    try:
        start_table = int(start_table_entry.get())
        end_table = int(end_table_entry.get()) + 1
        if start_table >= end_table:
            print("Start table must be less than end table.")
            return

        for canvas in canvases:
            canvas.destroy()
            
        # Reset grid configuration for consistent alignment
        #for r in range((end_table - start_table + 1) // 2 + 2):
        #    root.grid_rowconfigure(r, weight=1, uniform="row")
        for c in range(2):  # Two columns
            root.grid_columnconfigure(c, weight=1, uniform="column")

        # Define consistent padding
        padx = 1
        pady = 1

        canvases = []
        red_start_time = [None] * (end_table - start_table)
        table_colors = ['green'] * (end_table - start_table)

        # Adjust grid for numbering from bottom left, up the left column, then down the right column
        total_tables = end_table - start_table
        num_rows = (total_tables) // 2

        for i in range(start_table, end_table):
            canvas = tk.Canvas(root, width=100, height=20, bg='grey')
            canvas.create_rectangle(10, 5, 90, 20, fill='green', tags='table')
            canvas.create_text(50, 10, text=f"{i}", fill="white", font=("Helvetica", 10), tags="table_text")
            canvas.tag_bind('table', '<Button-1>', lambda e, i=i: cycle_table_color(i - start_table))  # Adjust index
            canvases.append(canvas)

            # Calculate position for bottom-left numbering
            col = 0 if ((i - start_table + 1) <= (num_rows))  else 1
            row = (num_rows - (i - start_table + 1)+1) if col == 0 else ((i - start_table + 1) - num_rows)  

            canvas.grid(row=row, column=col, padx=padx, pady=pady, sticky='')

    except ValueError:
        print("Invalid start or end table number.")

# Initialize table range
start_table = 1
end_table = 16
red_start_time = [None] * (end_table - start_table)
table_colors = ['green'] * (end_table - start_table)
ser = None  # Serial connection object

# Set up the tkinter GUI
root = tk.Tk()
root.title("Classroom Map")
root.geometry('1200x1000')  # Adjusted size to fit all widgets

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
start_table_entry.insert(0, "1")
start_table_entry.pack(pady=5)
tk.Label(table_range_frame, text="End Table:").pack()
end_table_entry = tk.Entry(table_range_frame, width=5)
end_table_entry.insert(0, "16")
end_table_entry.pack(pady=5)
update_table_button = tk.Button(table_range_frame, text="Update Tables", command=update_table_range)
update_table_button.pack(pady=5)

# Create canvas objects for tables
canvases = []
update_table_range()

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
