# ClassroomIndicatorLights
indicator lights for in your classroom. Students signal if they have a question by turning on a light. Microbits communicate the status to an application running on the teachers screen, showing which student has the longest open question. Particular usefull for large (undergraduate) classes with 50+ students. Includes software and hardware designs.

## Usage
- Flash the microbits with the software in software/teacherReceiverMicrobit and software/studentLightMicrobit.
- Connect the teacher microbit to your computer and run the teacher application (software/teacherApplication.py). This will show a UI with the status of all tables. Students press the button on their microbit to signal a question. You can also click on tables to change their status.

### Config
There are several configuration options:
- Range of table numbers
- Table layout
- Optional webserver to show status UI in the browser

By default, no webserver is configured and a table range of 1-16 is shown. This can be changed as follows:

- Copy `software/config.example.ini` to `software/config.ini`
- Set `start_table` and `end_table` to your desired range
- The default layout is two columns of tables, with the lowest number in the bottom left, ascending clockwise. You can set `table_layout` to a different set of columns, for example `1-5, 6-10, 11-16` for three columns, each ascending from top to bottom, or `8-1, 9-16` for two columns, each descending from top to bottom.

#### Webserver
You can run `software/website/server.py` to start a webserver (can be on a separate computer) that shows the same status UI in the browser. To configure it:
- Set `submit_to_server = true` in config.ini on the teacher computer side
- Set `server_url` to the address of the server, ending in `/event`
- Set the same `event_password` in both teacher computer and server config

For more details, see `software/website/README.md`.
