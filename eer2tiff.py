import os
import sys
import glob
import time
import json
from subprocess import Popen, PIPE, run
import argparse
import numpy as np # 2.0.1

# import the util.py module that is in the same directory as this script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import util

def resolve_relion_func(user_path):
    if user_path is not None:
        if not os.path.isfile(user_path):
            raise FileNotFoundError('relion_convert_to_tiff executable not found: {}'.format(user_path))
        if not os.access(user_path, os.X_OK):
            raise PermissionError('relion_convert_to_tiff is not executable: {}'.format(user_path))
        return user_path
    which_result = run(
        ['which', 'relion_convert_to_tiff'],
        stdout=PIPE,
        stderr=PIPE,
        encoding='utf-8',
        text=True
    )
    if which_result.returncode != 0:
        raise FileNotFoundError(
            'could not find relion_convert_to_tiff in PATH. '
            'Please provide it explicitly with --relion_func /path/to/relion_convert_to_tiff'
        )
    relion_func = which_result.stdout.strip()
    if relion_func == '':
        raise FileNotFoundError(
            'which relion_convert_to_tiff returned an empty path. '
            'Please provide it explicitly with --relion_func /path/to/relion_convert_to_tiff'
        )
    return relion_func

def main():
    parser = argparse.ArgumentParser(
        description='convert EER files to TIF using specified dose per rendered frame and total dose'
    )
    parser.add_argument('--folder', help='experiment folder (full path)')
    parser.add_argument('--out', help='output directory (full path)')
    parser.add_argument('--frame_dose', type=float, default=1, help='target dose per rendered frame [e/A^2]')
    parser.add_argument('--total_dose', type=float, default=None, help='target total dose [e/A^2]')
    parser.add_argument(
        '--relion_func',
        default=None,
        help='full path to relion_convert_to_tiff executable; if omitted, use `which relion_convert_to_tiff`'
    )
    parser.add_argument('--verbose', action='store_true', help='enable verbose output')
    args = parser.parse_args()

    # parse args
    in_dir = args.folder
    save_dir = args.out
    target_dose_A2_renframe = args.frame_dose
    target_dose_A2_tot = args.total_dose
    relion_func = resolve_relion_func(args.relion_func)

    if args.verbose:
        print('using relion_convert_to_tiff executable: {}'.format(relion_func))

    # save params to json in save_dir
    params = {
        'folder': in_dir,
        'out': save_dir,
        'frame_dose': target_dose_A2_renframe,
        'total_dose': target_dose_A2_tot,
        'relion_func': relion_func,
    }
    os.makedirs(save_dir, exist_ok=True)
    if target_dose_A2_tot is None:
        out_dname = 'tif_{}e'.format(target_dose_A2_renframe)
    else:
        out_dname = 'tif_{}e_{}tot'.format(target_dose_A2_renframe, target_dose_A2_tot)
    out_dir = os.path.join(save_dir, out_dname)
    os.makedirs(out_dir, exist_ok=True)
    params_json_fpath = os.path.join(out_dir, 'eer2tiff_params.json')
    with open(params_json_fpath, 'w') as f:
        json.dump(params, f, indent=4)
    if args.verbose:
        print('parameters saved to {}'.format(params_json_fpath))

    # get feg calibration file
    feg_calib_fpath = os.path.join(in_dir, 'calib', 'feg_calib.json')
    if not os.path.exists(feg_calib_fpath):
        raise FileNotFoundError('feg calibration file not found: {}'.format(feg_calib_fpath))
    else:
        print('using feg calibration file: {}'.format(feg_calib_fpath))

    # get pixel size
    pix_size_A = util.pixel_size # [A]
    pix_area_A2 = pix_size_A ** 2 # [A^2]

    # find all eer files
    in_eer_fpaths_wildcard = os.path.join(in_dir, 'eer', '*.eer')
    in_eer_fpaths_list = util.filter_and_sort_fpaths(glob.glob(in_eer_fpaths_wildcard))
    print('found {} total eer files to process'.format(len(in_eer_fpaths_list)))

    # calculate number of rendered frames to be made from each movie
    if target_dose_A2_tot is not None:
        n_renframes_tot = int(np.round(target_dose_A2_tot / target_dose_A2_renframe))

    # loop over eer files
    for e_ind, eer_fpath in enumerate(in_eer_fpaths_list):
        t_start = time.time()
        eer_dirname = os.path.dirname(eer_fpath)
        eer_basename = os.path.basename(eer_fpath)

        # check if already processed
        final_out_fpath = os.path.join(out_dir, eer_basename.replace('.eer', '.tif'))
        if os.path.exists(final_out_fpath):
            print('skipping already processed file: {}'.format(final_out_fpath))
            continue

        print('{}/{} [{}]'.format(e_ind + 1, len(in_eer_fpaths_list), eer_basename))

        # get dose rate from beam current
        beam_current = util.read_beam_current(eer_fpath) # [nA]
        dose_rate_eps = util.get_dose_rate_eps(beam_current, feg_calib_fpath=feg_calib_fpath) # [e/pix/s]
        dose_rate_eA2s = dose_rate_eps / pix_area_A2 # [e/A^2/s]

        # get exposure time and dose
        (n_frames_tot, exposure_time_s, _, _) = util.get_eer_exposure_info(eer_fpath)
        dose_A2_tot = exposure_time_s * dose_rate_eA2s
        if args.verbose:
            print('... beam current [nA]: {}'.format(beam_current))
            print('... total eer frames: {}'.format(n_frames_tot))
            print('... total exposure time [s]: {}'.format(exposure_time_s))
            print('... total dose [e/A^2]: {}'.format(dose_A2_tot))

        # calculate frame binning and truncation
        if target_dose_A2_tot is not None:
            if dose_A2_tot < target_dose_A2_tot:
                print('... ... SKIPPING: dose {:0.5f} < target {:0.5f} [e/A^2]'.format(dose_A2_tot, target_dose_A2_tot))
                continue
        dose_A2_frame = dose_A2_tot / n_frames_tot # dose per (raw) frame [e/A^2/frame]
        n_raw_per_renframe = int(np.round(target_dose_A2_renframe / dose_A2_frame)) # number of raw frames to sum into each rendered frame
        dose_A2_renframe = n_raw_per_renframe * dose_A2_frame # dose per rendered frame [e/A^2/renframe]
        if target_dose_A2_tot is not None:
            dose_A2_tot_kept = n_renframes_tot * dose_A2_renframe # total dose kept per square angstrom [e/A^2]
            n_frames_kept = n_renframes_tot * n_raw_per_renframe # number of raw frames used
        if args.verbose:
            print('... ... raw frames per rendered frame: {}'.format(n_raw_per_renframe))
            print('... ... dose per rendered frame [e/A^2]: {}'.format(dose_A2_renframe)) # [e/A^2/renframe]
            if target_dose_A2_tot is not None:
                print('... ... will render {} frames (keeping {}/{})'.format(n_renframes_tot, n_frames_kept, n_frames_tot))
                print('... ... will keep total dose {} [e/A^2]'.format(n_frames_kept * dose_A2_frame))
            if target_dose_A2_tot is not None:
                print('... converting to tiff ({} frames)'.format(int(n_frames_kept)))
            else:
                print('... converting to tiff ({} frames)'.format(int(n_frames_tot / n_raw_per_renframe)))

        # form command string
        cmd_str = [relion_func] # [util.relion_convert_to_tiff_exe]
        cmd_str.append('--i')
        cmd_str.append(eer_fpath)
        cmd_str.append('--o')
        cmd_str.append(out_dir)
        cmd_str.append('--eer_grouping')
        cmd_str.append(str(n_raw_per_renframe))

        # run command
        eer2tiff = Popen(cmd_str, stdout=PIPE, stderr=PIPE, encoding='utf-8', text=True)
        _, errs = eer2tiff.communicate()

        # wait for file to be written
        if eer2tiff.returncode != 0:
            raise RuntimeError(f'conversion failed:\n{errs}')

        # clean up
        src_dir = os.path.join(out_dir, eer_dirname.lstrip('/'))
        src_fpath = os.path.join(src_dir, eer_basename.replace('.eer', '.tif'))
        dst_fpath = os.path.join(out_dir, os.path.basename(src_fpath))
        os.rename(src_fpath, dst_fpath)

        # truncate tiff if needed
        if target_dose_A2_tot is not None:
            if args.verbose:
                print('... truncating to {} rendered frames'.format(n_renframes_tot))
            util.truncate_tiff(dst_fpath, dst_fpath, n_renframes_tot)

        # report execution time
        t_end = time.time()
        print('... processing time: {:.2f} s'.format(t_end - t_start))
        print('... saved to: {}'.format(dst_fpath))

        # do final cleanup
        run([
            'find', os.path.expanduser(out_dir),
            '-mindepth', '1', '-maxdepth', '1', '-type', 'd',
            '-exec', 'rm', '-rf', '{}', '+'],
            check=True
        )

if __name__ == "__main__":
    main()