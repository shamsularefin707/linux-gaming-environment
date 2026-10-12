# Scanner design (build step 1)

Date: 2026-10-12 · Project: Linux Gaming Setup Hub (working title) · Status: approved by Arefin 2026-10-12

## Why this exists

Setting up gaming on Ubuntu means hunting down every piece separately: the right driver, Vulkan, 32-bit support, the right kind of Steam, Heroic, GE-Proton, MangoHud, GameMode. Arefin found that "too much hassle". The scanner is the first piece of the fix: one command that looks at the whole PC at once and says, in plain words, what is already there, what is missing, and what it could not check. Later steps (planner, installer, GUI) read its results so they only install what is actually missing.

## What Arefin said it must get right

1. **Never lose data.** The scanner must not be able to damage anything on the PC.
2. **No false flags and no misses.** It must not claim something is missing when it is there, or call something fine when it is not.
3. **A clean, friendly interface with no AI slop.** Plain wording, nothing decorative, nothing that sounds like filler.

## Goals

- One command, run as a normal user, that checks everything in the list below in a few seconds.
- A readable report in the terminal.
- A machine-readable JSON file of the same results for the planner, installer and GUI to consume.
- Every result shows how it was decided (which command or file), so a wrong result can be traced.

## Non-goals (for this step)

- Installing, fixing or configuring anything. That is the installer (build step 3).
- Deciding *what* to install or producing install commands. That is the planner (step 2).
- The GUI (step 4).
- Crash diagnosis (v2), Lutris, mods, peripherals (v3+).

## Anti-goals (would be a failure even if it "works")

- Writing anywhere other than its own output file, running anything with `sudo`/`pkexec`, or running any command that can change the system.
- Guessing. If a check cannot be sure, it must say "couldn't check" and why, never "missing".
- Report text that is chatty, emoji-heavy, or padded ("Great news! 🎉 Your system is looking awesome!").
- Anything touching anti-cheat or DRM (out of scope forever).

## Constraints

- Python 3, **standard library only** (runs on a fresh Ubuntu without pip installs).
- Runs without root. Supported: **Ubuntu 24.04 and newer** and **Linux Mint 22 and newer** (Mint 22 is based on Ubuntu 24.04). Other Ubuntu-based distros (Pop!_OS, Zorin, elementary: `ID_LIKE=ubuntu`) are reported as unsupported, and all checks still run. *(Claude's call)*
- Arefin's test PC: **Ubuntu 26.04, Intel Iris integrated graphics**. AMD and NVIDIA must be tested with saved command outputs (fixtures) and later on VMs/real machines (build step 5).
- Scanner, planner and installer stay separate from the UI and runnable from the command line.

## Decisions already made

| Decision | Choice | Who |
|---|---|---|
| Scanner never changes the system | Read-only | Project rule |
| Intel GPUs | **Recognised and reported** in v1 (name, driver, Vulkan). Intel-specific installs stay v3. | Arefin |
| How installs get permission (step 3) | **Both**: report shows the exact commands; an *Install now* button uses Ubuntu's own password prompt (pkexec/polkit, app never sees the password) and a *Copy commands* button for people who prefer the terminal. | Arefin |
| Report ending | "Required installations" list, then *Install now* / *Later*. In step 1 the scanner just ends with the list; the buttons get wired in step 3. *Later* keeps the saved results. | Arefin |
| NVIDIA "set up properly" | Proprietary driver installed **and in use**, not just installed | Claude's call, Arefin agreed |
| Required vs optional | **Split.** Required: graphics driver, Vulkan, 32-bit support, Steam. Optional: Heroic, GE-Proton, MangoHud, GameMode. The later "Ask" step can promote optional items for a given person. | Arefin |
| Steam as Snap or Flatpak | "Have it, but not the recommended kind" (warning), not missing | Claude's call, Arefin agreed |

## What it checks

Each check produces one **item** with a status:

- `ok`: present and set up correctly
- `warning`: present but not in the recommended form (e.g. Snap Steam, old `radeon` driver), **or present but not working** (see below)
- `missing`: confirmed absent
- `unknown`: could not be checked (shown to the user as "Couldn't check", with the reason)
- `not_applicable`: doesn't apply on this PC (e.g. NVIDIA driver check when there is no NVIDIA card)

**Present but broken is `warning`, never `unknown` or `missing`.** *(Claude's call)* Examples: NVIDIA proprietary driver package installed but `nouveau` (or nothing) is in use, which usually means a restart is pending or Secure Boot blocked the module; `nvidia-smi` says it can't talk to the driver; `vulkaninfo` runs but finds only the `llvmpipe` software renderer; `vulkaninfo` fails while a GPU driver is in use. The summary says what is wrong and the likely cause ("Installed, but not active yet. A restart is usually needed."). This keeps real breakage out of "Couldn't check", and stops the planner from reinstalling something that is already there.

The rule that protects against false flags: **`missing` requires positive evidence of absence** (e.g. `dpkg-query` ran successfully and says the package isn't installed). If the tool that would answer the question is absent, errors, or times out, the result is `unknown`.

| Item | How (suggested source of truth) | Notes |
|---|---|---|
| Distro and version | `/etc/os-release` (`ID`, `VERSION_ID`, `ID_LIKE`, `UBUNTU_CODENAME`) | Supported: `ubuntu`, `linuxmint`. Anything else: report it as unsupported but still run the other checks. Mint maps to its Ubuntu base via `UBUNTU_CODENAME`. |
| Graphics card(s) | `lspci -nnk`, display classes 0300/0302/0380; vendor IDs `1002` AMD, `10de` NVIDIA, `8086` Intel | Report every GPU (laptops can have two). |
| Graphics driver in use | `Kernel driver in use` from `lspci -k`; NVIDIA version from `nvidia-smi` or `/proc/driver/nvidia/version` if available | NVIDIA: `nvidia` = ok, `nouveau` = warning, none = missing. AMD: `amdgpu` = ok, `radeon` = warning. Intel: `i915`/`xe` = ok. |
| Vulkan | `vulkaninfo --summary` when installed; otherwise ICD files in `/usr/share/vulkan/icd.d/` | If `vulkaninfo` isn't installed and ICD files exist, report "likely ok" as `unknown` with that note, not `ok`. |
| 32-bit support | `dpkg --print-foreign-architectures` contains `i386`; the 32-bit graphics driver for **each** GPU in use: `mesa-vulkan-drivers:i386` for AMD/Intel, `libnvidia-gl-<version>:i386` for NVIDIA, with `<version>` matching the installed NVIDIA driver | One item with sub-details. i386 off = `missing`. i386 on but a needed 32-bit driver absent = `missing`, naming which driver. Never check for the Mesa package on an NVIDIA-only PC. *(Claude's call)* |
| Steam | deb: `dpkg-query` for `steam-installer`, `steam-launcher`, `steam`; Snap: `snap list steam`; Flatpak: `com.valvesoftware.Steam` | deb = ok; Snap/Flatpak only = warning; none = missing. Report every install found. |
| Heroic | Flatpak `com.heroicgameslauncher.hgl`; deb `heroic` | Flatpak or deb = ok. |
| GE-Proton | `GE-Proton*` folders in Steam's `compatibilitytools.d` (native: `~/.steam/root/` and `~/.local/share/Steam/`; Flatpak: `~/.var/app/com.valvesoftware.Steam/data/Steam/`) and Heroic's `~/.config/heroic/tools/proton/` (Flatpak Heroic: under `~/.var/app/com.heroicgameslauncher.hgl/config/heroic/`) | One item, with a per-launcher list in `details`. Only installed launchers are checked. No launcher installed = `not_applicable` (hidden from the report). Launcher installed but folder absent (e.g. Steam never opened) = `missing` for that launcher, since the folder not existing is positive evidence. *(Claude's call)* |
| MangoHud | deb `mangohud`; Flatpak `org.freedesktop.Platform.VulkanLayer.MangoHud` | |
| GameMode | deb `gamemode` | |

## Safety rules (how "never lose data" is enforced)

- Commands come from a fixed allowlist of read-only programs (`lspci`, `vulkaninfo`, `dpkg-query`, `dpkg`, `snap`, `flatpak`, `nvidia-smi`). Arguments are fixed lists, never a shell string (`shell=False`).
- Every command has a timeout; a timeout gives `unknown`, never a crash.
- One check failing never stops the others.
- The only file written is the scanner's own results file, written atomically (write to a temp file, then rename) so a crash never leaves a half-written file.
- No network access.

## Output

**Terminal report** (default). Plain sections, no emoji, one line per item:

```
Your PC
  Ubuntu 26.04 · Intel Iris Xe Graphics (driver: i915)

Ready
  Graphics driver   Working (i915)
  Vulkan            Working (Intel Mesa driver)

Needs attention
  Steam             Installed as a Snap, which often breaks games. The regular version is recommended.

Required installations
  32-bit support    Not enabled. Steam and many games need it.

Optional
  Heroic            Not installed. Plays your Epic and GOG games.
  MangoHud          Not installed. Shows FPS and temperatures in game.

Couldn't check
  GameMode          The package list couldn't be read.
```

Sections appear only when they have items, in this order: Ready, Needs attention (`warning`), Required installations (`missing` + required), Optional (`missing` + optional), Couldn't check (`unknown`). `not_applicable` items are hidden from the terminal report but kept in the JSON. *(Claude's call)*

Each "missing" line says what the thing is for in under ten words. Warnings say what is wrong and why it matters ("Steam is the Snap version, which often breaks games").

**JSON file** (always written; also printable with a `--json` flag). Includes a `schema_version`, the scan time, scanner version, and for every item: `id`, `status`, `required` (true/false), a short human `summary`, `details` (e.g. versions found, install method), and `evidence` (the command or file used, and a trimmed copy of its output). Default location: `~/.local/state/<app-name>/last-scan.json`.

## Testing

- Each check is a small function that takes command outputs as input, so it can be unit-tested with saved outputs without running the real commands.
- A `--capture <folder>` option saves the raw output of every command the scanner runs, so Arefin, friends or testers on other hardware can send real fixtures. *(Claude's call)*
- Fixtures: real outputs captured from Arefin's Intel PC, plus samples for AMD, NVIDIA (proprietary and nouveau), hybrid laptops, Snap Steam, Flatpak Steam, Mint, and "tool not installed" cases. Until real captures arrive, AMD/NVIDIA samples come from public sources (bug reports, forum posts) and are labelled with where they came from; hand-written ones are labelled as such. Real captures replace them as they come in, and step 5 confirms on real hardware.
- Every check has a test that a missing or failing tool gives `unknown`, not `missing`.
- A manual run on Arefin's Ubuntu 26.04 machine before the step is called done.

## Left to the builder

- Module and file layout, function names, CLI flag names beyond `--json`.
- Exact parsing details for each command.
- Exact command timeouts.
- The report's exact wording, within the tone rules above.

## Still open (not blocking this step)

- Project name (use a placeholder package name until decided).
- Packaging (.deb / Flatpak / both) and license.
