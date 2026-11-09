# SNMP Monitor

An operations and monitoring platform for network devices, security devices, infrastructure, websites, and virtualized environments. It provides asset management, SNMP collection, topology, dashboards, alerts, inspections, data-center visualization, website/certificate monitoring, AI operations, cascade management, and system administration.

- Product version: **v2.22.43**
- License Studio: **v2.10.1**
- Backend: Python 3.10+ / FastAPI / SQLAlchemy
- Frontend: Vue 3 / Vite / Element Plus / ECharts / AntV X6
- Database: SQLite (default) / MySQL / PostgreSQL
- Cache: Redis (optional)
- Deployment: Linux systemd / Docker Compose / Linux offline package
- UI languages: Simplified Chinese, Traditional Chinese, English, Japanese, Korean, German, French, Spanish, Portuguese (Brazil), Russian, Arabic, Hindi

> Release package abbreviation: **IOP** (Intelligent Operations Platform). Packages and release directories are named `IOP-v<version>`.

> This README is the English edition. The Chinese edition is [README.md](README.md). Release packages contain both editions.

> Default login copyright: © 2026 Dalian Elay Technology Co., Ltd. All rights reserved.

## 1. Features

| Menu | Path | Main capabilities |
|---|---|---|
| Dashboard | `/instrument` | Customizable real-time operations dashboard |
| Monitoring overview | `/dashboard` | Device, website, and alert overview |
| Big screens | `/bigscreen` | Website, AI operations, asset, and virtualization screens |
| AI operations | `/ai` | Read-only Q&A, alert analysis, asset statistics, AI reports |
| Assets | `/devices` | Device CRUD, SNMP collection, groups, import/export, tags, warranty, copy |
| Inspections | `/inspection` | Scheduled/manual inspections, Word reports, upload, preview |
| Device backups | `/config-backups` | Network device configuration backups and history |
| Discovery | `/discovery` | Network scanning, SNMP identification, bulk import |
| Instant messaging | `/im` | Direct/group chat, audio/video calls, whiteboard |
| System tools | `/tools` | Ping, traceroute, SNMP walk, port probe, SSH, packet capture |
| MIB management | `/mibs` | MIB import, vendor/model mapping, online MIB lookup, AI-assisted matching |
| Rooms | `/rooms` | Rooms, racks, U positions, 3D digital twin |
| Topology | `/topology` | Network nodes, links, layouts, LLDP discovery |
| Cascade | `/cascade` | Encrypted HQ/branch tunnels and data synchronization |
| Virtualization | `/virtualization` | Read-only VMware, Proxmox, H3C CAS, KVM, Docker, Kubernetes management |
| Website monitoring | `/website` | HTTP/HTTPS availability, status codes, response time, certificates |
| Alert center | `/alerts` | Device, website, and virtualization alerts; acknowledge and history |
| Alert channels | `/notifications` | Email, webhook, SMS, upstream platform |
| Audit logs | `/system/audit` | Login and administrative operation audit |
| System settings | `/system/settings` | General, users, security, collection, backup, update, cluster, network, language |
| License | `/system/license` | Machine code, edition, price, features, activation |

### Asset-level alert rules

The asset list shows each device's asset-level alert rules:

- metric;
- current value;
- threshold and operator;
- current alert level or normal/disabled status.

### MIB online and AI-assisted matching

When no local MIB candidate exists, the operator can fetch vendor MIBs from the LibreNMS public MIB repository. If an external AI model and the AI license feature are available, AI can rank and explain existing candidates. AI cannot invent MIB IDs, bind a MIB directly, or bypass real SNMP OID validation.

### Virtualization alerts

- Confirmed VM alerts flash briefly, leave the current alert list, and move to alert history.
- The alert center aggregates device, website, and virtualization alerts.
- All alert sources can be filtered and acknowledged from the alert center.

## 2. License editions

A fresh installation contains no commercial license file and starts as the **Open Source edition**.

| Edition | Asset limit | Term | Default price | Features |
|---|---:|---|---:|---|
| Open Source | 50 | Permanent | Free | All features |
| Commercial | 100 | Permanent | Contact sales | All features |
| Flagship | 100+ | Permanent | Negotiable | All features, including cascade and cluster |

- AI operations is available in the Open Source edition.
- Cascade management and cluster are available in the Flagship edition.
- Prices, price descriptions, asset limits, node limits, and expiry dates can be customized in License Studio.
- The license is bound to the machine code and stored at `data/license.key`.
- Existing licenses are preserved during upgrades.

## 3. Linux systemd deployment

### Requirements

- Linux x86_64 / arm64 with systemd;
- Python 3.10 or later;
- Default Web login over HTTPS 443; HTTP 80 redirects to HTTPS; internal application port 8000;
- `frontend/dist` is included in the release; Node.js is only needed when rebuilding the frontend.

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip tar curl unzip
```

RHEL / AlmaLinux / openEuler / Kylin:

```bash
sudo dnf install -y python3 python3-pip tar curl unzip
```

### Offline installation

The release bundle includes a standalone Linux x86_64 Python 3.12 runtime compressed with xz, a static busybox extractor, all required Python wheels, and the built frontend. No Internet, system Python, pip, or apt/dnf package download is required.

```bash
unzip IOP-v2.22.43.zip -d /tmp
cd /tmp/IOP-v2.22.43
sudo bash deploy/apply-permissions.sh
sudo bash deploy/install-offline.sh
```

Requirements: Linux x86_64, glibc 2.17+, systemd, bash/coreutils/sed/grep/awk. If system `tar` is missing, the bundled `offline/bin/busybox tar` is used. Offline installs use SQLite and the in-process cache when `offline/os-packages` is empty; with PostgreSQL/Redis packages present they are attempted by default.

### Install

```bash
unzip IOP-v2.22.43.zip -d /tmp
cd /tmp/IOP-v2.22.43

# Fix executable bits if the extraction tool dropped them
bash deploy/apply-permissions.sh

sudo bash deploy/install-systemd.sh
```

The installer:

1. syncs the program to `/opt/snmp-monitor`;
2. creates a Python virtual environment and installs dependencies;
3. creates `deploy/snmp-nms.env` with a random `AUTH_SECRET`;
4. installs and starts `snmp-nms.service`;
5. installs the health-check timer and enables startup on boot.

Open:

```text
https://server-ip/
```

Default Web login uses HTTPS 443; HTTP 80 redirects to HTTPS with 308. `8000` is the internal application port and should not be exposed publicly. A `web_gateway_required` response from port 8000 is expected. On first startup a 10-year self-signed device certificate is generated; trust it once in the browser or upload an enterprise certificate.

The initial administrator password is generated and written to:

```text
/opt/snmp-monitor/data/initial_admin_password.txt
```

View it directly:

```bash
sudo cat /opt/snmp-monitor/data/initial_admin_password.txt
```

The first login must change the password. Do not publish this file.

### Service commands

```bash
systemctl status snmp-nms
systemctl restart snmp-nms
systemctl stop snmp-nms
systemctl enable snmp-nms
journalctl -u snmp-nms -f
tail -f /opt/snmp-monitor/data/logs/backend.log
curl http://127.0.0.1:8000/api/health
```

### Script permissions

Release entries are set to `0755` where appropriate. If the extraction tool loses Unix modes:

```bash
bash deploy/apply-permissions.sh
```

## 4. Docker Compose

```bash
cp .env.example .env
```

Set at least:

```text
POSTGRES_PASSWORD
DATABASE_URL
AUTH_SECRET
AUTH_DEFAULT_PASSWORD
```

Start:

```bash
docker compose up -d --build
```

Access:

```text
https://server-ip/
```

```bash
docker compose ps
docker compose logs -f snmp-nms
docker compose down
```

`docker compose down -v` deletes the database and application volumes. Back up first.

## 6. Configuration

systemd environment file:

```text
/opt/snmp-monitor/deploy/snmp-nms.env
```

| Variable | Default | Description |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Internal listen address |
| `API_PORT` | `8000` | Internal port |
| `DATABASE_URL` | SQLite | Database connection |
| `AUTH_SECRET` | generated | Token signing secret; must match across instances |
| `AUTH_DEFAULT_ADMIN` | `admin` | Initial administrator username |
| `AUTH_DEFAULT_PASSWORD` | empty | If empty, a random password is written to `/opt/snmp-monitor/data/initial_admin_password.txt`; view with `sudo cat` |
| `CORS_ORIGINS` | empty | Same-origin by default; wildcard is not allowed |
| `REDIS_URL` | empty | In-process cache when empty |
| `UPLOAD_DIR` | `data/uploads` | Upload directory |
| `LOG_DIR` | `data/logs` | Log directory |
| `LICENSE_FILE` | `data/license.key` | License file |
| `COLLECTION_INTERVAL` | `60` | Collection interval in seconds |
| `TEMPERATURE_THRESHOLD` | `80` | Temperature warning threshold |
| `TEMPERATURE_CRITICAL_THRESHOLD` | `90` | Temperature critical threshold |
| `SQLITE_BUSY_TIMEOUT_MS` | `30000` | SQLite lock wait |
| `RUN_BACKGROUND_TASKS` | `1` | Set to 1 on the primary node only |
| `METRICS_TOKEN` | empty | Prometheus scrape token |

The Web login protocol and port are stored in system settings. The default is HTTPS 443; HTTP 80 redirects to HTTPS.

## 7. Database and Redis

### SQLite

```text
/opt/snmp-monitor/data/snmp_monitor.db
```

### MySQL

```text
DATABASE_URL=mysql+pymysql://nms:password@127.0.0.1:3306/snmp_nms?charset=utf8mb4
```

### PostgreSQL

```text
DATABASE_URL=postgresql+psycopg2://nms:password@127.0.0.1:5432/snmp_nms
```

### Redis

```text
REDIS_URL=redis://127.0.0.1:6379/0
```

## 8. Upgrade, backup, and restore

The page updater accepts a package containing:

```text
IOP-v<version>/backend/version.json
IOP-v<version>/frontend/dist/index.html
```

Backup systemd deployment:

```bash
sudo systemctl stop snmp-nms
sudo tar -czf /root/snmp-monitor-backup-$(date +%F).tar.gz \
  -C /opt snmp-monitor/data snmp-monitor/deploy/snmp-nms.env
sudo systemctl start snmp-nms
```

Restore: stop the service, restore `data/` and the database, then start the service and verify `/api/health` and the login page.

## 8.1 TURN relay for audio/video

The release bundle includes a standalone coturn binary. Configure the platform host as a TURN relay:

```bash
sudo bash deploy/setup-turn.sh --host <server-ip-reachable-by-clients>
```

Open `3478/TCP`, `3478/UDP`, and `49160-49200/UDP`. The script writes `WEBRTC_TURN_*` settings to `/opt/snmp-monitor/deploy/snmp-nms.env` and restarts the services. Verify `/api/im/webrtc-config` reports `turn_configured: true`.

## 9. Uninstall

Back up first:

```bash
sudo systemctl stop snmp-nms
sudo cp -a /opt/snmp-monitor/data /root/snmp-monitor-data-backup-$(date +%F-%H%M%S)
```

Keep program and data, remove service/env/system user:

```bash
sudo bash /opt/snmp-monitor/uninstall.sh --keep-data
```

Remove program and all data:

```bash
sudo bash /opt/snmp-monitor/uninstall.sh --purge
```

`--purge` removes the program directory, SQLite database, license, uploads, logs and backups. It is irreversible and asks for `DELETE` confirmation. `--purge --yes` skips confirmation and must only be used when the consequences are fully understood.

Docker Compose:

```bash
cd /opt/snmp-monitor
docker compose down      # keep volumes
docker compose down -v   # remove database/upload/log volumes
```

After uninstall, check:

```bash
systemctl status snmp-nms
ls -ld /opt/snmp-monitor
```

External PostgreSQL/Redis, Nginx/Caddy, firewall rules and system backups must be cleaned separately.

## 10. Observability

- Health: `/api/health`
- Prometheus: `/metrics`
- API docs: `/docs` (internal port)
- Logs: `data/logs/backend.log`, `journalctl -u snmp-nms`
- Health-check timer: `snmp-nms-healthcheck.timer`

### Debug diagnostics

Use the standalone **Debug logs** tab to the right of **Network** in System Settings to create a redacted ZIP for support:

- Version, platform, disk and load;
- Recent application logs and ERROR/Traceback summary;
- Redacted configuration snapshot;
- Database table counts (no business data);
- Network interfaces, routes and listening ports;
- Optional problem description and reproduction steps.

Passwords, tokens, API keys, private keys, license files and database content are excluded or redacted. The latest 20 bundles are retained. Collection and download are audited. Required permission: `settings:view`.

## 11. Directory layout

```text
IOP-v2.22.43/
├── backend/
├── frontend/
├── deploy/
├── mibs/
├── tools/
├── data/                 runtime data, not included in release
├── docker-compose.yml
├── Dockerfile
├── SECURITY.md
├── README.md             Chinese README
├── README.en.md          English README
├── run_backend.py
├── start.sh
└── uninstall.sh
```

## 12. Security

- Run security checks before release:

```bash
python tools/security_check.py
python -m compileall -q backend
cd frontend && npm run build
```

- Do not commit `.env`, `data/`, databases, `data/license.key`, `data/.auth_secret`, initial password files, or the license private key.
- See [SECURITY.md](SECURITY.md) for the security baseline, OWASP review, and release blocking rules.

## 13. License

This project is licensed under the **Mozilla Public License 2.0 (MPL-2.0)**.

See [LICENSE](LICENSE) for the full text. The release package includes `LICENSE` automatically; the build fails if the license file is missing.

## 14. Version

This README corresponds to SNMP Monitor **v2.22.43**. Verify the server, network devices, database, and license before deployment.
