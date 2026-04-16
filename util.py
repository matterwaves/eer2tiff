### THINGS TO MODIFY

# absolute path to your relion_convert_to_tiff executable
# relion_convert_to_tiff_exe = '/usr/local/relion-4.0/bin/relion_convert_to_tiff'

### ================================================================================

import os
import re
import sys
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from datetime import datetime
import tifffile # 2024.12.12
import xmltodict # 0.14.2

pixel_size = 0.94 # [A]
start_time = datetime(2025, 8, 1, 0, 0, 0, tzinfo=ZoneInfo('America/Los_Angeles'))
end_time = datetime(2125, 8, 1, 0, 0, 0, tzinfo=ZoneInfo('America/Los_Angeles'))

def get_mic_datetime(fpath, relion=False, apply_tzinfo=True):
    fname = os.path.basename(fpath)
    if relion:
        match = re.match(r'^(\d{4}-\d{2}-\d{2})_(\d{2})_(\d{2})_(\d{2})', fname)
    else:
        match = re.match(r'^(\d{4}-\d{2}-\d{2})_(\d{2})\.(\d{2})\.(\d{2})', fname)
    if not match:
        raise ValueError(f'No valid timestamp found in filename: {fname}')
    date_str, hour, minute, second = match.groups()
    dt = datetime.strptime(f'{date_str} {hour}:{minute}:{second}', '%Y-%m-%d %H:%M:%S')
    if apply_tzinfo:
        dt = dt.replace(tzinfo=ZoneInfo('America/Los_Angeles'))
    return dt

def filter_and_sort_fpaths(
    fpaths_list, 
    start_time=start_time, 
    end_time=end_time, 
    sort_func=get_mic_datetime,
):
    res = []
    for f in fpaths_list:
        try:
            dt = sort_func(f)
            if start_time <= dt <= end_time:
                res.append((dt, f))
        except ValueError as e:
            print('skipping file: {} ({})'.format(f, e))
    res.sort(key=lambda x: x[0])
    return [f for _, f in res]

def read_mdoc_param(fpath, param_str, dtype=float):
    if fpath.endswith('.mdoc') is False:
        fpath = fpath + '.mdoc' # append .mdoc extension if not present
    value = None
    with open(fpath, 'r') as f:
        for line in f:
            if line.strip().startswith(f'{param_str} ='):
                key, val = line.strip().split('=')
                if dtype == float:
                    value = float(val.strip())
                else:
                    value = val.strip()
    return value

def read_beam_current(mic_fpath):
    mdoc_path = mic_fpath.replace('/eer/', '/mdoc/') + '.mdoc'
    return read_mdoc_param(mdoc_path, 'FEGCurrent')

def get_dose_rate_eps(beam_current, feg_calib_fpath=None):
    if feg_calib_fpath is None:
        raise ValueError('feg_calib_fpath must be provided')
    with open(feg_calib_fpath, 'r') as f:
        feg_coeffs = json.load(f)
    dose_rate_eps = feg_coeffs[0] * beam_current + feg_coeffs[1]
    return dose_rate_eps

def extract_eer_items(eer_fpath, suppress_errors=True) -> dict:
    """
    Read the metadata of an EER file and output it as a dict
    """
    if suppress_errors:
        class SuppressStderr:
            def __enter__(self):
                self.stderr_fd = sys.stderr.fileno()
                self.null_fd = os.open(os.devnull, os.O_RDWR)
                self.saved_stderr = os.dup(self.stderr_fd)
                os.dup2(self.null_fd, self.stderr_fd)
            def __exit__(self, exc_type, exc_value, traceback):
                os.dup2(self.saved_stderr, self.stderr_fd)
                os.close(self.null_fd)
        with SuppressStderr():
            with tifffile.TiffFile(eer_fpath) as tif:
                tag = tif.pages[0].tags['65001']
                data = tag.value.decode('UTF-8')
    else:
        with tifffile.TiffFile(eer_fpath) as tif:
            tag = tif.pages[0].tags['65001']
            data = tag.value.decode('UTF-8')

    # convert the XML to a dict
    parsed = xmltodict.parse(data)

    # flatten the dict
    metadata = {}
    for item in parsed['metadata']['item']:

        key   = item['@name']
        value = item['#text']
        metadata[key] = value

        # write unit if it exists
        try:
            unit = item['@unit']
            metadata[f'{key}.unit'] = unit
        except:
            pass
    return metadata

def get_eer_exposure_info(eer_fpath, return_eer_dose=True):
    metadata = extract_eer_items(eer_fpath, suppress_errors=True)
    dose_pix_tot = float(metadata['totalDose']) # [e/pix]
    mean_dose_rate = float(metadata['meanDoseRate']) # [e/pix/s]
    exposure_time_s = dose_pix_tot / mean_dose_rate # [s]
    n_frames_tot = int(metadata['numberOfFrames'])
    if return_eer_dose:
        return (n_frames_tot, exposure_time_s, dose_pix_tot, mean_dose_rate)
    return (n_frames_tot, exposure_time_s)

def truncate_tiff(in_fpath, out_fpath, n):
    with tifffile.TiffFile(in_fpath) as tif:
        orig_n = len(tif.pages)
        if n > orig_n:
            raise ValueError(f'Requested {n} frames but file only has {orig_n}')
        # read only first n frames
        data = tif.asarray(key=range(n))
    # save truncated
    tifffile.imwrite(out_fpath, data)