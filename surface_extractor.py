import numpy as np
from skimage import measure

def extract_surface(volume, color_vol, threshold, scale_factor, z_increment,
                    progress_callback=None, base_progress=0, weight=60,
                    stop_flag=lambda: False):
    if stop_flag():
        return None, None, None
    verts, faces, _, _ = measure.marching_cubes(volume, level=threshold / 255.0)
    if progress_callback:
        progress_callback(base_progress + int(weight * 0.3))
    if stop_flag():
        return None, None, None
    H, W, D, _ = color_vol.shape
    vi = np.clip(np.round(verts).astype(np.int32),
                 [0, 0, 0], [H - 1, W - 1, D - 1])
    bgr = (color_vol[vi[:, 0], vi[:, 1], vi[:, 2]].astype(np.float32)) / 255.0
    vert_colors = bgr[:, [2, 1, 0]]  # BGR → RGB
    verts[:, 0] *= scale_factor
    verts[:, 1] *= scale_factor
    verts[:, 2] *= z_increment
    if progress_callback:
        progress_callback(base_progress + weight)
    return verts, faces, vert_colors

def stream_extract_surface(volume, color_vol, threshold, scale_factor, z_increment,
                           chunk_depth=64, progress_callback=None, base_progress=0,
                           weight=60, stop_flag=lambda: False):
    H, W, D = volume.shape
    verts_all, faces_all, cols_all = [], [], []
    v_ofs = 0
    chunks = list(range(0, D, chunk_depth - 1))
    for ci, z0 in enumerate(chunks):
        if stop_flag():
            return None, None, None
        z1 = min(z0 + chunk_depth, D)
        sub_vol = volume[:, :, z0:z1]
        verts, faces, _, _ = measure.marching_cubes(sub_vol, level=threshold / 255.0)
        verts[:, 2] += z0
        vi = np.clip(np.round(verts).astype(np.int32), [0, 0, 0], [H - 1, W - 1, D - 1])
        bgr = color_vol[vi[:, 0], vi[:, 1], vi[:, 2]].astype(np.float32) / 255.0
        cols = bgr[:, [2, 1, 0]]
        verts_all.append(verts)
        faces_all.append(faces + v_ofs)
        cols_all.append(cols)
        v_ofs += verts.shape[0]
        if progress_callback:
            progress_callback(base_progress + int(weight * 0.3 * (ci + 1) / len(chunks)))
    verts = np.concatenate(verts_all, axis=0)
    faces = np.concatenate(faces_all, axis=0)
    vert_colors = np.concatenate(cols_all, axis=0)
    verts[:, 0] *= scale_factor
    verts[:, 1] *= scale_factor
    verts[:, 2] *= z_increment
    if progress_callback:
        progress_callback(base_progress + weight)
    return verts, faces, vert_colors

def gpu_extract_surface(volume, color_vol, threshold, scale_factor, z_increment,
                        progress_callback=None, base_progress=0, weight=60,
                        stop_flag=lambda: False):
    import torch, torchmcubes
    if stop_flag():
        return None, None, None
    vol_gpu = torch.from_numpy(volume).float().cuda()
    verts, faces = torchmcubes.marching_cubes(vol_gpu, threshold / 255.0)
    if stop_flag():
        return None, None, None
    H, W, D, _ = color_vol.shape
    color_gpu = torch.from_numpy(color_vol).float().cuda()
    vi = torch.round(verts).long()
    vi[:, 0].clamp_(0, H - 1)
    vi[:, 1].clamp_(0, W - 1)
    vi[:, 2].clamp_(0, D - 1)
    bgr = color_gpu[vi[:, 0], vi[:, 1], vi[:, 2]] / 255.0
    vert_colors = bgr[:, [2, 1, 0]].cpu().numpy()
    verts = verts.cpu().numpy()
    verts[:, 0] *= scale_factor
    verts[:, 1] *= scale_factor
    verts[:, 2] *= z_increment
    if progress_callback:
        progress_callback(base_progress + weight)
    return verts, faces.cpu().numpy(), vert_colors
