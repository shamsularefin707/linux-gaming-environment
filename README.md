# lgsh

A read-only scanner that checks whether a Ubuntu or Linux Mint machine is set up for gaming (GPU driver, Vulkan, 32-bit support, Steam and optional tools) and reports what it found and how it decided. It uses only the Python standard library and never changes the system.



## Usage

Run these from the repository root, as your normal user (the scanner refuses to run with `sudo`).

```
PYTHONPATH=src python3 -m lgsh.scanner
```

It prints a report and saves the results to `~/.local/state/lgsh/last-scan.json` (or `$XDG_STATE_HOME/lgsh/last-scan.json`).

| Flag | What it does |
| --- | --- |
| `--json` | Print the results as JSON instead of the text report. |
| `--output PATH` | Save the results to PATH. `--output -` means don't save. |
| `--capture FOLDER` | Also save the raw scan data to `FOLDER/lgsh-capture.json`. Refuses to overwrite an existing capture. |
| `--from-capture FILE` | Scan a saved capture instead of this PC. |

Exit codes: 0 scan done and saved; 1 scan done but results (or capture) couldn't be saved, or a capture file couldn't be read; 2 refused to run as root.

### Capturing a real machine (for test fixtures)

On the Ubuntu 26.04 Intel PC, as your normal user:

1. Run `PYTHONPATH=src python3 -m lgsh.scanner --capture ~/lgsh-capture`.
2. The report should print in a few seconds. Check each line by hand against what is actually installed.
3. Check that `~/.local/state/lgsh/last-scan.json` exists.
4. Copy `~/lgsh-capture/lgsh-capture.json` to `tests/fixtures/intel_ubuntu2604_real.json` and set its `provenance` to "captured on Arefin's PC".
5. Add `test_real_intel_capture_statuses` to `tests/test_scan.py` asserting the statuses you confirmed. Any line that is wrong is a bug: add a failing test from the capture, then fix it.
