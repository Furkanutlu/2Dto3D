import numpy as np

def clip_point_cloud(verts: np.ndarray,
                     colors: np.ndarray,
                     plane_pt: np.ndarray,
                     plane_n: np.ndarray):
    """
    plane_n   : normalize olmak zorunda değil.
    Dönüş     : (verts_keep, colors_keep), (verts_cut, colors_cut)
    """
    # taraf testi
    side = np.dot(verts - plane_pt, plane_n) >= 0
    return (verts[side], colors[side]), (verts[~side], colors[~side])
def world_plane_to_local(mesh, plane_pt, plane_n):
    """
    plane_pt, plane_n : world-space
    Dönüş             : (pt_local, n_local) – normal normalize edilmiştir
    """
    M_inv = np.linalg.inv(mesh.model_matrix())
    pt = np.append(plane_pt, 1.0)
    n  = plane_n / (np.linalg.norm(plane_n) + 1e-12)

    pt_local = (M_inv @ pt)[:3]
    n_local  = (M_inv[:3,:3].T @ n)          # inverse-transpose rot.
    n_local /= np.linalg.norm(n_local)
    return pt_local.astype(np.float32), n_local.astype(np.float32)