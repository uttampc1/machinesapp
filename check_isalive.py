#!/usr/bin/env python3

import requests
from database import get_connection

ISALIVE_PORT = 5001
ISALIVE_PATH = "/isalive"
TIMEOUT_SECS = 5


def check_machine(ip_address):
    if not ip_address or not ip_address.strip():
        return "unknown"

    url = f"http://{ip_address.strip()}:{ISALIVE_PORT}{ISALIVE_PATH}"

    try:
        resp = requests.get(url, timeout=TIMEOUT_SECS)
        if not resp.ok:
            return "off"

        data = resp.json()
        if data.get("status") == "ok":
            return "on"

        return "off"

    except (requests.RequestException, ValueError):
        return "off"


def update_isalive():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, ip_address FROM machines")
    rows = cur.fetchall()

    for row in rows:
        machine_id = row["id"]
        ip_address = row["ip_address"]

        alive_state = check_machine(ip_address)

        cur.execute(
            "UPDATE machines SET isalive = ? WHERE id = ?",
            (alive_state, machine_id)
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    update_isalive()
