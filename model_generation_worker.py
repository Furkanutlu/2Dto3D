import os
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from volume_loader import load_volume
from surface_extractor import extract_surface

class ModelGenerationWorker(QThread):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(str)

    def __init__(self, slice_folder, output_path, scale_factor=0.1,
                 z_increment=0.1, threshold=100, resolution=(256, 256),
                 noise_method='Yok'):
        super().__init__()
        self.slice_folder = slice_folder
        self.output_path = output_path
        self.scale_factor = scale_factor
        self.z_increment = z_increment
        self.threshold = threshold
        self.resolution = resolution
        self.noise_method = noise_method
        self.stop_requested = False

    def stop(self):
        self.stop_requested = True

    def run(self):
        self.progress_signal.emit(0)
        volume, color_vol = load_volume(
            self.slice_folder, self.resolution,
            stop_flag=lambda: self.stop_requested,
            progress_callback=self.progress_signal.emit,
            weight=40
        )
        if volume is None or self.stop_requested:
            self.finished_signal.emit('')
            return
        try:
            import torch
            import torchmcubes
            gpu_ok = torch.cuda.is_available()
        except ImportError:
            gpu_ok = False
        voxels = volume.size
        big = voxels > 256 * 256 * 512
        if gpu_ok:
            from surface_extractor import gpu_extract_surface as surf_fn
        elif big:
            from surface_extractor import stream_extract_surface as surf_fn
        else:
            from surface_extractor import extract_surface as surf_fn
        verts, faces, vert_colors = surf_fn(
            volume, color_vol, self.threshold,
            self.scale_factor, self.z_increment,
            progress_callback=self.progress_signal.emit,
            base_progress=40, weight=60,
            stop_flag=lambda: self.stop_requested
        )
        if verts is None or self.stop_requested:
            self.finished_signal.emit('')
            return
        with open(self.output_path, 'w') as f:
            for (x, y, z), (r, g, b) in zip(verts, vert_colors):
                f.write(f'v {x:.4f} {y:.4f} {z:.4f} {r:.4f} {g:.4f} {b:.4f}\n')
            for a, b_, c_ in (faces + 1):
                f.write(f'f {a} {b_} {c_}\n')
        self.progress_signal.emit(100)
        self.finished_signal.emit(self.output_path)

