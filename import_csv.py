#!/usr/bin/env python3
"""
import_csv.py — Import machines from a CSV file into the inventory database.

Usage:
    python3 import_csv.py machines.csv --dry-run
    python3 import_csv.py machines.csv
    python3 import_csv.py machines.csv --server http://10.216.149.190:5000
"""

import csv
import json
import sys
import os
import re
import urllib.request
import urllib.error

SERVER = os.environ.get("INVENTORY_SERVER", "http://10.216.169.120:5000")

COLUMN_MAP = {
    "machine name":     "machine_name",
    "machine_name":     "machine_name",
    "hostname":         "machine_name",
    "name":             "machine_name",
    "platform":         "platform_name",
    "platform name":    "platform_name",
    "arch":             "platform_name",
    "ip":               "ip_address",
    "ip address":       "ip_address",
    "ip_address":       "ip_address",
    "bmc":              "bmc_name",
    "bmc name":         "bmc_name",
    "bmc_name":         "bmc_name",
    "os":               "os",
    "description":      "description",
    "po / sms":         "po_sms",
    "po/sms":           "po_sms",
    "po_sms":           "po_sms",
    "program":          "program",
    "socket":           "socket",
    "system config":    "system_config",
    "system_config":    "system_config",
    "make":             "make",
    "manufacturer":     "make",
    "model":            "model",
    "category":         "category",
    "asset owner":      "asset_owner",
    "assetowner":       "asset_owner",
    "asset_owner":      "asset_owner",
    "owner":            "asset_owner",
    "serial":           "serial",
    "serial number":    "serial",
    "maas switch":      "maas_switch",
    "maas_switch":      "maas_switch",
    "switch":           "maas_switch",
    "pdu ip":           "pdu_ip",
    "pdu_ip":           "pdu_ip",
    "pdu port":         "pdu_port",
    "pdu_port":         "pdu_port",
    "site":             "site",
    "lab":              "lab",
    "row":              "row_location",
    "row_location":     "row_location",
    "rack":             "rack",
    "ru":               "ru",
    "cpu":              "cpu",
    "backplane":        "backplane",
    "jira":             "jira",
    "jira #":           "jira",
    "jira#":            "jira",
    "box id":           "box_id",
    "box_id":           "box_id",
    "current project":  "current_project",
    "current_project":  "current_project",
    "notes":            "_notes",
    "comments":         "_comments",
    "engineer":         "_engineer",
    "assigned to":      "_engineer",
    "reserved by":      "_engineer",
    "last updated":     "_ignore",
    "last_updated":     "_ignore",
}

VALID_DB_FIELDS = {
    "machine_name", "platform_name", "ip_address", "bmc_name", "os",
    "description", "po_sms", "program", "socket", "system_config",
    "make", "model", "category", "asset_owner", "serial", "maas_switch",
    "pdu_ip", "pdu_port", "site", "lab", "row_location", "rack", "ru",
    "cpu", "backplane", "jira", "box_id", "current_project",
}


def clean(value):
    if value is None:
        return None
    v = str(value).strip()
    return v if v else None


def slugify(text, max_len=60):
    text = text.lower().strip()
    text = text.replace('=', '-')
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    return text[:max_len]


def generate_machine_name(row_data, row_number):
    bmc = row_data.get("bmc_name")
    if bmc:
        name = slugify(bmc)
        if name:
            return name

    serial = row_data.get("serial")
    if serial:
        name = slugify(serial)
        if name:
            return name

    parts = []
    make = row_data.get("make", "")
    if make:
        s = slugify(make, 10)
        if s:
            parts.append(s)
    model = row_data.get("model", "")
    if model:
        s = slugify(model, 25)
        if s:
            parts.append(s)
    po = row_data.get("po_sms", "")
    if po:
        s = slugify(po, 15)
        if s:
            parts.append(s)

    if parts:
        return f"{'-'.join(parts)}-{row_number:03d}"

    return f"machine-{row_number:04d}"


def detect_delimiter(filepath):
    with open(filepath, "r", encoding="utf-8-sig") as f:
        first_line = f.readline()
        tabs = first_line.count('\t')
        commas = first_line.count(',')
        return '\t' if tabs > commas else ','


def map_row(csv_headers, csv_row, row_number):
    record = {}
    warnings = []
    engineer = None
    notes_parts = []

    for header, value in zip(csv_headers, csv_row):
        header_lower = header.strip().lower()
        value_clean = clean(value)

        if not value_clean:
            continue

        db_field = COLUMN_MAP.get(header_lower)

        if db_field is None:
            warnings.append(f"  Unknown column '{header}' -> skipped")
            continue

        if db_field == "_ignore":
            continue

        if db_field == "_engineer":
            engineer = value_clean
            continue

        if db_field == "_notes":
            notes_parts.append(value_clean)
            continue

        if db_field == "_comments":
            notes_parts.append(value_clean)
            continue

        if db_field in VALID_DB_FIELDS:
            record[db_field] = value_clean

    # combine notes/comments into description
    if notes_parts:
        existing_desc = record.get("description", "")
        combined = "; ".join(notes_parts)
        if existing_desc:
            record["description"] = f"{existing_desc}; {combined}"
        else:
            record["description"] = combined

    # auto-generate machine_name
    if "machine_name" not in record:
        record["machine_name"] = generate_machine_name(record, row_number)
        if record["machine_name"]:
            warnings.append(f"  Auto-generated name: {record['machine_name']}")
    # final safety check — machine_name must not be empty
    if not record.get("machine_name"):
        record["machine_name"] = f"machine-{row_number:04d}"
        warnings.append(f"  Fallback name: {record['machine_name']} (all name sources were empty)")

    # default platform_name
    if "platform_name" not in record:
        record["platform_name"] = "x86_64"

    # handle engineer -> reserved_by
    if engineer:
        # skip non-person values
        skip_values = {'unallocated', 'reserved', 'none', 'n/a', 'tbd', ''}
        if engineer.lower().strip() not in skip_values:
            record["_reserved_by"] = engineer

    # check if row has meaningful data
    has_data = any(
        record.get(f) for f in VALID_DB_FIELDS
        if f not in ("machine_name", "platform_name")
    )
    if not has_data:
        return record, warnings, "row has no meaningful data"

    return record, warnings, None


def fetch_existing(server):
    try:
        req = urllib.request.Request(
            f"{server}/machines",
            headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            machines = json.loads(resp.read().decode())
            return {m["machine_name"] for m in machines}
    except Exception as e:
        print(f"  Warning: could not fetch existing machines: {e}")
        return set()


def post_machine(server, record):
    reserved_by = record.pop("_reserved_by", None)

    payload = json.dumps(record).encode("utf-8")

    req = urllib.request.Request(
        f"{server}/machines",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            msg = result.get("message", "inserted")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
            return False, err.get("error", body)
        except Exception:
            return False, f"HTTP {e.code}: {body}"
    except Exception as e:
        return False, str(e)

    # reserve if engineer was set
    if reserved_by:
        machine_name = record["machine_name"]
        status_payload = json.dumps({
            "status": "reserved",
            "reserved_by": reserved_by
        }).encode("utf-8")

        encoded_name = urllib.request.quote(machine_name, safe='')
        status_req = urllib.request.Request(
            f"{server}/machines/{encoded_name}",
            data=status_payload,
            headers={"Content-Type": "application/json"},
            method="PUT"
        )

        try:
            with urllib.request.urlopen(status_req, timeout=10) as resp:
                msg += f" | reserved by {reserved_by}"
        except Exception as e:
            msg += f" | WARNING: reserve failed: {e}"

    return True, msg


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Import machines from CSV/TSV into the inventory."
    )
    parser.add_argument("csvfile", help="Path to the CSV/TSV file")
    parser.add_argument("--server", default=SERVER,
                        help=f"Server URL (default: {SERVER})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be imported without doing it")
    parser.add_argument("--show-mapping", action="store_true",
                        help="Show column mapping and exit")
    parser.add_argument("--allow-duplicates", action="store_true",
                        help="Don't skip machines that already exist")
    parser.add_argument("--delimiter", default=None,
                        help="Field delimiter (auto-detected if not set)")

    args = parser.parse_args()

    if args.show_mapping:
        print("\nColumn Mapping (CSV header -> database field):\n")
        seen = {}
        for csv_col, db_field in sorted(COLUMN_MAP.items()):
            if db_field.startswith("_"):
                label = {
                    "_engineer": "-> reserved_by + sets status='reserved'",
                    "_notes": "-> appended to description",
                    "_comments": "-> appended to description",
                    "_ignore": "(ignored)"
                }.get(db_field, db_field)
            else:
                label = db_field
            if db_field not in seen:
                seen[db_field] = True
                print(f"  {csv_col:<25} -> {label}")
        print()
        return

    if not os.path.isfile(args.csvfile):
        print(f"Error: file not found: {args.csvfile}")
        sys.exit(1)

    # detect delimiter
    delimiter = args.delimiter
    if delimiter is None:
        delimiter = detect_delimiter(args.csvfile)
        delim_name = "TAB" if delimiter == '\t' else f"comma"
        print(f"  Auto-detected delimiter: {delim_name}")

    # read file — try UTF-8 first, fall back to Windows-1252 (cp1252)
    file_encoding = "utf-8-sig"
    try:
        with open(args.csvfile, "r", encoding=file_encoding) as f:
            f.read()  # test read
    except UnicodeDecodeError:
        file_encoding = "cp1252"
        print(f"  Note: file is not UTF-8, using Windows-1252 encoding.")

    with open(args.csvfile, "r", encoding=file_encoding) as f:
        reader = csv.reader(f, delimiter=delimiter)
        headers = next(reader)
        rows = list(reader)

    print(f"\n{'='*65}")
    print(f"  CSV Import -- {len(rows)} data rows from {args.csvfile}")
    print(f"  Server: {args.server}")
    if args.dry_run:
        print(f"  *** DRY RUN -- nothing will be sent ***")
    print(f"{'='*65}\n")

    # show header mapping
    print("Column mapping for this file:")
    unmapped = []
    for h in headers:
        h_lower = h.strip().lower()
        db_field = COLUMN_MAP.get(h_lower)
        if db_field:
            if db_field.startswith("_"):
                label = {
                    "_engineer": "reserved_by + status",
                    "_notes": "description (append)",
                    "_comments": "description (append)",
                    "_ignore": "(ignored)"
                }.get(db_field, db_field)
            else:
                label = db_field
            print(f"  OK '{h}' -> {label}")
        else:
            print(f"  ?? '{h}' -> UNMAPPED (skipped)")
            unmapped.append(h)
    print()

    if unmapped:
        print(f"  Warning: {len(unmapped)} unmapped column(s): {', '.join(unmapped)}\n")

    # fetch existing
    existing = set()
    if not args.allow_duplicates and not args.dry_run:
        print("Fetching existing machines from server...")
        existing = fetch_existing(args.server)
        print(f"  Found {len(existing)} existing machine(s).\n")

    # process rows
    success = 0
    skip = 0
    fail = 0
    empty = 0
    seen_names = set()

    for i, row in enumerate(rows, start=1):
        if not any(clean(v) for v in row):
            empty += 1
            continue

        record, warnings, skip_reason = map_row(headers, row, i)
        name = record.get("machine_name", f"row-{i}")

        # deduplicate within the file
        original_name = name
        suffix = 1
        while name in seen_names or name in existing:
            suffix += 1
            name = f"{original_name}-{suffix:02d}"

        if name != original_name:
            record["machine_name"] = name
            warnings.append(f"  Renamed: {original_name} -> {name} (duplicate)")

        print(f"[{i:3d}] {name}")
        for w in warnings:
            print(f"      {w}")

        if skip_reason:
            print(f"      SKIP: {skip_reason}")
            skip += 1
            print()
            continue

        if not args.allow_duplicates and original_name in existing:
            print(f"      SKIP: already exists in database")
            skip += 1
            print()
            continue

        if args.dry_run:
            print(f"      DRY RUN -- would insert:")
            for k, v in sorted(record.items()):
                if not k.startswith("_"):
                    print(f"        {k}: {v}")
            rb = record.get("_reserved_by")
            if rb:
                print(f"        -> would reserve for: {rb}")
            success += 1
            seen_names.add(name)
            print()
            continue

        ok, msg = post_machine(args.server, record)

        if ok:
            print(f"      OK {msg}")
            success += 1
            existing.add(name)
            seen_names.add(name)
        else:
            print(f"      FAILED: {msg}")
            fail += 1

        print()

    print(f"\n{'='*65}")
    print(f"  Import Summary")
    print(f"{'='*65}")
    print(f"  Total rows:      {len(rows)}")
    print(f"  Empty rows:      {empty}")
    print(f"  Inserted:        {success}")
    print(f"  Skipped:         {skip}")
    print(f"  Failed:          {fail}")
    print(f"{'='*65}\n")

    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
