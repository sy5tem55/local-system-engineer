"""
mesh_builder.py
Convert a 2D image + depth map into a textured 3D mesh (GLB / OBJ).
"""
import io
import numpy as np
from PIL import Image
import trimesh


def build_mesh(
    image: Image.Image,
    depth: np.ndarray,
    resolution: int = 256,
    depth_scale: float = 0.6,
) -> trimesh.Trimesh:
    """
    Build a UV-mapped quad grid displaced by the depth map.
    Includes X-axis mirror for symmetric back-of-head reconstruction.
    """
    N = resolution

    # Resize — flip image vertically so Y+ = up in 3D space
    img_pil = image.resize((N, N), Image.LANCZOS).transpose(Image.FLIP_TOP_BOTTOM)
    img_arr = np.array(img_pil)

    depth_pil = Image.fromarray((depth * 255).astype(np.uint8)).resize((N, N), Image.BILINEAR)
    depth_pil = depth_pil.transpose(Image.FLIP_TOP_BOTTOM)
    depth_r = np.array(depth_pil).astype(np.float32) / 255.0

    # Vertex grid: x left→right, y bottom→top (after flip), z = depth
    grid = np.linspace(-1, 1, N)
    xx, yy = np.meshgrid(grid, grid)      # (N, N)
    zz = depth_r * depth_scale            # (N, N)

    vertices = np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=-1).astype(np.float32)

    # Quad faces
    idx = np.arange(N * N).reshape(N, N)
    tl = idx[:-1, :-1].ravel()
    tr = idx[:-1, 1:].ravel()
    bl = idx[1:, :-1].ravel()
    br = idx[1:, 1:].ravel()
    faces = np.vstack([
        np.column_stack([tl, bl, tr]),
        np.column_stack([tr, bl, br]),
    ]).astype(np.int32)

    # UV: standard top-left origin (image is already flipped so no UV flip needed)
    u = (xx + 1) / 2.0
    v = (yy + 1) / 2.0
    uv = np.stack([u.ravel(), v.ravel()], axis=-1).astype(np.float32)

    texture = Image.fromarray(img_arr)

    # Front face mesh
    front = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        visual=trimesh.visual.TextureVisuals(uv=uv, image=texture),
        process=False,
    )

    # Mirror on X axis for back half — flattened depth, mirrored texture
    back_verts = vertices.copy()
    back_verts[:, 0] *= -1
    back_verts[:, 2] *= 0.3          # shallower back
    back_faces = faces[:, ::-1]      # reverse winding for correct normals

    mirror_img = Image.fromarray(img_arr[:, ::-1, :])  # mirror texture horizontally

    back = trimesh.Trimesh(
        vertices=back_verts,
        faces=back_faces,
        visual=trimesh.visual.TextureVisuals(uv=uv, image=mirror_img),
        process=False,
    )

    mesh = trimesh.util.concatenate([front, back])
    return mesh


def export_glb(mesh: trimesh.Trimesh) -> bytes:
    buf = io.BytesIO()
    mesh.export(buf, file_type="glb")
    return buf.getvalue()


def export_obj(mesh: trimesh.Trimesh) -> bytes:
    buf = io.BytesIO()
    mesh.export(buf, file_type="obj")
    return buf.getvalue()


def to_glb_or_obj(mesh: trimesh.Trimesh, fmt: str = "glb"):
    if fmt == "glb":
        return export_glb(mesh), "model/gltf-binary", "glb"
    return export_obj(mesh), "text/plain", "obj"
