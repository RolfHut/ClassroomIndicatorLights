from flask import Flask, request, Response, render_template
import json
import queue
import configparser
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.ini"
DEFAULT_START_TABLE = 1
DEFAULT_END_TABLE = 16

def load_config():
    config = configparser.ConfigParser()
    if not config.read(CONFIG_PATH):
        raise SystemExit(f"Missing config file: {CONFIG_PATH}")

    if not config.has_section("classroom"):
        raise SystemExit("Missing [classroom] section in config.ini")

    server_url = config.get("classroom", "server_url", fallback="").strip()
    event_password = config.get("classroom", "event_password", fallback="").strip()
    start_table = config.getint("classroom", "start_table", fallback=DEFAULT_START_TABLE)
    end_table = config.getint("classroom", "end_table", fallback=DEFAULT_END_TABLE)

    if not server_url:
        raise SystemExit("Missing required config key: classroom.server_url")
    if not event_password:
        raise SystemExit("Missing required config key: classroom.event_password")
    return server_url, event_password, start_table, end_table

app = Flask(__name__)

clients = []
table_state = {}

ALLOWED_COLORS = {"red", "orange", "green"}
SERVER_URL, EVENT_PASSWORD, START_TABLE, END_TABLE = load_config()

@app.route("/")
def index():
    return render_template(
        "index.html",
        start_table=START_TABLE,
        end_table=END_TABLE + 1
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