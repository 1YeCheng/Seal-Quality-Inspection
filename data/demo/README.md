# Demo Dataset

This folder contains a small curated dataset for quickly testing the inspection pipeline without using the full local dataset.

## Structure

```text
data/demo/
|-- paired_2D/
`-- paired_IR/
```

Each 2D image has a corresponding infrared image with a nearby timestamp. The default pairing tolerance is configured in `config.json` as `pairing.max_time_diff_ms`.

## Run

From the project root:

```bash
python main.py --batch --folder-2d data/demo/paired_2D --folder-ir data/demo/paired_IR --no-save
```

Expected summary:

```text
Detected 5 bag records
BAG0001: 2D=OK, IR=OK, FINAL=OK
BAG0002: 2D=NG, IR=OK, FINAL=NG
BAG0003: 2D=NG, IR=NG, FINAL=NG
BAG0004: 2D=OK, IR=OK, FINAL=OK
BAG0005: 2D=OK, IR=NG, FINAL=NG
```

The demo covers normal samples, visible-light defects, infrared defects, and combined NG cases.
