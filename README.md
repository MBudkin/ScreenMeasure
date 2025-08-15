# ScreenMeasure — calibration and measuring distances on an image

**ScreenMeasure** — lightweight desktop utility for Windows that allows you to calibrate scale using a known length and accurately measure segments and polylines on any image/screenshot. All measurements remain on the picture with a length label.

## Why
- Quick measurements on drawings, diagrams, screenshots, photos.
- Matching real object sizes using a reference (ruler in photo, known span, etc.).
- Preparing visual illustrations: export image with applied measurements.

## How it works
1. **Open an image** (`Ctrl+O`) or **paste from clipboard** (`Ctrl+V`).
2. **Calibration** (`C`): click two points with a known real distance → enter length and units (mm/cm/m/inches, etc.).  
   The scale will be saved; all existing measurements will be recalculated automatically.
3. **Line measurement** (`L`): click two points — a line with a length label will appear.
4. **Polyline measurement** (`P`): click several points → **RMB** to finish. Length is labeled in the middle of the path.
5. **Export**:  
   – **CSV** with the list of measurements (`Ctrl+E`)  
   – **Image with measurements** (*Export Annotated Image* button).

## Features
- Persistent objects on the image: **lines** and **polylines** with automatic length labels.  
- Good visibility on any background: double outline (**black border + colored line**).
- **Guides** (horizontal/vertical/±45°) for aligning points:
  - Appear only in active modes (calibration/line/polyline).
  - Anchored to the last LMB point, **do not move** during pan/zoom.
  - Thin when tool is selected but points are not placed yet; **thicker** during construction.
  - Toggles: **Horizontal**, **Vertical**, **45° guides**.
- Canvas control: **zoom with wheel**, **pan** with MMB or **space + LMB**.
- Measurement history: **Undo** (last), **Delete selected**, **Clear measurements**, **Clear image + measurements**.
- Recalibration **automatically recalculates all measurements**.

## Hotkeys
| Action | Key |
|---|---|
| Paste from clipboard | `Ctrl+V` |
| Open file | `Ctrl+O` |
| Export CSV | `Ctrl+E` |
| Reset view | `R` |
| Calibration | `C` |
| Line | `L` |
| Polyline | `P` |
| Finish polyline | **RMB** |
| Undo last | `Ctrl+Z` |
| Cancel mode/clear temporary points | `Esc` |
| Pan | **MMB** or **Space + LMB** |

## Export and saving
- **CSV**: time, type, units, length, point coordinates.
- **PNG/JPG image** with applied lines, labels, and (if needed) current temporary geometry.

## System requirements
- Windows 10/11  
- Python 3.9+ and `PySide6` *(for running from source)* or ready `.exe`.

## Privacy
All operations are performed **locally**, data is not sent anywhere.

---

*If necessary, we will add hotkeys for hiding/showing guides and snapping to axes/45° while holding `Shift`.*
