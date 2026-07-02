"""
pifuhd_model.py  —  drop-in replacement for depth_model.py + mesh_builder.py
Wraps PIFuHD to produce a full 3D mesh from a single portrait PNG.

Usage:
    from pifuhd_model import reconstruct_portrait
    mesh = reconstruct_portrait("/path/to/portrait.png")  # returns trimesh.Trimesh
"""

import sys
import os
import io
import numpy as np
from pathlib import Path
from PIL import Image
import trimesh
import torch

# PIFuHD repo must be cloned at PROJECT_ROOT/pifuhd/
PROJECT_ROOT = Path(__file__).parent
PIFUHD_DIR   = PROJECT_ROOT / "pifuhd"
CHECKPOINT   = PIFUHD_DIR / "checkpoints" / "pifuhd.pt"
UPLOAD_TMP   = PROJECT_ROOT / "uploads"
UPLOAD_TMP.mkdir(exist_ok=True)

# Add PIFuHD to path
sys.path.insert(0, str(PIFUHD_DIR))

_model = None

def _load_model():
    global _model
    if _model is not None:
        return _model

    print("[pifuhd] Loading PIFuHD model...")
    from lib.options import BaseOptions
    from lib.mesh_util import save_obj_mesh_with_color, reconstruction
    from lib.model import HGPIFuNetwNML, HGPIFuMRNet

    # PIFuHD uses its own option parser — build minimal options
    opt = _make_options()

    # Build coarse + fine networks
    state_dict = torch.load(str(CHECKPOINT), map_location='cpu')

    netG = HGPIFuNetwNML(opt, 'geometric')
    netMR = HGPIFuMRNet(opt, netG, 'geometric')

    def load_state(net, state):
        own = net.state_dict()
        new = {k: v for k, v in state.items() if k in own and own[k].shape == v.shape}
        own.update(new)
        net.load_state_dict(own)

    load_state(netMR, state_dict)

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    netMR = netMR.to(device)
    netMR.eval()
    print(f"[pifuhd] Model loaded on {device}")

    _model = (netMR, opt, device)
    return _model


def _make_options():
    """Minimal option object for PIFuHD inference."""
    class Opt:
        pass
    opt = Opt()
    # Coarse network
    opt.loadSize = 512
    opt.resolution = 256
    opt.num_views = 1
    opt.norm = 'group'
    opt.norm_color = 'instance'
    opt.num_stack = 4
    opt.num_hourglass = 2
    opt.skip_hourglass = False
    opt.hg_down = 'ave_pool'
    opt.hourglass_dim = 256
    opt.mlp_dim = [257, 1024, 512, 256, 128, 1]
    opt.mlp_dim_color = [513, 1024, 512, 256, 128, 3]
    opt.use_attention = False
    opt.use_spatial_feature = True
    opt.point_feat_size = 256
    opt.num_sample_inout = 5000
    opt.num_sample_color = 0
    opt.sigma = 5.0
    opt.image_size = 512
    # Fine network (MR)
    opt.loadSizeMR = 1024
    opt.resolutionMR = 512
    opt.num_stackMR = 1
    opt.num_hourglassMR = 2
    opt.hourglass_dimMR = 256
    opt.mlp_dimMR = [257+13, 1024, 512, 256, 128, 1]
    opt.use_attentionMR = False
    opt.use_spatial_featureMR = True
    opt.point_feat_sizeMR = 256+13
    return opt


def reconstruct_portrait(img_path: str) -> trimesh.Trimesh:
    """
    Run PIFuHD on a portrait image and return a trimesh.Trimesh.

    Args:
        img_path: path to input PNG/JPG portrait (any size, will be resized)

    Returns:
        trimesh.Trimesh with full 3D face/bust reconstruction
    """
    from lib.mesh_util import reconstruction
    from lib.data_util import load_calib

    netMR, opt, device = _load_model()

    # Prepare image — resize to 512 (coarse) and 1024 (fine)
    img = Image.open(img_path).convert('RGB')

    def to_tensor(pil_img, size):
        pil_img = pil_img.resize((size, size), Image.LANCZOS)
        arr = np.array(pil_img, dtype=np.float32) / 255.0
        arr = arr * 2.0 - 1.0  # normalize to [-1, 1]
        return torch.from_numpy(arr.transpose(2, 0, 1)).unsqueeze(0).to(device)

    img_512  = to_tensor(img, 512)
    img_1024 = to_tensor(img, 1024)

    # Orthographic calibration matrix (identity for frontal portrait)
    calib = torch.eye(4, dtype=torch.float32).unsqueeze(0).to(device)

    print("[pifuhd] Running reconstruction (may take 15-30s)...")

    with torch.no_grad():
        verts, faces, normals, _ = reconstruction(
            net       = netMR,
            cuda      = device,
            calib_tensor = calib,
            resolution   = opt.resolutionMR,
            b_min        = np.array([-1.0, -1.0, -1.0]),
            b_max        = np.array([ 1.0,  1.0,  1.0]),
            use_octree   = True,
            num_samples  = 50000,
            transform    = None,
            img_tensor   = img_512,
            img_tensor_high = img_1024,
        )

    print(f"[pifuhd] Mesh: {len(verts)} verts, {len(faces)} faces")

    mesh = trimesh.Trimesh(
        vertices = verts,
        faces    = faces,
        vertex_normals = normals,
        process  = False,
    )
    return mesh


def export_glb(mesh: trimesh.Trimesh) -> bytes:
    buf = io.BytesIO()
    mesh.export(buf, file_type='glb')
    return buf.getvalue()
