# IOP Offline Installation Guide

This guide describes a fully offline installation of IOP on Linux x86_64.

## 1. Package contents

```text
IOP-v<version>/
├── offline/
│   ├── python-linux-x86_64.tar.xz   standalone CPython 3.12 runtime
│   ├── bin/busybox                  static extractor for xz
│   ├── wheels/                      backend Python wheels
│   ├── manifest.json                platform and version metadata
│   └── SHA256SUMS                   checksums
├── frontend/dist/                    prebuilt frontend
├── deploy/install-offline.sh        offline installer entry point
├── deploy/install-systemd.sh        shared systemd installer
└── README-OFFLINE.md                Chinese offline guide
```

## 2. Requirements

- Linux x86_64;
- glibc 2.17 or later;
- systemd;
- `tar`, `bash`, `coreutils`, `sed`, `grep`, and `awk`;
- no Internet access, system Python, pip, or apt/dnf download required for the Python runtime.

Supported examples: Ubuntu 20.04+, Debian 11+, RHEL/AlmaLinux/openEuler/Kylin 8+ on x86_64.

Not supported: Alpine/musl and ARM hosts.

## 3. PostgreSQL / Redis provisioning

A fresh installation attempts to install PostgreSQL and Redis automatically and writes the connection settings into the platform. If provisioning fails, the installer falls back to SQLite and the in-process cache with an explicit warning.

For offline provisioning, place packages for the target distribution under:

```text
offline/os-packages/debian/*.deb
offline/os-packages/rhel/*.rpm
```

Generate them on an online machine of the same distribution and architecture:

```bash
sudo bash deploy/prepare-offline-os-packages.sh --target debian
sudo bash deploy/prepare-offline-os-packages.sh --target rhel
```

Without these packages the platform still installs, using SQLite and the in-process cache.

## 4. Install

```bash
unzip IOP-v<version>.zip -d /tmp
cd /tmp/IOP-v<version>
sudo bash deploy/apply-permissions.sh
sudo bash deploy/install-offline.sh
```

The installer:

1. copies the application and `offline/` to `/opt/snmp-monitor`;
2. extracts the standalone Python runtime with the bundled busybox;
3. creates a virtual environment;
4. installs backend wheels with `pip --no-index --find-links`;
5. creates `deploy/snmp-nms.env` with a random `AUTH_SECRET`;
6. installs and starts `snmp-nms.service`;
7. installs the health-check timer.

If PostgreSQL/Redis offline packages are present under `offline/os-packages/`, the installer can use them; otherwise it falls back to SQLite and in-memory cache with a warning.

## 5. Access

```text
https://server-ip/
```

HTTP 80 redirects to HTTPS. The internal application port 8000 is not a public login port.

The first startup generates a 10-year self-signed certificate. Trust it in the browser or upload an enterprise certificate in **System Settings → Login and Security**.

Initial administrator password:

```text
/opt/snmp-monitor/data/initial_admin_password.txt
```

```bash
sudo cat /opt/snmp-monitor/data/initial_admin_password.txt
```

Change the initial password on first login.

## 6. Verify package integrity

```bash
cd /tmp/IOP-v<version>/offline
sha256sum -c SHA256SUMS
```

## 7. Service operations

```bash
systemctl status snmp-nms
systemctl restart snmp-nms
journalctl -u snmp-nms -f
tail -f /opt/snmp-monitor/data/logs/backend.log
curl -k https://127.0.0.1/api/health
```

## 8. Offline limitations

Without Internet access, online MIB download, external AI model calls, upstream platform synchronization, and online updates are unavailable. The core monitoring, local MIB parsing, alerts, assets, topology, rooms, and the web UI continue to work.

## 9. Troubleshooting

- `set: -` or `syntax error`: the shell script has CRLF line endings; use the latest package, whose `.sh` files are LF.
- Missing Python/wheels: verify the ZIP is complete and run `sha256sum -c`.
- HTTPS does not start: check port 443 and certificate configuration. The system may temporarily fall back to HTTP 80.
- Database lock: stop duplicate application processes; for larger deployments use PostgreSQL.
