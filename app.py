import sqlite3
import io
import csv
import requests
from flask import Flask, request, jsonify, render_template, Response
from database import get_connection, init_db
from datetime import datetime

app = Flask(__name__)

# Every column that may appear in a PUT body
UPDATABLE_FIELDS = {
    "machine_name",
    "platform_name",
    "ip_address",
    "bmc_name",
    "os",
    "description",
    "status",
    "reserved_by",
    "po_sms",
    "program",
    "socket",
    "system_config",
    "make",
    "model",
    "category",
    "asset_owner",
    "serial",
    "maas_switch",
    "pdu_ip",
    "pdu_port",
    "site",
    "lab",
    "row_location",
    "rack",
    "ru",
    "cpu",
    "backplane",
    "jira",
    "box_id",
    "current_project",
    "team",
    "motd",
}

# Columns shown in the terminal table and their headers
COLUMNS = [
    ("machine_name",  "MACHINE"),
    ("platform_name", "PLATFORM"),
    ("ip_address",    "IP ADDRESS"),
    ("bmc_name",      "BMC"),
    ("os",            "OS"),
    ("status",        "STATUS"),
    ("reserved_by",   "RESERVED BY"),
    ("team",          "TEAM"),
    ("po_sms",        "PO/SMS"),
    ("program",       "PROGRAM"),
    ("socket",        "SOCKET"),
    ("system_config", "SYS CONFIG"),
    ("make",          "MAKE"),
    ("model",         "MODEL"),
    ("category",      "CATEGORY"),
    ("asset_owner",   "ASSET OWNER"),
    ("serial",        "SERIAL"),
    ("maas_switch",   "MAAS SWITCH"),
    ("pdu_ip",        "PDU IP"),
    ("pdu_port",      "PDU PORT"),
    ("site",          "SITE"),
    ("lab",           "LAB"),
    ("row_location",  "ROW"),
    ("rack",          "RACK"),
    ("ru",            "RU"),
    ("cpu",           "CPU"),
    ("backplane",     "BACKPLANE"),
    ("jira",          "JIRA"),
    ("description",   "DESCRIPTION"),
    ("box_id",          "BOX_ID"),
    ("current_project", "CURRENT_PROJECT"),
    ("motd",          "MOTD"),
]


# ── helpers ────────────────────────────────────────────────────────────────────

def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def row_to_dict(row):
    return dict(row) if row else None

def _wants_text(req):
    """
    Return True  → send plain-text table
    Return False → send JSON

    Rules (checked in order):
      1. Accept: application/json  → always JSON
      2. Accept: text/html         → always JSON  (browser gets JSON, UI is at /)
      3. curl / wget / httpie with no explicit Accept → text table
      4. anything else             → JSON
    """
    accept = req.headers.get("Accept", "")
    ua     = req.headers.get("User-Agent", "").lower()

    # explicit JSON request → always honour it
    if "application/json" in accept:
        return False

    # browser requesting the API endpoint directly → return JSON
    if "text/html" in accept:
        return False

    # terminal tools that send Accept: */*  (curl default)
    terminal_tools = ("curl/", "httpie/", "wget/", "python-requests/")
    if any(t in ua for t in terminal_tools):
        return True

    return False    # default: JSON

# ── input sanitizer (if not already in app.py) ─────────────────────────────────

def clean(value):
    """
    Strip whitespace from strings.
    Return None for empty/whitespace-only strings and actual None.
    """
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return value

# ── LIST  ─────────────────────────────────────────────────────────────────────
# GET /machines
# GET /machines?status=available
# GET /machines?status=reserved

@app.route("/machines", methods=["GET"])
def list_machines():
    status_filter = request.args.get("status")

    conn = get_connection()
    if status_filter:
        rows = conn.execute(
            "SELECT * FROM machines WHERE status = ? ORDER BY machine_name",
            (status_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM machines ORDER BY machine_name"
        ).fetchall()
    conn.close()

    machines = [row_to_dict(r) for r in rows]

    if _wants_text(request):
        return _render_table(machines), 200, {"Content-Type": "text/plain"}

    return jsonify(machines)

# ── RESERVE ─────────────────────────────────────────────────────────────────────
# POST /machines/reserve
@app.route('/machines/reserve', methods=['POST'])
def reserve_machine():
    data = request.get_json(silent=True) or {}

    user_email = (data.get('user_email') or '').strip()
    machine_name = (data.get('machine_name') or '').strip()
    ip_address = (data.get('ip_address') or '').strip()

    if not user_email:
        return jsonify({'error': 'user_email is required'}), 400
    if not machine_name:
        return jsonify({'error': 'machine_name is required'}), 400
    if not ip_address:
        return jsonify({'error': 'ip_address is required'}), 400

    try:
        remote_url = f'http://{ip_address}:5001/reserve'
        payload = {
            'user_email': user_email,
            'machine_name': machine_name
        }

        print(f'[reserve_machine] remote_url={remote_url}')
        print(f'[reserve_machine] payload={payload}')

        resp = requests.post(remote_url, json=payload, timeout=30)

        print(f'[reserve_machine] response_status={resp.status_code}')
        print(f'[reserve_machine] response_text={resp.text}')
        try:
            result = resp.json()
        except Exception:
            result = {'error': resp.text or 'Invalid response from remote reserve service'}

        if resp.ok:
            return jsonify({
                'message': result.get('message', 'Machine reserved successfully'),
                'machine_name': machine_name,
                'ip_address': ip_address,
                'user_email': user_email
            }), 200
        else:
            return jsonify({
                'error': result.get('error', 'Remote reservation failed'),
                'details': result.get('details', '')
            }), resp.status_code

    except requests.exceptions.Timeout:
        return jsonify({
            'error': f'Timeout while contacting reserve service on {ip_address}:5001'
        }), 504

    except requests.exceptions.ConnectionError:
        return jsonify({
            'error': f'Could not connect to reserve service on {ip_address}:5001'
        }), 502

    except Exception as e:
        return jsonify({
            'error': 'Unexpected server error during reservation',
            'details': str(e)
        }), 500

# ── INSERT ─────────────────────────────────────────────────────────────────────
# POST /machines
# Required body fields: machine_name, platform_name

@app.route("/machines", methods=["POST"])
def insert_machine():
    data = request.get_json(silent=True) or {}
    data = {k: clean(v) for k, v in data.items()}

    missing = [f for f in ("machine_name", "platform_name") if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO machines
                (machine_name, platform_name, ip_address, bmc_name, os, description,
                 po_sms, program, socket, system_config, make, model, category,
                 asset_owner, serial, maas_switch, pdu_ip, pdu_port,
                 site, lab, row_location, rack, ru, cpu, backplane, jira,
                 box_id, current_project, team, motd,
                 status, reserved_by)
            VALUES (?,?,?,?,?,?, ?,?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?,?,?,?,?,?,?,?, 'available', NULL)
        """, (
            data["machine_name"],
            data["platform_name"],
            data.get("ip_address"),
            data.get("bmc_name"),
            data.get("os"),
            data.get("description"),
            data.get("po_sms"),
            data.get("program"),
            data.get("socket"),
            data.get("system_config"),
            data.get("make"),
            data.get("model"),
            data.get("category"),
            data.get("asset_owner"),
            data.get("serial"),
            data.get("maas_switch"),
            data.get("pdu_ip"),
            data.get("pdu_port"),
            data.get("site"),
            data.get("lab"),
            data.get("row_location"),
            data.get("rack"),
            data.get("ru"),
            data.get("cpu"),
            data.get("backplane"),
            data.get("jira"),
            data.get("box_id"),
            data.get("current_project"),
            data.get("team"),
            data.get("motd"),
        ))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 409

    conn.close()
    return jsonify({"message": f"Machine '{data['machine_name']}' inserted."}), 201


# ── UPDATE ─────────────────────────────────────────────────────────────────────
# PUT /machines/<current_machine_name>
# Body may contain any subset of UPDATABLE_FIELDS
# machine_name in body → renames the machine

@app.route("/machines/<current_name>", methods=["PUT"])
def update_machine(current_name):
    data = request.get_json(silent=True) or {}

    # clean every incoming value
    data = {k: clean(v) for k, v in data.items()}

    # collect only recognised fields the caller actually sent
    updates = {k: v for k, v in data.items() if k in UPDATABLE_FIELDS}

    if not updates:
        return jsonify({
            "error":     "No updatable fields provided.",
            "updatable": sorted(UPDATABLE_FIELDS),
        }), 400

    # ── status rules ──────────────────────────────────────────────────────────
    new_status = updates.get("status")

    if new_status is not None:
        if new_status not in ("available", "reserved"):
            return jsonify(
                {"error": "status must be 'available' or 'reserved'"}
            ), 400

        if new_status == "reserved" and not updates.get("reserved_by"):
            return jsonify(
                {"error": "reserved_by is required when reserving a machine"}
            ), 400

        if new_status == "available":
            updates["reserved_by"] = None   # always clear on release

    # ── machine_name rename: check new name is not already taken ──────────────
    new_name = updates.get("machine_name")
    if new_name and new_name != current_name:
        conn = get_connection()
        clash = conn.execute(
            "SELECT id FROM machines WHERE machine_name = ?", (new_name,)
        ).fetchone()
        conn.close()
        if clash:
            return jsonify(
                {"error": f"Machine name '{new_name}' is already in use."}
            ), 409

    # ── verify the machine we are updating exists ─────────────────────────────
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM machines WHERE machine_name = ?", (current_name,)
    ).fetchone()

    if not row:
        conn.close()
        return jsonify({"error": f"Machine '{current_name}' not found."}), 404

    # ── build dynamic SET clause and execute ──────────────────────────────────
    updates["updated_at"] = now()

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values     = list(updates.values()) + [current_name]

    conn.execute(
        f"UPDATE machines SET {set_clause} WHERE machine_name = ?",
        values
    )
    conn.commit()
    conn.close()

    changed_fields = [k for k in updates if k != "updated_at"]
    response = {"message": f"Machine '{current_name}' updated.",
                "fields_updated": changed_fields}

    if new_name and new_name != current_name:
        response["renamed_to"] = new_name

    return jsonify(response)


# ── BROWSER UI ─────────────────────────────────────────────────────────────────
# GET /

@app.route("/", methods=["GET"])
def ui():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM machines ORDER BY machine_name"
    ).fetchall()
    conn.close()

    machines  = [row_to_dict(r) for r in rows]
    available = sum(1 for m in machines if m["status"] == "available")
    reserved  = sum(1 for m in machines if m["status"] == "reserved")

    return render_template("index.html",
                           machines=machines,
                           total=len(machines),
                           available=available,
                           reserved=reserved)


# ── DELETE  DELETE /machines/<machine_name> ────────────────────────────────────

@app.route("/machines/<machine_name>", methods=["DELETE"])
def delete_machine(machine_name):
    conn = get_connection()

    row = conn.execute(
        "SELECT * FROM machines WHERE machine_name = ?", (machine_name,)
    ).fetchone()

    if not row:
        conn.close()
        return jsonify({"error": f"Machine '{machine_name}' not found."}), 404

    machine = row_to_dict(row)

    # ── optional: block deletion of reserved machines ─────────────────────────
    if machine["status"] == "reserved":
        force = request.args.get("force", "").lower() == "true"
        if not force:
            return jsonify({
                "error":   f"Machine '{machine_name}' is currently reserved by '{machine['reserved_by']}'.",
                "hint":    "Add ?force=true to delete anyway, or release it first.",
                "release": f"PUT /machines/{machine_name}  {{\"status\":\"available\"}}"
            }), 409

    conn.execute("DELETE FROM machines WHERE machine_name = ?", (machine_name,))
    conn.commit()
    conn.close()

    return jsonify({
        "message":  f"Machine '{machine_name}' deleted.",
        "deleted":  machine,
    })

def get_db_data():
    """Helper function to fetch all rows and columns from the database."""
    conn = get_connection()
    # This row factory allows fetching data as dictionary-like objects (column_name: value)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Replace 'your_table_name' with your actual table
    cursor.execute("SELECT * FROM machines")
    rows = cursor.fetchall()
    conn.close()
    return rows

@app.route('/machines/data/csv', methods=['GET'])
def get_data_csv():
    rows = get_db_data()
    if not rows:
        return Response("No data found", status=200, mimetype='text/csv')

    # Extract headers from the first row keys
    headers = rows[0].keys()

    # Write data to an in-memory string buffer
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header and rows
    writer.writerow(headers)
    for row in rows:
        writer.writerow(list(row))

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-disposition": "attachment; filename=database_export.csv"}
    )

# ── plain-text table for terminal callers ──────────────────────────────────────

def _render_table(machines):
    if not machines:
        return "No machines found.\n"

    # dynamic column widths
    widths = {}
    for key, header in COLUMNS:
        col_max = max((len(m.get(key) or "") for m in machines), default=0)
        widths[key] = max(len(header), col_max)

    def divider():
        return "+-" + "-+-".join("-" * widths[k] for k, _ in COLUMNS) + "-+"

    def fmt_row(values):
        cells = (
            str(v or "").ljust(widths[k])
            for (k, _), v in zip(COLUMNS, values)
        )
        return "| " + " | ".join(cells) + " |"

    lines = [
        divider(),
        fmt_row([h for _, h in COLUMNS]),
        divider(),
    ]
    for m in machines:
        lines.append(fmt_row([m.get(k) for k, _ in COLUMNS]))

    lines.append(divider())
    lines.append(f"  {len(machines)} machine(s).\n")
    return "\n".join(lines)


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
