# Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only command-line scanner that checks an Ubuntu/Mint PC for everything gaming needs and prints a plain report plus a JSON results file.

**Architecture:** Three layers. A **collector** runs a fixed allowlist of read-only commands and file reads and stores their raw results in a `Snapshot`. **Checks** are pure functions `Snapshot -> Item`, so every check is tested from saved snapshots (fixtures) without touching the real system. A **report** layer renders the items to text and JSON. The same snapshot format is what `--capture` saves, so a capture from any PC becomes a test fixture.

**Tech Stack:** Python 3.12+ standard library only (runtime and tests). Tests use `unittest`, run with `python3 -m unittest`.

**Spec:** `docs/superpowers/specs/2026-10-12-scanner-design.md` (approved 2026-10-12). Read it alongside this plan.

## Global Constraints

- Standard library only, at runtime and in tests. Python floor: 3.12 (Ubuntu 24.04, Mint 22).
- Never runs `sudo`/`pkexec`; never runs a program outside `ALLOWED_PROGRAMS`; `subprocess.run(..., shell=False)` always; no network.
- Writes only: the results file (atomic: temp file + `os.replace`) and, when asked, the `--capture` file. Never overwrites an existing capture file.
- `missing` requires positive evidence of absence. Tool not found / errored / timed out => `unknown`, except the "present but broken" cases in the spec, which are `warning`.
- One failing check never stops the others.
- Required items: `gpu_driver`, `vulkan`, `multiarch_32bit`, `steam`. Optional: `heroic`, `ge_proton`, `mangohud`, `gamemode`. `distro` and `gpu` are informational (`required=False`).
- Supported: `ID=ubuntu` with `VERSION_ID >= 24.04`; `ID=linuxmint` with major version `>= 22`. Anything else: `warning` "unsupported", all checks still run.
- Report copy: no emoji, no exclamation marks, one line per item, missing lines say what the thing is for in under ten words.
- Package name placeholder: `lgsh` (project name still open). Results file: `$XDG_STATE_HOME/lgsh/last-scan.json`, default `~/.local/state/lgsh/last-scan.json`. `schema_version = 1`.
- Every item except `not_applicable` carries at least one `Evidence` for the command, file or folder it was decided from (spec: "every result shows how it was decided").
- All commands run with env `LC_ALL=C` so output parsing doesn't depend on the user's language.

## Review Focus

1. **Run with `sudo` by mistake.** Home becomes `/root`, so launcher paths are wrong. Expected: refuse with "Run this as your normal user, without sudo." and exit 2. (Task 12, `test_refuses_root`.)
2. **Garbage or empty command output** (truncated `lspci`, empty `vulkaninfo`). Expected: that item is `unknown`, never a crash; a check that raises becomes `unknown` "The scanner hit an internal error on this check." (Task 10, `test_check_exception_becomes_unknown`; each parser has an empty-input test.)
3. **Results file can't be written** (read-only home, disk full). Expected: report still prints, then "Couldn't save results: <reason>", exit 1, no partial file. (Task 10, `test_write_failure_leaves_no_file`; Task 12, `test_save_failure_exit_code`.)
4. **Hybrid laptop (Intel + NVIDIA).** Expected: both GPUs listed, driver judged per GPU, 32-bit drivers required for each vendor. (Fixture `hybrid_intel_nvidia`, Tasks 5 and 7.)
5. **Snap or Flatpak tool absent** (`snap`/`flatpak` not installed). Expected: treated as "no snaps/flatpaks installed" (positive evidence), not `unknown`; but `dpkg-query` absent or failing => `unknown`. (Task 4, `test_snap_not_found_means_none`.)

---

## File Structure

```
lgsh/                         repo root (new git repo)
  pyproject.toml              metadata, console script lgsh-scan = lgsh.scanner.cli:main
  README.md                   how to run, how to capture
  src/lgsh/__init__.py        __version__ = "0.1.0"
  src/lgsh/scanner/
    model.py                  Status, Evidence, Item, ScanResult, worst()
    runner.py                 CommandResult, FileRead, DirListing, run_command, read_file, list_dir, allowlists
    snapshot.py               Snapshot, COMMANDS, FILES, DIRS, collect(), save/load
    sources.py                PackageIndex (dpkg), parse_snaps, parse_flatpaks, Gpu, parse_gpus
    checks/distro.py          check_distro, check_gpu
    checks/driver.py          check_gpu_driver
    checks/vulkan.py          check_vulkan
    checks/multiarch.py       check_multiarch
    checks/launchers.py       check_steam, check_heroic
    checks/extras.py          check_ge_proton, check_mangohud, check_gamemode
    scan.py                   ALL_CHECKS, run_scan(snapshot) -> ScanResult
    storage.py                default_results_path, write_json_atomic
    report.py                 render_text(result) -> str
    cli.py                    main(argv) -> int
  tests/
    fixtures/*.json           saved snapshots, each with a "provenance" field
    helpers.py                load_fixture(name) -> Snapshot, make_snapshot(**overrides)
    test_*.py                 one per module
```

---

### Task 1: Project skeleton and result model

**Files:**
- Create: `pyproject.toml`, `README.md`, `src/lgsh/__init__.py`, `src/lgsh/scanner/__init__.py`, `src/lgsh/scanner/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Produces:
  - `class Status(StrEnum)`: `OK="ok"`, `WARNING="warning"`, `MISSING="missing"`, `UNKNOWN="unknown"`, `NOT_APPLICABLE="not_applicable"`
  - `@dataclass Evidence(source: str, output: str)` where `source` is the command line or file path, `output` trimmed to 2000 chars by `Evidence.of(source, text)`
  - `@dataclass Item(id: str, title: str, status: Status, required: bool, summary: str, details: dict = {}, evidence: list[Evidence] = [])` with `to_dict() -> dict`
  - `@dataclass ScanResult(items: list[Item], scanned_at: str, scanner_version: str, schema_version: int = 1)` with `to_dict()` and `item(id) -> Item`
  - `worst(statuses: Iterable[Status]) -> Status`, severity `MISSING > WARNING > UNKNOWN > OK > NOT_APPLICABLE`; empty input => `NOT_APPLICABLE`

- [ ] **Step 1:** `git init lgsh`, add `pyproject.toml` (setuptools, `requires-python = ">=3.12"`, no dependencies, script `lgsh-scan`), `README.md` with one paragraph and `python3 -m lgsh.scanner.cli`.
- [ ] **Step 2: Write failing tests** `test_worst_order` (`worst([OK, WARNING, UNKNOWN]) == WARNING`, `worst([OK, MISSING, WARNING]) == MISSING`, `worst([]) == NOT_APPLICABLE`), `test_evidence_trims` (`len(Evidence.of("x", "a"*5000).output) == 2000`), `test_item_to_dict` (status serialises as `"ok"`, keys `id,title,status,required,summary,details,evidence`).
- [ ] **Step 3:** Run `PYTHONPATH=src python3 -m unittest tests.test_model -v`. Expected: FAIL (import error).
- [ ] **Step 4:** Implement `model.py`.
- [ ] **Step 5:** Re-run. Expected: PASS.
- [ ] **Step 6:** Commit `feat: project skeleton and scan result model`.

### Task 2: Safe command runner and readers

**Files:**
- Create: `src/lgsh/scanner/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Produces:
  - `ALLOWED_PROGRAMS = frozenset({"lspci", "vulkaninfo", "dpkg-query", "dpkg", "snap", "flatpak", "nvidia-smi"})`
  - `@dataclass CommandResult(argv: list[str], returncode: int | None, stdout: str, stderr: str, error: str | None)`; `error` is one of `None`, `"not_found"`, `"timeout"`, `"os_error"`; property `ok` = `error is None and returncode == 0`; `to_dict()` / `from_dict()`
  - `@dataclass FileRead(path: str, content: str | None, error: str | None)`; `error` `"absent"` when the file doesn't exist, `"os_error"` otherwise
  - `@dataclass DirListing(path: str, entries: list[str] | None, error: str | None)`; `error` `"absent"` when the folder doesn't exist (positive evidence), `"os_error"` for permission and other failures
  - `run_command(argv: list[str], timeout: float = 10.0) -> CommandResult`; raises `ValueError` if `argv[0]` not in `ALLOWED_PROGRAMS`
  - `read_file(path: str) -> FileRead`, `list_dir(path: str) -> DirListing` (sorted entries)

- [ ] **Step 1: Write failing tests:** `test_rejects_unlisted_program` (`run_command(["rm", "-rf", "/tmp/x"])` raises `ValueError`, and `subprocess.run` is never called; patch it and assert not called), `test_not_found` (patch `subprocess.run` to raise `FileNotFoundError` => `error == "not_found"`, `ok is False`), `test_timeout` (raise `subprocess.TimeoutExpired` => `error == "timeout"`), `test_runs_without_shell_and_with_c_locale` (patched call receives `shell=False`, `env["LC_ALL"] == "C"`, `stdin=subprocess.DEVNULL`), `test_list_dir_absent_vs_denied` (temp dir: missing path => `error == "absent"`; `chmod 000` dir => `error == "os_error"`, skip if running as root), `test_command_result_roundtrip`.
- [ ] **Step 2:** Run `PYTHONPATH=src python3 -m unittest tests.test_runner -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `runner.py`. Decode output with `errors="replace"` so odd bytes never crash.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: allowlisted read-only command runner`.

### Task 3: Snapshot, collector and capture files

**Files:**
- Create: `src/lgsh/scanner/snapshot.py`, `tests/helpers.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: Task 2 types and functions.
- Produces:
  - `COMMANDS: dict[str, tuple[list[str], float]]` (key -> argv, timeout):
    - `"lspci": (["lspci", "-nnk"], 10)`
    - `"vulkaninfo": (["vulkaninfo", "--summary"], 20)`
    - `"foreign_arch": (["dpkg", "--print-foreign-architectures"], 10)`
    - `"dpkg": (["dpkg-query", "-W", "-f=${binary:Package}\t${db:Status-Abbrev}\t${Version}\n"], 20)`
    - `"snap": (["snap", "list"], 10)`
    - `"flatpak": (["flatpak", "list", "--columns=application,version"], 10)`
    - `"nvidia_smi": (["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], 10)`
  - `FILES: dict[str, str]`: `"os_release": "/etc/os-release"`, `"nvidia_version": "/proc/driver/nvidia/version"`
  - `DIRS: dict[str, str]` (paths with `~`, expanded only at collect time so fixtures stay portable): `"icd_usr": "/usr/share/vulkan/icd.d"`, `"icd_etc": "/etc/vulkan/icd.d"`, `"steam_root_compat": "~/.steam/root/compatibilitytools.d"`, `"steam_share_compat": "~/.local/share/Steam/compatibilitytools.d"`, `"steam_flatpak_compat": "~/.var/app/com.valvesoftware.Steam/data/Steam/compatibilitytools.d"`, `"steam_snap_compat": "~/snap/steam/common/.local/share/Steam/compatibilitytools.d"`, `"heroic_proton": "~/.config/heroic/tools/proton"`, `"heroic_flatpak_proton": "~/.var/app/com.heroicgameslauncher.hgl/config/heroic/tools/proton"`, `"heroic_config": "~/.config/heroic"`
  - `@dataclass Snapshot(commands: dict[str, CommandResult], files: dict[str, FileRead], dirs: dict[str, DirListing], provenance: str = "live")` with `to_dict()`, `from_dict()`; a key missing from a fixture behaves as `CommandResult(error="not_found")` / `FileRead(error="absent")` / `DirListing(error="absent")` via `snapshot.cmd(key)`, `snapshot.file(key)`, `snapshot.dir(key)`
  - `collect(run=run_command, read=read_file, ls=list_dir, home: Path | None = None) -> Snapshot`
  - `save_capture(snapshot: Snapshot, folder: Path) -> Path` writes `folder/lgsh-capture.json` with `provenance = "captured <ISO date>"` (no hostname or username); raises `FileExistsError` if that file already exists
  - `load_snapshot(path: Path) -> Snapshot`
  - `tests/helpers.py`: `load_fixture(name: str) -> Snapshot` (reads `tests/fixtures/<name>.json`), `make_snapshot(commands=None, files=None, dirs=None) -> Snapshot`

- [ ] **Step 1: Write failing tests:** `test_collect_calls_every_command_once` (fake `run` records argv; set equals `COMMANDS` argvs), `test_collect_expands_home` (fake `ls` receives `/home/test/.steam/root/compatibilitytools.d` for `home=Path("/home/test")`), `test_snapshot_roundtrip`, `test_missing_key_defaults` (`make_snapshot().cmd("lspci").error == "not_found"`), `test_save_capture_refuses_overwrite` (second save raises `FileExistsError`, original content unchanged).
- [ ] **Step 2:** Run `PYTHONPATH=src python3 -m unittest tests.test_snapshot -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `snapshot.py` and `tests/helpers.py`.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: snapshot collector and capture files`.

### Task 4: Package sources, distro and GPU detection

**Files:**
- Create: `src/lgsh/scanner/sources.py`, `src/lgsh/scanner/checks/__init__.py`, `src/lgsh/scanner/checks/distro.py`, fixture `tests/fixtures/intel_ubuntu2604.json`
- Test: `tests/test_sources.py`, `tests/test_distro.py`

**Interfaces:**
- Consumes: `Snapshot`, `CommandResult`, `Item`, `Status`.
- Produces:
  - `class PackageIndex`: `from_command(r: CommandResult) -> PackageIndex | None` (None unless `r.ok`); installed means `db:Status-Abbrev` starts with `"ii"`; `installed(name: str, arch: str | None = None) -> bool` (arch None matches `name` and `name:<any>`; arch given matches only `name:<arch>`); `version(name) -> str | None`; `names_matching(prefix: str) -> list[str]`
  - `parse_snaps(r: CommandResult) -> set[str] | None`: `error == "not_found"` => `set()` (no snap tool means no snaps); other failures => `None`; else first column of each line after the header
  - `parse_flatpaks(r: CommandResult) -> set[str] | None`: same rule; app IDs from first column
  - `@dataclass Gpu(vendor: str, vendor_id: str, name: str, driver: str | None)`; `vendor` in `"amd" | "nvidia" | "intel" | "other"`
  - `parse_gpus(r: CommandResult) -> list[Gpu] | None`: None unless `r.ok`; device blocks whose class is `[0300]`, `[0302]` or `[0380]`; vendor from `[xxxx:yyyy]` vendor ID `1002`/`10de`/`8086`; driver from the block's `Kernel driver in use:` line, else None
  - `check_distro(s: Snapshot) -> Item` (id `"distro"`, title `"System"`, details `{"id","version","pretty_name","ubuntu_codename"}`)
  - `check_gpu(s: Snapshot) -> Item` (id `"gpu"`, title `"Graphics card"`, details `{"gpus": [asdict(Gpu)...]}`): `unknown` if `parse_gpus` is None or returns `[]`; `ok` if any vendor recognised; `warning` "This graphics card isn't supported yet." if all `other`

Sample `lspci -nnk` block the parser must handle:
```
00:02.0 VGA compatible controller [0300]: Intel Corporation Alder Lake-P GT2 [Iris Xe Graphics] [8086:46a6] (rev 0c)
	Subsystem: Lenovo Device [17aa:3a29]
	Kernel driver in use: i915
	Kernel modules: i915, xe
```

- [ ] **Step 1: Write failing tests:** `test_package_index_installed_and_arch` (lines `mesa-vulkan-drivers:amd64\tii \t24.2`, `mesa-vulkan-drivers:i386\tii \t24.2`, `steam-installer\trc \t1.0` => `installed("mesa-vulkan-drivers")`, `installed("mesa-vulkan-drivers", "i386")`, not `installed("steam-installer")`), `test_package_index_none_on_failure`, `test_snap_not_found_means_none` (`set()`), `test_snap_error_is_unknown` (`returncode=1` => `None`), `test_parse_gpus_intel_block` (sample above => one `Gpu("intel", "8086", "Intel Corporation Alder Lake-P GT2 [Iris Xe Graphics]", "i915")`), `test_parse_gpus_hybrid` (Intel + NVIDIA `[0302]` blocks => two GPUs), `test_parse_gpus_empty_output_is_unknown_item`, `test_distro_ubuntu_2604_ok`, `test_distro_ubuntu_2204_warning`, `test_distro_mint_22_ok`, `test_distro_popos_unsupported_warning` (`ID=pop`, `ID_LIKE="ubuntu debian"`), `test_distro_missing_file_unknown`.
- [ ] **Step 2:** Run `PYTHONPATH=src python3 -m unittest tests.test_sources tests.test_distro -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `sources.py` and `checks/distro.py`. Compare versions as integer tuples (`"24.04"` -> `(24, 4)`).
- [ ] **Step 4:** Write fixture `intel_ubuntu2604.json` (provenance `"hand-written, replace with Arefin's capture"`): Ubuntu 26.04, the Intel block above, `vulkaninfo` absent, i386 not enabled, Snap Steam, no Heroic/MangoHud/GameMode.
- [ ] **Step 5:** Re-run. Expected: PASS.
- [ ] **Step 6:** Commit `feat: package sources, distro and GPU detection`.

### Task 5: Graphics driver check

**Files:**
- Create: `src/lgsh/scanner/checks/driver.py`, fixtures `nvidia_proprietary.json`, `nvidia_nouveau_pending.json`, `hybrid_intel_nvidia.json`, `amd_radeon_legacy.json`
- Test: `tests/test_driver.py`

**Interfaces:**
- Consumes: `parse_gpus`, `PackageIndex`, `worst`.
- Produces: `check_gpu_driver(s: Snapshot) -> Item` (id `"gpu_driver"`, title `"Graphics driver"`, required, details `{"per_gpu": [{"name","vendor","driver","status","note"}], "nvidia_version": str | None}`). Overall status = `worst` of per-GPU statuses; GPU list None/empty => `unknown`.

Per-GPU rules (from the spec):

| Vendor | Driver in use | Status | Summary |
|---|---|---|---|
| nvidia | `nvidia` | ok, or warning if `nvidia_smi` stderr/stdout contains "couldn't communicate" | "Working (NVIDIA <version>)" / "Installed, but not responding. A restart usually fixes this." |
| nvidia | `nouveau` or None, and any installed package starting `nvidia-driver-` | warning | "Installed, but not active yet. A restart is usually needed." |
| nvidia | `nouveau`, no package | warning | "Using the open-source nouveau driver, which is slow for games." |
| nvidia | None, no package | missing | "No NVIDIA driver installed." |
| amd | `amdgpu` | ok | |
| amd | `radeon` | warning | "Using the old radeon driver. Games need amdgpu." |
| intel | `i915` or `xe` | ok | |
| amd/intel | None | warning | "No driver is active for this card." |
| other | any | not_applicable | |

NVIDIA version: `nvidia_smi` stdout first line if ok, else parse `NVRM version: ... Kernel Module  <x.y.z>` from `nvidia_version` file, else None. The NVIDIA "missing" case needs `PackageIndex` non-None; if dpkg can't be read, that case is `unknown`.

- [ ] **Step 1: Write failing tests**, one per table row, plus `test_hybrid_both_listed` (fixture `hybrid_intel_nvidia`: Intel `i915` + NVIDIA `nvidia` => ok, two `per_gpu` entries), `test_dpkg_unreadable_nvidia_no_driver_is_unknown`.
- [ ] **Step 2:** Run `PYTHONPATH=src python3 -m unittest tests.test_driver -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `check_gpu_driver`. Write the four fixtures with provenance labels (public source URL, or `"hand-written"`).
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: graphics driver check`.

### Task 6: Vulkan check

**Files:**
- Create: `src/lgsh/scanner/checks/vulkan.py`
- Test: `tests/test_vulkan.py`

**Interfaces:**
- Consumes: `Snapshot`, `parse_gpus`.
- Produces: `check_vulkan(s: Snapshot) -> Item` (id `"vulkan"`, title `"Vulkan"`, required, details `{"devices": [{"name","type","driver"}], "icd_files": [...]}`).

Rules, in order:
1. `vulkaninfo` ok: parse each `GPUn:` section's `deviceName`, `deviceType`, `driverName`. Any device whose type isn't `PHYSICAL_DEVICE_TYPE_CPU` => ok, summary "Working (<driverName list>)". Only CPU devices => warning "Only the slow software renderer was found, so games won't run well." No devices parsed => unknown.
2. `vulkaninfo` ran and failed (`error is None`, `returncode != 0`) and at least one GPU has a driver in use => warning "Vulkan failed to start. The graphics driver may need a restart or reinstall." Otherwise unknown.
3. `vulkaninfo` timed out or `os_error` => unknown "Vulkan check timed out." / reason.
4. `vulkaninfo` not found: `.json` files in `icd_usr` + `icd_etc`. Some => unknown "The vulkaninfo tool isn't installed. Driver files are present, so Vulkan is likely fine." Both listings `absent` or empty => missing "No Vulkan driver installed." Any listing `os_error` and no files => unknown.

- [ ] **Step 1: Write failing tests:** `test_real_gpu_ok`, `test_llvmpipe_only_warning`, `test_failed_with_driver_warning`, `test_failed_without_driver_unknown`, `test_timeout_unknown`, `test_tool_missing_icd_present_unknown`, `test_tool_missing_no_icd_missing`, `test_empty_output_unknown`. Use a trimmed real `vulkaninfo --summary` `Devices:` section as test input.
- [ ] **Step 2:** Run `PYTHONPATH=src python3 -m unittest tests.test_vulkan -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `check_vulkan`.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: Vulkan check`.

### Task 7: 32-bit support check

**Files:**
- Create: `src/lgsh/scanner/checks/multiarch.py`
- Test: `tests/test_multiarch.py`

**Interfaces:**
- Consumes: `PackageIndex`, `parse_gpus`.
- Produces: `check_multiarch(s: Snapshot) -> Item` (id `"multiarch_32bit"`, title `"32-bit support"`, required, details `{"i386_enabled": bool | None, "needed": [pkg...], "missing": [pkg...], "notes": [...]}`).

Rules:
1. `foreign_arch` not ok => unknown. `i386` not in its lines => missing "Not enabled. Steam and many games need it."
2. Needed packages: `mesa-vulkan-drivers:i386` if any GPU is amd or intel; for NVIDIA, find installed `libnvidia-gl-<N>` (non-i386 arch) and need `libnvidia-gl-<N>:i386`. NVIDIA with no `libnvidia-gl-*` installed adds a note ("NVIDIA driver not installed yet") and needs nothing for it. Never add the Mesa package for an NVIDIA-only PC.
3. GPUs or dpkg unreadable => unknown "Enabled, but the 32-bit graphics drivers couldn't be checked."
4. Any needed package absent => missing "Enabled, but the 32-bit graphics driver is missing (<pkg>)."; else ok "Enabled".

- [ ] **Step 1: Write failing tests:** `test_i386_off_missing`, `test_intel_needs_mesa_i386`, `test_nvidia_only_never_needs_mesa` (fixture `nvidia_proprietary` with `libnvidia-gl-560:amd64` installed and `:i386` absent => missing naming `libnvidia-gl-560:i386`, and `"mesa-vulkan-drivers:i386" not in details["needed"]`), `test_hybrid_needs_both`, `test_all_present_ok`, `test_dpkg_unreadable_unknown`.
- [ ] **Step 2:** Run `PYTHONPATH=src python3 -m unittest tests.test_multiarch -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `check_multiarch`.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: 32-bit support check`.

### Task 8: Steam and Heroic checks

**Files:**
- Create: `src/lgsh/scanner/checks/launchers.py`, fixtures `amd_snap_steam.json`, `mint22_flatpak_steam.json`
- Test: `tests/test_launchers.py`

**Interfaces:**
- Consumes: `PackageIndex`, `parse_snaps`, `parse_flatpaks`.
- Produces:
  - `steam_installs(s: Snapshot) -> list[str] | None` returning any of `"deb"`, `"snap"`, `"flatpak"`; None if dpkg unreadable, or snap/flatpak returned `None`, and nothing was found
  - `heroic_installs(s: Snapshot) -> list[str] | None` (`"deb"`, `"flatpak"`), same None rule
  - `check_steam(s) -> Item` (id `"steam"`, required, details `{"installs": [...]}`)
  - `check_heroic(s) -> Item` (id `"heroic"`, not required, details `{"installs": [...]}`)

Rules: Steam deb = any of `steam-installer`, `steam-launcher`, `steam` installed; Snap = `steam` in snaps; Flatpak = `com.valvesoftware.Steam`. Deb present => ok (even if others too; list all in details). Only Snap/Flatpak => warning "Installed as a Snap, which often breaks games. The regular version is recommended." (Flatpak: "Installed as a Flatpak. The regular version is recommended."). None and all sources answered => missing "Not installed. The main store and launcher for most games." None and a source failed => unknown.
Heroic: deb `heroic` or Flatpak `com.heroicgameslauncher.hgl` => ok. None found but `heroic_config` listing exists => unknown "Heroic settings found, but no installed package. It may be an AppImage, which this check can't see." Else missing "Not installed. Plays your Epic and GOG games." (or unknown if a source failed).

- [ ] **Step 1: Write failing tests:** `test_steam_deb_ok`, `test_steam_deb_and_snap_ok_lists_both`, `test_steam_snap_only_warning`, `test_steam_flatpak_only_warning`, `test_steam_none_missing`, `test_steam_flatpak_tool_failed_unknown`, `test_heroic_flatpak_ok`, `test_heroic_appimage_config_unknown`, `test_heroic_none_missing`.
- [ ] **Step 2:** Run `PYTHONPATH=src python3 -m unittest tests.test_launchers -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `launchers.py`; write the two fixtures with provenance.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: Steam and Heroic checks`.

### Task 9: GE-Proton, MangoHud and GameMode checks

**Files:**
- Create: `src/lgsh/scanner/checks/extras.py`
- Test: `tests/test_extras.py`

**Interfaces:**
- Consumes: `steam_installs`, `heroic_installs`, `PackageIndex`, `parse_flatpaks`.
- Produces: `check_ge_proton(s) -> Item` (id `"ge_proton"`, details `{"per_launcher": {"steam": {"versions": [...], "status": ...}, "heroic": {...}}}`), `check_mangohud(s) -> Item`, `check_gamemode(s) -> Item`. None required.

GE-Proton folders per install type: Steam deb => `steam_root_compat`, `steam_share_compat`; Steam Flatpak => `steam_flatpak_compat`; Steam Snap => `steam_snap_compat`; Heroic deb => `heroic_proton`; Heroic Flatpak => `heroic_flatpak_proton`. Per launcher: entries starting `GE-Proton` => ok with versions; all listings `absent` or without GE-Proton entries => missing; any `os_error` and nothing found => unknown. Overall: no launcher installed => not_applicable; launcher detection None => unknown; else ok if any launcher ok, otherwise `worst` of launchers. Missing summary: "Not installed. Extra fixes that help some games run."
MangoHud: deb `mangohud` or Flatpak `org.freedesktop.Platform.VulkanLayer.MangoHud` => ok; missing "Not installed. Shows FPS and temperatures in game."; unknown if dpkg unreadable.
GameMode: deb `gamemode` => ok; missing "Not installed. Lets games ask for full CPU speed."; unknown if dpkg unreadable.

- [ ] **Step 1: Write failing tests:** `test_ge_proton_no_launchers_not_applicable`, `test_ge_proton_steam_never_opened_missing` (Steam deb, both compat listings `absent`), `test_ge_proton_found_lists_versions` (`["GE-Proton9-20", "GE-Proton10-4"]`), `test_ge_proton_permission_error_unknown`, `test_ge_proton_heroic_flatpak_path`, `test_mangohud_flatpak_layer_ok`, `test_mangohud_missing`, `test_gamemode_dpkg_unreadable_unknown`.
- [ ] **Step 2:** Run `PYTHONPATH=src python3 -m unittest tests.test_extras -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `extras.py`.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: GE-Proton, MangoHud and GameMode checks`.

### Task 10: Scan orchestration and atomic results file

**Files:**
- Create: `src/lgsh/scanner/scan.py`, `src/lgsh/scanner/storage.py`
- Test: `tests/test_scan.py`, `tests/test_storage.py`

**Interfaces:**
- Consumes: all `check_*` functions, `ScanResult`, `__version__`.
- Produces:
  - `ALL_CHECKS: list[tuple[str, str, bool, Callable[[Snapshot], Item]]]` (id, title, required, fn) in order `distro, gpu, gpu_driver, vulkan, multiarch_32bit, steam, heroic, ge_proton, mangohud, gamemode`
  - `run_scan(s: Snapshot, now: datetime | None = None) -> ScanResult`; a check that raises becomes `Item(id, title, UNKNOWN, required, "The scanner hit an internal error on this check.", details={"error": repr(exc)})`
  - `default_results_path(env: Mapping[str, str] = os.environ, home: Path | None = None) -> Path`
  - `write_json_atomic(path: Path, data: dict) -> None`: creates parent folders, writes a temp file in the same folder, `fsync`, `os.replace`; on any error removes the temp file and re-raises

- [ ] **Step 1: Write failing tests:** `test_all_items_present_in_order` (fixture `intel_ubuntu2604` => ids in the order above), `test_check_exception_becomes_unknown` (patch one check to raise; others still present and correct), `test_intel_fixture_statuses` (gpu_driver ok, vulkan unknown, multiarch_32bit missing, steam warning, heroic missing, ge_proton missing or unknown per fixture dirs, mangohud missing, gamemode missing), `test_every_item_has_evidence` (every fixture: each non-`not_applicable` item has `len(evidence) >= 1`), `test_results_path_xdg` (`XDG_STATE_HOME=/x` => `/x/lgsh/last-scan.json`), `test_results_path_default`, `test_write_atomic_roundtrip`, `test_write_failure_leaves_no_file` (patch `os.replace` to raise `OSError`; target absent and no `*.tmp` left in folder).
- [ ] **Step 2:** Run `PYTHONPATH=src python3 -m unittest tests.test_scan tests.test_storage -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `scan.py` and `storage.py`.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: scan orchestration and atomic results file`.

### Task 11: Terminal report

**Files:**
- Create: `src/lgsh/scanner/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `ScanResult`, `Item`, `Status`.
- Produces: `render_text(result: ScanResult) -> str`.

Layout: `Your PC` header line built from `distro.details["pretty_name"]` (fallback "Unknown system") and each GPU as `<name> (driver: <driver or none>)`, joined with ` + `, separated from the distro by ` · `. Then sections, each only if non-empty, in order: `Ready` (ok), `Needs attention` (warning), `Required installations` (missing and required), `Optional` (missing and not required), `Couldn't check` (unknown). Items `distro` and `gpu` appear in the header only, except when their status is warning or unknown, when they also appear in the matching section. `not_applicable` never appears. Each line: two-space indent, title padded to 18 columns, then summary. No emoji; no trailing whitespace. If nothing is missing or warning, end with the line `Everything needed for gaming is in place.`

- [ ] **Step 1: Write failing tests:** `test_intel_fixture_matches_expected` (compare to `tests/fixtures/intel_ubuntu2604.expected.txt`, written in this step to match the spec's sample layout), `test_section_order`, `test_empty_sections_omitted`, `test_not_applicable_hidden`, `test_required_vs_optional_split`, `test_no_emoji_or_exclamation` (render every fixture; assert no char with `ord > 0x2FFF` except `·`, and no `!`), `test_all_ok_message`.
- [ ] **Step 2:** Run `PYTHONPATH=src python3 -m unittest tests.test_report -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `render_text`.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: terminal report`.

### Task 12: Command-line entry point, end-to-end tests, real-machine run

**Files:**
- Create: `src/lgsh/scanner/cli.py`, `src/lgsh/scanner/__main__.py` (calls `cli.main`), fixture `tools_missing.json`
- Modify: `README.md` (usage and capture instructions)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `collect`, `load_snapshot`, `save_capture`, `run_scan`, `render_text`, `default_results_path`, `write_json_atomic`.
- Produces: `main(argv: list[str] | None = None, *, collect_fn=collect, euid_fn=os.geteuid) -> int`

Flags: `--json` (print the JSON to stdout instead of the text report), `--output PATH` (results file location), `--capture FOLDER` (also save the snapshot there), `--from-capture FILE` (scan a saved snapshot instead of this PC; still writes results unless `--output -`, where `-` means don't save). Exit codes: 0 scan done and saved; 1 scan done but results couldn't be saved (or capture file already exists, message "A capture already exists in <folder>. Choose an empty folder."); 2 refused to run as root.

- [ ] **Step 1: Write failing tests:** `test_refuses_root` (`euid_fn=lambda: 0` => exit 2, message "Run this as your normal user, without sudo.", `collect_fn` not called), `test_from_capture_prints_report` (fixture path, `--output` to temp file => exit 0, stdout contains `Required installations`, file has `schema_version == 1`), `test_json_flag_outputs_valid_json`, `test_save_failure_exit_code` (output path inside a read-only temp dir => exit 1, report still printed, stderr starts `Couldn't save results:`), `test_capture_refuses_existing` (exit 1, existing file unchanged), `test_tools_missing_fixture_no_crash` (every item `unknown` or `not_applicable` except distro).
- [ ] **Step 2:** Run `PYTHONPATH=src python3 -m unittest tests.test_cli -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `cli.py` with `argparse`, and `__main__.py`.
- [ ] **Step 4:** Run the whole suite: `PYTHONPATH=src python3 -m unittest discover -s tests -v`. Expected: all PASS.
- [ ] **Step 5:** Commit `feat: lgsh-scan command line`.
- [ ] **Step 6: Real-machine run (Arefin, on Ubuntu 26.04 Intel PC):** `PYTHONPATH=src python3 -m lgsh.scanner --capture ~/lgsh-capture`. Expected: report prints in a few seconds; every line matches what is actually installed (check each one by hand); `~/.local/state/lgsh/last-scan.json` exists. Copy `~/lgsh-capture/lgsh-capture.json` to `tests/fixtures/intel_ubuntu2604_real.json`, set its provenance to "captured on Arefin's PC", add `test_real_intel_capture_statuses` to `tests/test_scan.py` asserting the statuses Arefin confirmed, and commit `test: real capture from Ubuntu 26.04 Intel PC`. Any line that is wrong is a bug: add a failing test from the capture, fix, re-run.
