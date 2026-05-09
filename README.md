# Cisco Tactical Controller

A PyQt5 GUI application that acts as a network controller and automates IOS-XE firmware
upgrades across a fleet of Cisco devices using a combination of RESTCONF (for version retrieval),
SSH/CLI (for pushing commands, flash checks, ...), and SCP (for image transfer).
The tool also operates as a Command Pusher, sending arbitrary CLI commands to selected
devices and displaying the terminal-style output per device.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Project Structure](#project-structure)
5. [Excel Tracker Setup](#excel-tracker-setup)
6. [IOS Repository Setup](#ios-repository-setup)
7. [Running the Application with Python](#running-the-application-with-python)
8. [Workflow Reference](#workflow-reference)
9. [Logging](#logging)
10. [Known Issues](#known-issues)

---

## Overview

The tool operates in two modes: **Updater** and **Command Pusher**.

**Updater** reads a device inventory from an Excel workbook, connects to each device over SSH,
retrieves the running IOS version via RESTCONF, compares it against a recommended version stored
in the sheet, and orchestrates the full install-mode upgrade sequence:

```
SSH check → RESTCONF check → Version retrieval → Flash check → IOS image file present check → SCP transfer → install add → install activate → (reload) → install commit → install remove inactive → Excel update
```

**Command Pusher** sends a user-supplied list of CLI commands to all selected devices
concurrently, and displays the terminal-style output per device with color-coded result tabs.

Everything is tracked live in the Excel file so you can inspect results per device
at any point during or after the run.

---

## Prerequisites
Note that this requirements are only necessary if you are cloning this repository, not for the compiled application (.zip folder).
### Python

Python **3.9 or later** is required.

### Python packages

Install all dependencies with:

```bash
pip install -r requirements.txt
```

Create a `requirements.txt` containing:

```
pandas>=3.0.2
PyQt5>=5.15.11
psutil>=7.2.2
openpyxl>=3.1.5
netmiko>=4.6.0
paramiko>=4.0.0
scp>=0.15.0
aiohttp>=3.13.5
```

### Network requirements

| Protocol | Port | Direction           | Purpose                        |
|----------|------|---------------------|--------------------------------|
| SSH      | 22   | Controller → Device | CLI, SCP transfer              |
| HTTPS    | 443  | Controller → Device | RESTCONF version retrieval     |
| OOBM     | —    | Out-of-band mgmt    | All connections go via OOBM IP |

SSL certificate validation is disabled (`ssl=False`) — use only on a trusted
management network.

### Device requirements

- Cisco IOS-XE devices in **install mode** (not bundle mode).
- SSH enabled and reachable on the OOBM IP*
- RESTCONF and SCP enabled*
- Credentials must have privilege level 15 (or equivalent) to run `install` commands.

*This can be completed with "COMMAND PUSHER" mode by sending the necessary commands

---

## Installation

```bash
git clone <repo-url>
cd <repo-name>
pip install -r requirements.txt
```

Place the Excel tracker (`LAN_Network_Devices.xlsx`) and the `ios_repository/`
folder in the same directory as the Python files. See the sections below for
their required formats.

---

## Project Structure

```
cisco-tactical-controller/
│
├── program_gui.py                  # Entry point — PyQt5 main window and workers
├── excel_and_data_ops.py           # All DataFrame and Excel I/O operations
├── device_cli_ops.py               # Netmiko SSH/CLI operations (install, cleanup, command push)
├── device_api_ops.py               # aiohttp RESTCONF operations (version retrieval, polling)
├── device_file_transfer_ops.py     # Paramiko + SCP file transfer
├── ip_addressing_ops.py            # IPv4 address validation helper
├── common_helper_functions.py      # Path resolution and version string normalisation
│
├── LAN_Network_Devices.xlsx        # Device inventory and tracking spreadsheet
│
├── ios_repository/                 # Local IOS image storage (you must create this)
│   ├── C9200/                      # One subfolder per device model (matches "Model" column)
│   │   └── cat9k_lite_iosxe.17.15.04c.SPA.bin
│   ├── C9300/
│   │   └── cat9k_iosxe.17.15.04c.SPA.bin
│   └── ...
│
├── execution_logs.log              # Rotating log file (auto-created on first run)
└── requirements.txt
```

---

## Excel Tracker Setup

The workbook must contain a sheet whose name you enter in the GUI. The sheet
must have **all of the following columns** (order does not matter, but names
must match exactly):

| Column                    | Type    | Populated by | Description                                                     |
|---------------------------|---------|--------------|-----------------------------------------------------------------|
| `Hostname`                | Static  | You          | Device hostname, used as the lookup key                         |
| `Model`                   | Static  | You          | Must match the subfolder name in `ios_repository/`              |
| `OOBM IP Address`         | Static  | You          | Management IP used for all connections. Must be unique per row. |
| `Recommended IOS Version` | Static  | You          | Target version string, e.g. `17.15.4c`                          |
| `Current IOS Version`     | Dynamic | Tool         | Retrieved live via RESTCONF                                     |
| `Needs Update`            | Dynamic | Tool         | `YES` / `NO` / `UNKNOWN`                                        |
| `Update IOS File Present` | Dynamic | Tool         | `YES` / `NO` / `N/A`                                            |
| `Enough Flash Space`      | Dynamic | Tool         | `YES` / `NO` / `UNKNOWN` / `N/A`                                |
| `Status`                  | Dynamic | Tool         | `ONLINE` / `OFFLINE`                                            |
| `Auth Status`             | Dynamic | Tool         | `AUTH_OK` / `AUTH_BAD` / `N/A`                                  |
| `RESTCONF Status`         | Dynamic | Tool         | `OPERATIVE` / `NOT_OPERATIVE` / `N/A`                           |
| `SCP Enabled`             | Dynamic | Tool         | `YES` / `NO` / `AUTH_BAD` / `N/A` / `UNKNOWN`                              |
| `Transfer Result`         | Dynamic | Tool         | `SUCCESS` / `FAILED` / `N/A`                                    |
| `Install Status`          | Dynamic | Tool         | `INSTALL_TRIGGERED` / `ADD_FAILED` / `NOT_ATTEMPTED` / …        |
| `Update Result`           | Dynamic | Tool         | `SUCCESS` / `FAILED` / `COMMIT_FAILED` / `UNKNOWN` / `N/A`      |
| `Cleaned Inactive`        | Dynamic | Tool         | `CLEANED` / `NOTHING_TO_CLEAN` / `N/A`/ `...`                         |

All **Dynamic** columns are wiped and rewritten on every run. Do not put
manual data in them.

> **Close the Excel file before running.** The tool checks for open file handles
> at startup and will abort with an error if the file is locked.

> **OOBM IP addresses must be unique.** The tool validates for duplicate IPs during
> the Excel check and will abort with a descriptive error listing all conflicting entries
> if duplicates are found.

---

## IOS Repository Setup

The `ios_repository/` folder is in the application directory. Inside it,
create one subfolder per device model. Some of them already exist. The subfolder name must exactly match
the value in the `Model` column of your Excel sheet.

Place the `.bin` IOS image file inside the matching model folder. The filename
must contain the version string from the `Recommended IOS Version` column.
Leading zeros in version segments are handled automatically
(e.g. `17.15.04c` and `17.15.4c` are treated as equal).

```
ios_repository/
└── C9300/
    └── cat9k_iosxe.17.15.04c.SPA.bin   ← filename must contain "17.15.4c" or "17.15.04c"
```

---

## Running the Application with Python

```bash
python program_gui.py
```

### Updater mode — step-by-step GUI walkthrough
<br/>
1. Enter the Excel sheet name in the text field at the top (e.g. `LAN`).
<br/>
<br/>
2. Click SHOW ELIGIBLE DEVICES.
<br/>
<br/>
3. Enter device credentials in the popup and select UPDATER mode.
   The tool connects to all devices over SSH,
   checks versions and flash space, then populates the Excel tracker.
<br/>
<br/>
4. Review the table. Only devices that pass all eligibility checks appear:
   ONLINE, AUTH_OK, RESTCONF OPERATIVE, SCP ENABLED, IOS image present locally, enough
   flash space, and current version differs from recommended.
<br/>
<br/>
5. Select devices using the checkboxes (or click ALL).
<br/>
<br/>
6. Click START UPDATE.
<br/>
<br/>
7. Choose the transfer mode:
   - Sequential — one device at a time; safe, readable progress per device.
   - Threaded — all devices simultaneously; faster but progress output overlaps.
<br/>
<br/>
8. The tool runs the full install sequence autonomously. A summary dialog appears
   on completion. The Excel tracker is updated after each stage.

### Cancel during transfer

The `CANCEL UPDATE` button is active **only during the SCP transfer stage**.
Clicking it:
- Immediately updates the status label to `Cancelling transfer...` — the UI remains responsive.
- Sets a global cancellation flag to prevent new transfers from starting and abort
  active transfers at the next progress callback by closing the SSH transport.
- Dispatches a daemon thread that connects to each device, clears all VTY lines
  (terminating any lingering SCP session on the router side), and deletes the
  partially transferred file from `bootflash:`.

### Command Pusher mode — step-by-step GUI walkthrough
<br/>
1. Enter the Excel sheet name in the text field at the top.
<br/>
<br/>
2. Click SHOW ELIGIBLE DEVICES.
<br/>
<br/>
3. Enter device credentials in the popup and select COMMAND PUSHER mode.
   The tool connects to all devices over SSH and checks reachability.
<br/>
<br/>
4. Select the devices you want to target using the checkboxes.
<br/>
<br/>
5. Click PUSH COMMANDS.
<br/>
<br/>
6. Type the commands to push — one per line. Up to 20 commands per push.
   Commands are treated as exec-mode. To push config-mode commands, include
   `configure terminal` as the first line.
<br/>
<br/>
7. Click PUSH. The commands are sent concurrently to all selected devices.
<br/>
<br/>
8. The output phase shows a tab per device. Tabs are color-coded:
   - Green — all commands succeeded.
   - Amber — a command error occurred but some commands were pushed (BAD_COMMAND, CONFIG_ERROR, TIMEOUT).
   - Red — a connection-level error occurred and no commands were pushed (AUTH_BAD, OFFLINE, SSH_ERROR, UNEXPECTED_ERROR).
<br/>
<br/>
9. Click any tab to see the full terminal-style output for that device, including
   the device prompt, every command sent, the router's response, and a list of
   any commands that were not pushed due to an earlier error.
<br/>
<br/>
10. Click PUSH MORE to return to the input phase and push a new set of commands
    to the same set of devices.

---

## Workflow Reference

| Stage                 | Function                            | Notes                                                                                                      |
|-----------------------|-------------------------------------|------------------------------------------------------------------------------------------------------------|
| RESTCONF poll         | `get_all_restconf_status`           | Polls `/restconf` endpoint; 30s timeout during Show, 720s after reload.                                  |
| Version retrieval     | `get_all_versions`                  | Uses `Cisco-IOS-XE-device-hardware-oper` YANG model.                                                       |
| Flash check           | `get_flash_free_space_all`          | Parses `show file systems`; prefers `bootflash:` over `flash:`.                                            |
| SCP transfer          | `threaded_transfer_ios_image_all`   | Transfers to `bootflash:/`. Progress bar per device in terminal. Abortable via `cancel_event`.             |
| Boot variable         | `install_ios_image` (stage 1)       | Pushes `boot system bootflash:packages.conf` and saves config before install commands.                     |
| Install add           | `install_ios_image` (stage 2)       | 900s read timeout. Detects dead peers via TCP keepalives + watchdog thread.                               |
| Install activate      | `install_ios_image` (stage 3)       | Uses `send_multiline` with a two-step command list to handle the reload confirmation prompt.                |
| Post-reload wait      | `populate_post_install_columns`     | Sleeps 10 minutes, then polls RESTCONF for up to 12 minutes.                                                |
| Install commit        | `commit_ios_install_all`            | Runs `install commit` to persist the new image.                                                            |
| Version verify        | `get_all_versions` (post-install)   | Confirms running version matches recommended.                                                              |
| Cleanup               | `remove_inactive_ios_all`           | Runs `install remove inactive` and auto-confirms. See BUG 0002 for known limitation on empty bootflash.    |
| Command push          | `push_commands_all`                 | Sends commands concurrently. Returns terminal-style output and status per device.                |

---

## Logging

All operations are logged to `execution_logs.log` in the application directory.
The file rotates at **5 MB** and is replaced (not backed up) when full.

Log format:
```
2025-01-15 14:32:01,234 - device_cli_ops - INFO - 'SW-CORE-01' (10.1.1.1): boot system commands pushed and config saved
```

---

## Known Issues

### 🔴 BUG 0001
When the SCP transfer is finished, a set of CLI commands is pushed to each device as part of the
install sequence. If a device goes offline during this command push, the session will hang for up
to 15 minutes (the Netmiko `read_timeout` value) before raising an error and notifying the GUI.
The Paramiko TCP socket is closed by the OS within ~70 seconds of connectivity loss, but Netmiko
continues attempting to read output until the timeout expires. The error is recorded in the log
file as soon as it occurs; only the GUI notification is delayed.


### 🔴 BUG 0002
`send_multiline` sends `install remove inactive` and waits for the pattern `'Do you want to remove the above files.'`
If there's nothing to remove, IOS skips the prompt entirely and returns to the exec prompt immediately —
the expected pattern never arrives, so `send_multiline` sits and waits for the full `read_timeout=120`
seconds before raising a `ReadTimeout`, which gets caught as `UNEXPECTED_ERROR`. The
`NOTHING_TO_CLEAN` check is never reached in this path. One possible fix is to use `send_command`
for the first step, inspect the output, and only send `y` if the prompt actually appeared. However,
results with that architecture have been failing several times due to the way Netmiko handles
interactive prompts.
