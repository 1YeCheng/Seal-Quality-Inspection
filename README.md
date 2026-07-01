# Seal Quality Inspection System

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-Image%20Processing-5C3EE8?logo=opencv&logoColor=white)
![PyQt5](https://img.shields.io/badge/PyQt5-Desktop%20UI-41CD52)
![Inputs](https://img.shields.io/badge/Inputs-2D%20%2B%20Infrared-0F766E)
![Inspection](https://img.shields.io/badge/Inspection-Batch%20%26%20Real--time-2563EB)
![Traceability](https://img.shields.io/badge/Traceability-JSON%20%2B%20CSV%20Logs-7C3AED)

This project implements an industrial vision prototype for automatic heat-seal quality inspection. The system combines 2D visible-light images and infrared images to pair corresponding samples, locate seal regions, extract quality-related features, classify each package as OK or NG, and save traceable inspection records.

The project is structured as a practical image-processing system. It includes a PyQt5 desktop interface, configurable inspection thresholds, batch processing, NG image archiving, CSV/JSON logging, and simulated IO signals for production-line integration.

## Preview

![Desktop UI](docs/images/ui_runtime_detection.png)

The desktop interface supports real-time inspection, 2D/IR image review, feature tables, package-level decisions, local logs, and NG record browsing.

## Technical Route

The inspection pipeline first filters 2D and IR image streams by file prefix and extension. Timestamps are parsed from file names. If a timestamp cannot be parsed, file modification time is used as a fallback. The matcher then pairs the nearest 2D and IR images within a configurable time window.

For visible-light inspection, the system first localises the package body and seal region. It supports fixed ROI settings, resolution-specific ROI presets, and automatic ROI search. Within the selected seal region, the detector converts the image to HSV space. It then extracts high-value and low-saturation silver-edge regions, removes small noise by morphological filtering, and measures defect area, maximum connected-component area, component count, and defect ratio. A separate foreign-region mask captures abnormal local variation inside the ROI.

For infrared inspection, the system crops the configured seal ROI and segments the hot seal band. Segmentation can use pseudo-colour HSV ranges, Otsu thresholding, or a fixed threshold. The largest valid contour is measured by width, height, area, angle, aspect ratio, and boundary roughness. Pixel intensity is mapped to an estimated temperature range, which supports reporting of mean temperature and temperature uniformity.

The final decision is made at package level. A sample is marked OK only when image pairing succeeds and both visible-light and infrared inspections pass their rule sets. Each inspection result is saved with annotated images, structured JSON, CSV logs, NG image copies, and simulated IO states.

## Technical Features

- **Multimodal image pairing**: 2D and IR images are matched by prefix, timestamp, file-extension filters, and a configurable maximum time difference.
- **Adaptive ROI handling**: seal regions can be set manually, selected from resolution-specific presets, or located automatically using package-body cues.
- **Visible-light defect detection**: silver-edge defects are extracted in HSV space and quantified by area, ratio, component count, and maximum component size.
- **Foreign-region analysis**: abnormal local variation within the visible-light ROI is measured separately from silver-edge regions.
- **Infrared seal segmentation**: the IR branch supports pseudo-colour HSV segmentation, Otsu thresholding, and fixed-threshold segmentation.
- **Geometric quality measurement**: detected seal contours are checked by width, height, area, angle, aspect ratio, and boundary roughness.
- **Thermal feature estimation**: grayscale intensity is mapped to a configurable temperature range to estimate mean temperature and temperature uniformity.
- **Rule-based decision fusion**: package-level OK/NG decisions combine pair status, visible-light inspection, infrared inspection, and rule-level failure reasons.
- **Operational traceability**: the system saves annotated images, raw NG images, per-package JSON files, CSV inspection logs, and simulated IO states.
- **Desktop and batch execution**: the same inspection service supports PyQt5 review, folder polling, batch evaluation, and simulated production-line IO.

## System Workflow

```text
2D images + IR images
        |
        v
Timestamp parsing and pair matching
        |
        v
ROI localisation and feature extraction
        |
        v
2D inspection + IR inspection
        |
        v
Package-level OK/NG decision
        |
        v
Annotated images, JSON records, CSV logs, and IO status
```

## Repository Structure

```text
.
|-- main.py                    # Command-line entry point and UI launcher
|-- config.json                # Inspection thresholds, ROI settings, paths, and runtime options
|-- requirements.txt           # Python dependencies
|-- modules/                   # Core inspection logic
|   |-- detector_2d.py          # Visible-light inspection
|   |-- detector_ir.py          # Infrared inspection
|   |-- pair_matcher.py         # 2D/IR timestamp pairing
|   |-- inspection_service.py   # End-to-end inspection pipeline
|   |-- logger.py               # CSV/JSON/result saving
|   `-- ...
|-- ui/                        # PyQt5 desktop interface
|-- data/                      # Local inspection images and a small public demo dataset
`-- result/                    # Generated inspection outputs
```

## Installation

Python 3.10 or newer is recommended.

```bash
pip install -r requirements.txt
```

The main dependencies are:

- OpenCV
- NumPy
- Pandas
- PyQt5

## Run the Desktop UI

```bash
python main.py
```

The UI supports image inspection, folder polling, result visualisation, threshold configuration, log viewing, and NG record browsing.

## Run Batch Inspection

The command below assumes that paired image folders are available locally:

```bash
python main.py --batch --folder-2d data/paired_2D --folder-ir data/paired_IR
```

This repository includes a small curated demo dataset under:

```text
data/demo/paired_2D
data/demo/paired_IR
```

It can be tested with:

```bash
python main.py --batch --folder-2d data/demo/paired_2D --folder-ir data/demo/paired_IR
```

To test the algorithm without writing result files:

```bash
python main.py --batch --no-save
```

Example output:

```text
Detected 75 bag records
BAG0001: 2D=NG, IR=NG, FINAL=NG, ...
BAG0004: 2D=OK, IR=OK, FINAL=OK, OK
```

## Image Naming Convention

The recommended image naming format is:

```text
2D_20240301_153012_125.jpg
IR_20240301_153012_180.jpg
```

The system parses timestamps in the `YYYYMMDD_HHMMSS_mmm` format. If no timestamp is found in the file name, it falls back to the file modification time.

## Configuration

Most inspection parameters are stored in `config.json`, including:

- 2D and IR ROI settings
- segmentation mode and thresholds
- geometric and temperature acceptance ranges
- maximum allowed 2D silver-edge area and ratio
- pairing time tolerance
- output directories
- simulated IO signal names and reject duration

This allows the system to be recalibrated for different image resolutions, lighting conditions, seal materials, and production requirements.

## Outputs

When saving is enabled, the system generates:

- annotated inspection images
- NG raw images
- per-package JSON result files
- CSV inspection logs
- simulated IO states

Only the curated demo images and representative result examples are intended for the public repository; full local datasets and generated inspection outputs should remain excluded.

Example inspection results:

| Visible-light inspection | Infrared inspection |
| --- | --- |
| ![2D detection example](docs/images/2d_detection_example.jpg) | ![IR detection example](docs/images/ir_detection_example.jpg) |

NG traceability and log review:

| NG browser | Log window |
| --- | --- |
| ![NG trace example](docs/images/ng_trace_example.png) | ![Log window](docs/images/log_review_window.png) |

## Data Availability

The full local dataset and generated inspection results are not intended to be committed to the public repository. The `.gitignore` file excludes most of `data/` and all of `result/` by default, while allowing the small public demo dataset under `data/demo/`.

## Technical Scope

The implementation covers classical computer vision for industrial inspection, multimodal image matching, rule-based decision fusion, configurable processing pipelines, PyQt5 desktop UI development, and traceable inspection logging.

## Notes

The system is a research and engineering prototype. Production deployment would require hardware camera integration, real IO/PLC communication, larger-scale validation, and further calibration on more diverse defect samples.
