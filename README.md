# Plants vs. Zombies: Replanted – PS4 Save Editor

**CUSA55613 · v2.6 · Max Sun + Endless Streaks + Zen Garden Preview**

A Windows GUI save editor for the PS4 version of **Plants vs. Zombies: Replanted**.

## Features

### Profile (`0.pb.dat`)
- Verified version-8 profile parser
- Raw-DEFLATE decompress/edit/recompress
- Coins and Adventure/R.I.P. progression
- Mode and unlock flags
- 80 purchase records
- 100 challenge records
- 37 in-profile achievement flags
- Trophy-prep counters / best records
- Zen Garden editing and live plant preview
- Automatic backups and re-parse validation

### In-game saves (`.ig.dat`)
- Detects populated AcQS / SaveHeader records
- Lists Level ID, save version, P1/P2 Sun, streak/stage and payload size
- Edit Player 1 and Player 2 Sun
- Max Sun preset: **9999**
- Edit live `Challenge.mSurvivalStage`
- I, Zombie Endless streak preset: **10** (Level ID 115)
- Vasebreaker Endless streak preset: **15** (Level ID 105)
- Survival Day Endless preset: **20 completed stages / at least 40 flags** (Level ID 95)
- Raw-DEFLATE recompression with validation

### Trophy-prep records
- Tree of Wisdom: 100
- Vasebreaker Endless best record: 15
- I, Zombie Endless best record: 10
- Survival Day Endless best record: 40 flags

## Running from source

Requirements:
- Windows
- Python 3
- Tkinter (included with standard Windows Python installs)

Double-click:

`Launch Editor.vbs`

This launches the `.pyw` GUI without a command window. No third-party Python modules are required at runtime.

## Building the Windows EXE

The repository includes a GitHub Actions workflow that builds a no-console Windows executable using PyInstaller. Open the **Actions** tab and run/download the Windows build artifact, or push changes to trigger the workflow.

## Save safety

- Keep a full PS4 save backup before experimenting.
- `0.pb.dat` and `.ig.dat` are edited separately.
- The editor preserves the first automatic `.bak` file.
- `profile_data.dat` / PendingAchievements is not modified.
- Zen Garden editing modifies existing potted-plant records only; it does not fabricate new records.

## Verified CUSA55613 mappings

The supplied samples were used to verify:
- I, Zombie Endless (Level ID 115): live Sun and current streak
- Vasebreaker Endless (Level ID 105): current streak
- Survival Day Endless (Level ID 95): completed survival stage
- Replanted saves containing Sun values up to **9999**

## Version

Current source: **v2.6**
