"""Downloads the models of the AI texture test into C:/tww3_mtb_comfyui/ComfyUI/models. Only .safetensors, only from the authors' repositories.

Run with the venv's python: C:/tww3_mtb_comfyui/venv/Scripts/python.exe tools/ai_tex_fetch_models.py [info]
"""
import shutil
import sys
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

MODELS = Path("C:/tww3_mtb_comfyui/ComfyUI/models")
FILES = [
    ("stabilityai/stable-diffusion-xl-base-1.0", "sd_xl_base_1.0.safetensors", "checkpoints/sd_xl_base_1.0.safetensors"),
    ("diffusers/stable-diffusion-xl-1.0-inpainting-0.1", "unet/diffusion_pytorch_model.fp16.safetensors", "unet/sdxl_inpaint_0.1.fp16.safetensors"),
    ("madebyollin/sdxl-vae-fp16-fix", "sdxl.vae.safetensors", "vae/sdxl_vae_fp16_fix.safetensors"),
    ("h94/IP-Adapter", "sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors", "ipadapter/ip-adapter-plus_sdxl_vit-h.safetensors"),
    ("h94/IP-Adapter", "models/image_encoder/model.safetensors", "clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"),
    ("xinsir/controlnet-canny-sdxl-1.0", "diffusion_pytorch_model.safetensors", "controlnet/sdxl_canny_xinsir.safetensors"),
]
api = HfApi()
total = 0
for repo, name, target in FILES:
    info = api.model_info(repo, files_metadata=True)
    size = next(s.size for s in info.siblings if s.rfilename == name)
    total += size
    print(repo, name, f"{size / 2**30:.2f} GB", "license:", (info.card_data or {}).get("license"), info.card_data.get("license_name") if info.card_data else None, flush=True)
print(f"total {total / 2**30:.1f} GB", flush=True)
if len(sys.argv) > 1:
    sys.exit()
for repo, name, target in FILES:
    out = MODELS / target
    if out.exists():
        continue
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(hf_hub_download(repo, name, local_dir=MODELS.parent.parent / "hf_tmp"))
    shutil.move(str(tmp), str(out))
    print("got", out, out.stat().st_size, flush=True)
shutil.rmtree(MODELS.parent.parent / "hf_tmp", ignore_errors=True)
print("all done", flush=True)
