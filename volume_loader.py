# volume_loader.py  –  TAM HALİ
import os, cv2, numpy as np
from concurrent.futures import ThreadPoolExecutor

def _read_png(fn, resolution):
    g = cv2.imread(fn, cv2.IMREAD_GRAYSCALE)
    c = cv2.imread(fn, cv2.IMREAD_COLOR)
    if resolution:
        g = cv2.resize(g, resolution, interpolation=cv2.INTER_AREA)
        c = cv2.resize(c, resolution, interpolation=cv2.INTER_AREA)
    return g, c

def load_volume(slice_folder, resolution,
                stop_flag=lambda: False,
                progress_callback=None, weight=40):
    files = [os.path.join(slice_folder, f)
             for f in sorted(os.listdir(slice_folder))
             if f.lower().endswith('.png')]
    total = len(files)
    gray_slices, color_slices = [None]*total, [None]*total

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        futs = {pool.submit(_read_png, fn, resolution): i
                for i, fn in enumerate(files)}
        for done in futs:
            if stop_flag():
                return None, None
            idx = futs[done]
            g, c = done.result()
            gray_slices[idx]  = g
            color_slices[idx] = c
            if progress_callback:
                progress_callback(int((idx + 1) / total * weight))

    volume    = np.stack(gray_slices , axis=-1).astype(np.float32) / 255.0
    color_vol = np.stack(color_slices, axis= 2)
    return volume, color_vol
