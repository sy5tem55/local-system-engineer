# Image Generation Tools

## ComfyUI
- **Path:** `/home/sy5/comfyui/`
- **Port:** `:8188`
- **Status:** Not running
- **PyTorch:** 2.12.0
- **Custom Nodes:**
  - ComfyUI-GGUF
  - ComfyUI_IPAdapter_plus
  - ComfyUI-Advanced-ControlNet
  - ComfyUI-VideoHelperSuite
  - comfyui_controlnet_aux
  - ComfyUI-AnimateDiff-Evolved
- **Model dirs:** checkpoints (empty), clip, clip_vision, controlnet, diffusion_models, loras, vae
- **Last run issue:** Corrupted node `#8` in workflow
- **Log:** `comfy_restart.log`

## AUTOMATIC1111 (Stable Diffusion WebUI)
- **Path:** `/home/sy5/imageGenHub/a1111/webui/`
- **Port:** `:7860` (default)
- **Conda env:** `env_a1111`
- **Entry:** `webui.py` / `launch.py`
- **Config:** `config.json`
- **Status:** Not running
- **Last activity:** May 22
- **Log:** `a1111_launch.log`
