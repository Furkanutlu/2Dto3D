import os
import cv2
import numpy as np

def load_volume(slice_folder, resolution, stop_flag=lambda: False,
                progress_callback=None, weight=40):
    slice_files = [f for f in sorted(os.listdir(slice_folder))
                   if f.lower().endswith('.png')]
    gray_slices = []
    color_slices = []
    total = len(slice_files)
    for idx, fn in enumerate(slice_files):
        if stop_flag():
            return None, None
        g = cv2.imread(os.path.join(slice_folder, fn), cv2.IMREAD_GRAYSCALE)
        c = cv2.imread(os.path.join(slice_folder, fn), cv2.IMREAD_COLOR)
        if resolution:
            g = cv2.resize(g, resolution, interpolation=cv2.INTER_AREA)
            c = cv2.resize(c, resolution, interpolation=cv2.INTER_AREA)
        gray_slices.append(g)
        color_slices.append(c)
        if progress_callback:
            progress_callback(int((idx + 1) / total * weight))
    volume = np.stack(gray_slices, axis=-1).astype(np.float32) / 255.0
    color_vol = np.stack(color_slices, axis=2)
    return volume, color_vol
