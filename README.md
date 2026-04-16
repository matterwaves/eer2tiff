# eer2tiff

Convert EER cryo-EM data from an EMPIAR download into TIFF outputs.

## Overview

This repository provides `eer2tiff.py`, a command-line script for processing raw EMPIAR data folders and writing TIFF outputs to a user-specified output directory.

## Requirements

The tested conda environment is provided in `environment.yml`.

Create it with:

```bash
conda env create -f environment.yml
conda activate eer2tiff
```

A pip fallback is also provided:

```bash
python -m venv testenv
source testenv/bin/activate
pip install -r requirements.txt
```

## Input data

Download the raw dataset separately from EMPIAR.

Example input folder:

`/path/to/empiar/data_ON/H2_on`

## Usage

Example:

```bash
python3 eer2tiff.py \
  --folder /path/to/empiar/data_ON/H2_on \
  --out /path/where/outputs/should/go/H2_on \
  --frame_dose 1
```

Show all options:

```bash
python3 eer2tiff.py --help
```

## Arguments

- `--folder`: experiment folder containing the input data
- `--out`: output directory
- `--frame_dose`: target dose per rendered frame in e/A^2
- `--total_dose`: target total dose in e/A^2
- `--relion_func`: full path to relion_convert_to_tiff executable; uses `which relion_convert_to_tiff` if omitted
- `--verbose`: enable verbose output

## Outputs

`eer2tiff.py` writes TIFF outputs to the directory given by `--out`. In the example above, the outputs will go in the folder `/path/where/outputs/should/go/H2_on`. There will be a subfolder called `tif_1.0e` which contains in its name the per-frame dose used. If total dose is provided, that will also be added to the folder name (e.g. `tif_1.0e_50.0tot`). Within that folder, a file `eer2tiff_params.json` will be created with the input arguments. That folder will also contain all the converted files, identified in `/path/to/empiar/data_ON/H2_on/eer/*.eer` and written with the same base name and new extension `.tif`.

## Notes

- This repository does not include EMPIAR raw data.
- Users must download the relevant dataset separately.
- The tested software environment is described in `environment.yml`.

## Citation

If you use this software, please cite the GitHub/Zenodo release associated with the version you used.

See `CITATION.cff` for citation metadata.

## License

This project is licensed under the terms of the license in `LICENSE`.