# point_cloud_extractor.py
import numpy as np

def extract_point_cloud(volume: np.ndarray,
                        color_vol: np.ndarray,
                        threshold: int = 80,
                        scale_factor: float = 1.0,
                        z_increment: float = 1.0,
                        step: int = 1):
    """
    volume    : (H,W,D) uint8 veya float32
    color_vol : (H,W,D,3) uint8  (BGR)
    threshold : 0-255   – eşiğin ÜSTÜ ‘madde’ sayılır
    step      : >1 ise seyreltme (performans)
    ------------------------------------------------------------------
    Dönüş     : verts(N,3 float32), colors(N,3 float32)  (RGB 0-1)
    """
    if volume.dtype != np.float32:
        volume = volume.astype(np.float32) / 255.0
    msk = volume >= (threshold / 255.0)
    if step > 1:            # basit down-sample
        msk[1::step, 1::step, 1::step] = False

    coords = np.argwhere(msk)
    if coords.size == 0:
        return np.empty((0, 3), np.float32), np.empty((0, 3), np.float32)

    verts = coords.astype(np.float32)
    bgr   = color_vol[coords[:, 0], coords[:, 1], coords[:, 2]].astype(np.float32) / 255.0
    colors = bgr[:, [2, 1, 0]]               # BGR → RGB

    verts[:, 0] *= scale_factor
    verts[:, 1] *= scale_factor
    verts[:, 2] *= z_increment
    return verts, colors
