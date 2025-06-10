# surface_extractor.py – yumuşatılmış marching-cubes (3 değer döndürür)
import numpy as np
from skimage import measure

# ----------------------------- Laplacian smoothing ---------------------
def _laplacian(verts, faces, it=15, lam=0.33):
    N = len(verts)
    adj = [[] for _ in range(N)]
    for a, b, c in faces:
        adj[a] += (b, c); adj[b] += (a, c); adj[c] += (a, b)
    v = verts.copy()
    for _ in range(it):
        delta = np.zeros_like(v)
        for i, nb in enumerate(adj):
            if nb:
                delta[i] = v[np.array(nb)].mean(0) - v[i]
        v += lam * delta
    return v

# ----------------------------- Ana fonksiyon ---------------------------
def extract_surface(volume, color_vol, threshold,
                    scale_factor, z_increment,
                    progress_callback=None, base_progress=0, weight=60,
                    stop_flag=lambda: False):
    """Geriye: verts, faces, vert_colors  (3 değer)"""
    if stop_flag(): return None, None, None
    if volume.dtype != np.float32:
        volume = volume.astype(np.float32) / 255.0

    iso = threshold / 255.0
    verts, faces, _, _ = measure.marching_cubes(volume, level=iso)
    if progress_callback: progress_callback(base_progress + int(weight*0.6))

    verts = _laplacian(verts, faces, it=15, lam=0.33)
    if progress_callback: progress_callback(base_progress + int(weight*0.8))

    H, W, D, _ = color_vol.shape
    vi = np.clip(np.round(verts).astype(np.int32),
                 [0,0,0], [H-1, W-1, D-1])
    bgr = color_vol[vi[:,0], vi[:,1], vi[:,2]].astype(np.float32)/255.0
    colors = bgr[:,[2,1,0]]

    verts[:,0] *= scale_factor
    verts[:,1] *= scale_factor
    verts[:,2] *= z_increment

    if progress_callback: progress_callback(base_progress + weight)
    return verts.astype(np.float32), faces.astype(np.uint32), colors

# ----------------------------- Büyük hacim -----------------------------
def stream_extract_surface(volume, color_vol, threshold,
                           scale_factor, z_increment,
                           chunk_depth=64, progress_callback=None,
                           base_progress=0, weight=60,
                           stop_flag=lambda: False):
    H, W, D = volume.shape
    verts_all, faces_all, cols_all = [], [], []
    v_ofs = 0
    chunks = list(range(0, D, chunk_depth-1))
    for ci, z0 in enumerate(chunks):
        if stop_flag(): return None, None, None
        z1 = min(z0+chunk_depth, D)
        sub = volume[:, :, z0:z1]
        vs, fs, _, _ = measure.marching_cubes(sub, level=threshold/255.0)
        vs[:,2] += z0
        vs = _laplacian(vs, fs, it=10, lam=0.33)

        vi = np.clip(np.round(vs).astype(np.int32),
                     [0,0,0], [H-1,W-1,D-1])
        bgr = color_vol[vi[:,0], vi[:,1], vi[:,2]].astype(np.float32)/255.0
        cols = bgr[:,[2,1,0]]

        verts_all.append(vs)
        faces_all.append(fs + v_ofs)
        cols_all.append(cols)
        v_ofs += vs.shape[0]

        if progress_callback:
            done = (ci+1)/len(chunks)
            progress_callback(base_progress + int(weight*0.8*done))

    verts  = np.concatenate(verts_all,0)
    faces  = np.concatenate(faces_all,0)
    colors = np.concatenate(cols_all,0)

    verts[:,0] *= scale_factor
    verts[:,1] *= scale_factor
    verts[:,2] *= z_increment
    if progress_callback: progress_callback(base_progress + weight)
    return verts.astype(np.float32), faces.astype(np.uint32), colors

# ----------------------------- GPU (opsiyonel) -------------------------
def gpu_extract_surface(volume, color_vol, threshold,
                        scale_factor, z_increment,
                        progress_callback=None, base_progress=0, weight=60,
                        stop_flag=lambda: False):
    try:
        import torch, torchmcubes
    except ModuleNotFoundError:
        # kütüphane yoksa CPU sürümüne düş
        return extract_surface(volume, color_vol, threshold,
                               scale_factor, z_increment,
                               progress_callback, base_progress, weight,
                               stop_flag)

    if stop_flag(): return None, None, None
    vol_gpu = torch.from_numpy(volume).float().cuda()
    verts, faces = torchmcubes.marching_cubes(vol_gpu, threshold/255.0)
    if stop_flag(): return None, None, None
    verts = verts.cpu().numpy(); faces = faces.cpu().numpy()

    H,W,D,_ = color_vol.shape
    vi = np.clip(np.round(verts).astype(np.int32),
                 [0,0,0], [H-1,W-1,D-1])
    bgr = color_vol[vi[:,0], vi[:,1], vi[:,2]].astype(np.float32)/255.0
    colors = bgr[:,[2,1,0]]

    verts[:,0] *= scale_factor
    verts[:,1] *= scale_factor
    verts[:,2] *= z_increment
    if progress_callback: progress_callback(base_progress + weight)
    return verts.astype(np.float32), faces.astype(np.uint32), colors
