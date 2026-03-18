# Classroom Status Webserver

Flask app that receives table events and streams live updates to browser clients.

## Run

From `software/website` run `python3 server.py`

Server listens on port `5005`.

## Server config

Copy software/config.ini.example to software/config.ini. Edit as needed (table range and event communication password).

## Client (teacherApplication.py) config

To make `teacherApplication.py` send status updates to this webserver:

- create the config file on the client, just as described above
- set `submit_to_server = true`
- set `server_url` to the address of the server, ending in `/event`
- set the same `event_password` in both sender and server config

If `submit_to_server = false`, teacher app runs locally and does not post to `/event`.
