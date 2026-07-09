Simple machine resource management system.
SERVER="http://<your-server-ip>:5000"

# List all resources from the database
$ curl $SERVER/machines
$ curl "$SERVER/machines?status=available"      # filter by status
$ curl "$SERVER/machines?status=reserved"
$ curl -H "Accept: application/json" $SERVER/machines

# INSERT resource into database
$ curl -s -X POST $SERVER/machines \
  -H "Content-Type: application/json" \
  -d '{"machine_name":"worker-01","platform_name":"x86_64"}'

$ curl -s -X POST $SERVER/machines \
  -H "Content-Type: application/json" \
  -d '{
    "machine_name":  "worker-02",
    "platform_name": "arm64",
    "ip_address":    "10.0.0.42",
    "bmc_name":      "bmc-worker-02",
    "os":            "RHEL 9.3",
    "description":   "rack-3 slot 4"
  }'

# UPDATE resource
# ── UPDATE: status ────────────────────────────────────────────────────────────

$ curl -s -X PUT $SERVER/machines/worker-01 \
  -H "Content-Type: application/json" \
  -d '{"status":"reserved","reserved_by":"alice"}'

$ curl -s -X PUT $SERVER/machines/worker-01 \
  -H "Content-Type: application/json" \
  -d '{"status":"available"}'              # reserved_by auto-cleared

# RELEASE Reservation
# machine is reserved — release it 
$ curl -s -X PUT $SERVER/machines/old-worker-03 \
     -H "Content-Type: application/json" \
     -d '{"status":"available"}'

# DELETE from DB Operations
# Machine is available, can be deleteted from the database
$ curl -s -X DELETE $SERVER/machines/old-worker-03

# Machine is reserved, need to force it to delete it from the database
$ curl -s -X DELETE "$SERVER/machines/old-worker-03?force=true"
