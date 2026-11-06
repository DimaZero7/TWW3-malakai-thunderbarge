"""Sends the variants to the local ComfyUI (127.0.0.1 only). Venv python: ai_tex_generate.py SET [SET...] ; SETs are in ai_tex_sets.py. Results: build/solid_hull_ai/work/gen/NAME.png, seconds in gen/times.json."""
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

from ai_tex_common import OUT, WORK

COMFY = Path("C:/tww3_mtb_comfyui/ComfyUI")
URL = "http://127.0.0.1:8199"
GEN = WORK / "gen"
GEN.mkdir(exist_ok=True)

PROMPT = {
    "wood": "hand painted game texture, dark brown stained hardwood ship hull, flat orthographic albedo map, long rigid planks, perfectly straight horizontal seams, thin dark gaps between boards, straight parallel wood grain, hard timber, fine scratches",
    "steel": "hand painted game texture, flat orthographic albedo map, grey riveted steel armour plate, hammered mottled metal, straight vertical plate seam with bright edge, round steel rivets",
}
NEGATIVE = {
    "wood": "wavy, curved, bent, warped, swirling grain, fan, radial, knots, soft, blurry, perspective, depth, photo, text, watermark, nails, metal, circle, noise",
    "steel": "wood, curved seam, soft, blurry, perspective, depth, photo, text, watermark, rust, circle, hole, noise",
}


def post(path, data):
    req = urllib.request.Request(URL + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        raise SystemExit(e.read().decode()[:3000])


def get(path):
    return json.load(urllib.request.urlopen(URL + path))


def input_file(path):
    name = "mtb_" + path.name
    shutil.copy(path, COMFY / "input" / name)
    return name


def graph(v):
    """v: kind (wood/steel), mode (fill/partial/base), pic, mask, init, guide, style, seed, denoise, cn, ipa, ipa_end, steps, cfg."""
    g = {}
    n = 0

    def add(cls, **inputs):
        nonlocal n
        n += 1
        g[str(n)] = {"class_type": cls, "inputs": inputs}
        return [str(n), 0], str(n)

    def out(node, i):
        return [node, i]

    _, ck = add("CheckpointLoaderSimple", ckpt_name="sd_xl_base_1.0.safetensors")
    clip = out(ck, 1)
    vae = add("VAELoader", vae_name="sdxl_vae_fp16_fix.safetensors")[0]
    model = out(ck, 0) if v["mode"] == "base" else add("UNETLoader", unet_name="sdxl_inpaint_0.1.fp16.safetensors", weight_dtype="default")[0]
    if v.get("ipa", 0) > 0:
        ip = add("IPAdapterModelLoader", ipadapter_file="ip-adapter-plus_sdxl_vit-h.safetensors")[0]
        cv = add("CLIPVisionLoader", clip_name="CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors")[0]
        style = add("LoadImage", image=input_file(WORK / f"{v['style']}.png"))[0]
        model = add("IPAdapterAdvanced", model=model, ipadapter=ip, image=style, clip_vision=cv, weight=v["ipa"], weight_type=v.get("ipa_type", "style transfer"), combine_embeds="concat", start_at=0.0, end_at=v.get("ipa_end", 1.0), embeds_scaling="V only")[0]
    pos = add("CLIPTextEncode", clip=clip, text=PROMPT[v["kind"]])[0]
    neg = add("CLIPTextEncode", clip=clip, text=NEGATIVE[v["kind"]])[0]
    pic = add("LoadImage", image=input_file(WORK / f"{v['pic']}.png"))[0]
    mask = add("LoadImageMask", image=input_file(WORK / f"{v['mask']}.png"), channel="red")[0]
    init = pic if v["mode"] == "fill" or not v.get("init") else add("LoadImage", image=input_file(WORK / f"{v['init']}.png"))[0]
    if v["mode"] == "fill":
        latent = add("VAEEncodeForInpaint", pixels=pic, vae=vae, mask=mask, grow_mask_by=8)[0]
    else:
        latent = add("VAEEncode", pixels=init, vae=vae)[0]
        latent = add("SetLatentNoiseMask", samples=latent, mask=mask)[0]
    if v["mode"] == "partial":
        _, ic = add("InpaintModelConditioning", positive=pos, negative=neg, vae=vae, pixels=init, mask=mask, noise_mask=True)
        pos, neg, latent = out(ic, 0), out(ic, 1), out(ic, 2)
    if v.get("cn", 0) > 0:
        cn = add("ControlNetLoader", control_net_name="sdxl_canny_xinsir.safetensors")[0]
        hint = add("LoadImage", image=input_file(WORK / f"{v['guide']}.png"))[0]
        _, ca = add("ControlNetApplyAdvanced", positive=pos, negative=neg, control_net=cn, image=hint, strength=v["cn"], start_percent=0.0, end_percent=v.get("cn_end", 1.0), vae=vae)
        pos, neg = out(ca, 0), out(ca, 1)
    sampled = add("KSampler", model=model, positive=pos, negative=neg, latent_image=latent, seed=v["seed"], steps=v.get("steps", 30), cfg=v.get("cfg", 6.0), sampler_name="dpmpp_2m", scheduler="karras", denoise=v.get("denoise", 1.0))[0]
    image = add("VAEDecode", samples=sampled, vae=vae)[0]
    add("SaveImage", images=image, filename_prefix="mtb/" + v["name"])
    return g


def run(v):
    start = time.time()
    res = post("/prompt", {"prompt": graph(v)})
    pid = res["prompt_id"]
    while True:
        h = get("/history/" + pid)
        if pid in h:
            break
        time.sleep(1)
    entry = h[pid]
    if entry["status"].get("status_str") == "error":
        raise SystemExit(json.dumps(entry["status"], indent=1)[:3000])
    for node in entry["outputs"].values():
        for im in node.get("images", []):
            src = COMFY / "output" / im["subfolder"] / im["filename"]
            shutil.move(str(src), str(GEN / f"{v['name']}.png"))
    return time.time() - start


def main():
    import ai_tex_sets as sets
    times_file = GEN / "times.json"
    times = json.loads(times_file.read_text()) if times_file.exists() else {}
    for set_name in sys.argv[1:]:
        for v in getattr(sets, set_name):
            times[v["name"]] = round(run(v), 1)
            print(v["name"], times[v["name"]], "s", flush=True)
            times_file.write_text(json.dumps(times, indent=1))


if __name__ == "__main__":
    main()
