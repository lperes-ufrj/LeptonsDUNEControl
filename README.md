# Leptons DUNE Deposition Control System

Web application for the Leptons Lab: deposition samples (mass control, visual inspection, cryogenic immersion,
optical efficiency), Final QA sign-off, HTML/PDF reports with QR codes, OPTO batch arrival and Leptons cleaning
lots, statistics, users and audit log.

It runs on a server: Flask (Python 3.13) behind gunicorn and nginx, with the data in MariaDB. Every dependency is
an official Debian 13 package. Server installation: [deploy/LEIAME.md](deploy/LEIAME.md) (in Portuguese, for IT).

## Layout

| Path | What it is |
| --- | --- |
| `webapp/app.py` | Flask app: all pages and routes |
| `webapp/db.py` | MariaDB connection and every table definition |
| `webapp/config.py` | Reads the configuration file (database, session key, data folder) |
| `webapp/auth.py` | Users, passwords, audit log |
| `webapp/dados.py`, `tarefas.py` | Reading and saving samples, status rules |
| `webapp/chegada.py`, `lotes.py`, `retirados.py` | Batches, internal lots, cleaning lots, removed filters |
| `webapp/relatorio.py`, `pdf.py` | HTML/PDF reports and QR codes |
| `webapp/estatisticas.py`, `projecoes.py`, `planilha.py` | Statistics, projections, DUNE_Control.xlsx sync |
| `webapp/textos_pt.py`, `i18n.py` | Portuguese translation of the screens |
| `deploy/` | Server files: config template, systemd unit, nginx site, SQLite → MariaDB migration |

## Development setup (Linux)

1. Python environment, with the same library versions as Debian 13:

   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

2. A local MariaDB (`sudo apt install mariadb-server`), with a database and user:

   ```sql
   CREATE DATABASE leptons CHARACTER SET utf8mb4;
   CREATE USER 'leptons'@'localhost' IDENTIFIED BY 'dev-password';
   GRANT ALL PRIVILEGES ON leptons.* TO 'leptons'@'localhost';
   ```

3. Configuration: copy `deploy/leptons.conf.example` to `leptons.conf` in the project folder (it is ignored by
   git) and set `host = localhost`, the password, a `secret_key`, `data_dir = dados` and `secure_cookies = false`
   (the development server has no HTTPS).

4. Data: either copy the lab's SQLite databases into MariaDB once

   ```bash
   LEPTONS_CONFIG=leptons.conf .venv/bin/python deploy/migrar_sqlite.py /folder/with/the/db/files
   ```

   or start empty and create an Admin account:

   ```bash
   LEPTONS_CONFIG=leptons.conf .venv/bin/flask --app "webapp.app:criar_app()" create-admin
   ```

5. Run: VS Code › Run and Debug › **Web app (Flask dev server)**, or

   ```bash
   LEPTONS_CONFIG=leptons.conf .venv/bin/flask --app "webapp.app:criar_app()" run --port 8780 --debug
   ```

   and open <http://127.0.0.1:8780>.

## Notes

- New tables are created when the app starts (`db.criar_tabelas`). A new column in an existing table needs an
  `ALTER TABLE` run on the server.
- The SQL in the code uses `?` placeholders; `db.py` turns them into PyMySQL's `%s`.
- Keep gunicorn at one worker process (`deploy/leptons.service`): a JSON import and a spreadsheet sync are kept in
  memory between two pages.
