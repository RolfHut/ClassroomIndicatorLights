from flask import Flask, request, Response, render_template
import json
import queue
import configparser
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.ini"
DEFAULT_START_TABLE = 1
DEFAULT_END_TABLE = 16


def parse_table_layout(layout: str, start: int, end: int):
    """Parse a layout string like "1-3, 10-4, 11-17" into columns of table numbers.

    Each segment defines a column. A segment like "10-4" produces a descending range.
    """

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

        if not (start <= start_num <= end) or not (start <= end_num <= end):
            raise ValueError(
                f"Table numbers in layout segment must be between {start} and {end}: {segment}"
            )

        step = 1 if end_num >= start_num else -1
        columns.append(list(range(start_num, end_num + step, step)))

    return columns


def load_config():
    config = configparser.ConfigParser()
    if not config.read(CONFIG_PATH):
        raise SystemExit(f"Missing config file: {CONFIG_PATH}")

    if not config.has_section("classroom"):
        raise SystemExit("Missing [classroom] section in config.ini")

    event_password = config.get("classroom", "event_password", fallback="").strip()
    start_table = config.getint("classroom", "start_table", fallback=DEFAULT_START_TABLE)
    end_table = config.getint("classroom", "end_table", fallback=DEFAULT_END_TABLE)

    if not event_password:
        raise SystemExit("Missing required config key: classroom.event_password")

    table_layout = config.get("classroom", "table_layout", fallback="").strip()
    table_columns = None
    if table_layout:
        try:
            table_columns = parse_table_layout(table_layout, start_table, end_table)
        except ValueError as e:
            raise SystemExit(f"Invalid classroom.table_layout: {e}")

    # default layout if not set
    if table_columns is None:
        total_tables = end_table - start_table + 1
        if total_tables <= 0:
            raise SystemExit("Invalid classroom.start_table/end_table: end must be >= start")

        first_count = (total_tables + 1) // 2
        first_col = list(range(start_table, start_table + first_count))[::-1]
        second_col = list(range(start_table + first_count, end_table + 1))
        table_columns = [first_col]
        if second_col:
            table_columns.append(second_col)

    return event_password, start_table, end_table, table_columns

app = Flask(__name__)

clients = []
table_state = {}

ALLOWED_COLORS = {"red", "orange", "green"}
EVENT_PASSWORD, START_TABLE, END_TABLE, TABLE_COLUMNS = load_config()

@app.route("/")
def index():
    return render_template(
        "index.html",
        start_table=START_TABLE,
        end_table=END_TABLE + 1,
        table_columns=TABLE_COLUMNS,
    )

# Receive events from teacher application
@app.route("/event", methods=["POST"])
def receive_event():
    received_password = request.headers.get("X-Event-Password", "")
    if received_password != EVENT_PASSWORD:
        return {"status": "error", "message": "unauthorized"}, 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"status": "error", "message": "invalid json"}, 400

    table = data.get("table")
    color = data.get("color")

    if not isinstance(table, int) or table < START_TABLE or table > END_TABLE:
        return {"status": "error", "message": "invalid table"}, 400

    if color not in ALLOWED_COLORS:
        return {"status": "error", "message": "invalid color"}, 400

    table_state[table] = color

    event_payload = {
        "table": table,
        "color": color
    }

    message = json.dumps(event_payload)

    for client in clients:
        client.put(message)

    return {"status": "ok"}

# Send events to opened webpages
@app.route("/events")
def stream():
    def event_stream(q):
        for table, color in table_state.items():
            yield f"data: {json.dumps({'table': table, 'color': color})}\n\n"

        try:
            while True:
                data = q.get()
                yield f"data: {data}\n\n"
        except GeneratorExit:
            clients.remove(q)

    q = queue.Queue()
    clients.append(q)
    return Response(event_stream(q), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(port=5005, threaded=True)