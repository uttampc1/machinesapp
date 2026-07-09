from flask import Flask, request, jsonify, render_template
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
    ("description",   "DESCRIPTION"),
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


# ── INSERT ─────────────────────────────────────────────────────────────────────
# POST /machines
# Required body fields: machine_name, platform_name

@app.route("/machines", methods=["POST"])
def insert_machine():
    data = request.get_json(silent=True) or {}

    missing = [f for f in ("machine_name", "platform_name") if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO machines
                (machine_name, platform_name, ip_address,
                 bmc_name, os, description, status, reserved_by)
            VALUES (?, ?, ?, ?, ?, ?, 'available', NULL)
        """, (
            data["machine_name"],
            data["platform_name"],
            data.get("ip_address"),
            data.get("bmc_name"),
            data.get("os"),
            data.get("description"),
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
    app.run(host="0.0.0.0", port=5000, debug=True)
