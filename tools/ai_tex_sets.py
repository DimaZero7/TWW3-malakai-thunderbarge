"""The variants tried."""
W = dict(kind="wood", pic="wood_pic", mask="wood_mask", style="wood_style")
# A: inpainting model from nothing; B: the same from rows running across the hole; C: plain SDXL over a copy of the same rows further along
wood1b = None  # set below
wood1 = [
    dict(W, name="wood_A1", mode="fill", guide="wood_guide", seed=11, cn=0.75, ipa=0.7),
    dict(W, name="wood_A2", mode="fill", guide="wood_guide_grain", seed=12, cn=0.75, ipa=0.7),
    dict(W, name="wood_B1", mode="partial", init="wood_init_rows", guide="wood_guide_grain", seed=21, denoise=0.8, cn=0.7, ipa=0.7),
    dict(W, name="wood_B2", mode="partial", init="wood_init_rows", guide="wood_guide_grain", seed=22, denoise=0.65, cn=0.7, ipa=0.7),
    dict(W, name="wood_C1", mode="base", init="wood_init_shift", guide="wood_guide", seed=31, denoise=0.5, cn=0.6, ipa=0.6),
    dict(W, name="wood_C2", mode="base", init="wood_init_rows", guide="wood_guide_grain", seed=32, denoise=0.6, cn=0.7, ipa=0.7),
]
wood1b = wood1[2:]
# second round: around C1 (plain SDXL over the same rows further along) and a stronger pure generation
wood2 = [
    dict(W, name="wood_C3", mode="base", init="wood_init_shift", guide="wood_guide", seed=33, denoise=0.6, cn=0.6, ipa=0.6),
    dict(W, name="wood_C4", mode="base", init="wood_init_shift", guide="wood_guide", seed=34, denoise=0.45, cn=0.5, ipa=0.6),
    dict(W, name="wood_B3", mode="partial", init="wood_init_shift", guide="wood_guide", seed=23, denoise=0.75, cn=0.6, ipa=0.6),
    dict(W, name="wood_A3", mode="fill", guide="wood_guide", seed=13, cn=0.5, ipa=0.9, ipa_type="strong style transfer"),
]
# third round: the rough start from rows 330 columns further on, clean of burns and rivets
wood3 = [
    dict(W, name="wood_C5", mode="base", init="wood_init_shift330", guide="wood_guide", seed=35, denoise=0.5, cn=0.6, ipa=0.6),
    dict(W, name="wood_C6", mode="base", init="wood_init_shift330", guide="wood_guide", seed=36, denoise=0.6, cn=0.6, ipa=0.6),
    dict(W, name="wood_B4", mode="partial", init="wood_init_shift330", guide="wood_guide", seed=24, denoise=0.7, cn=0.6, ipa=0.6),
    dict(W, name="wood_B5", mode="partial", init="wood_init_shift330", guide="wood_guide", seed=25, denoise=0.85, cn=0.6, ipa=0.6),
]
S = dict(kind="steel", pic="steel_pic", mask="steel_mask", style="steel_style", guide="steel_guide")
steel1 = [
    dict(S, name="steel_A1", mode="fill", seed=41, cn=0.8, ipa=0.7),
    dict(S, name="steel_B1", mode="partial", init="steel_init", seed=51, denoise=0.9, cn=0.8, ipa=0.7),
    dict(S, name="steel_B2", mode="partial", init="steel_init", seed=52, denoise=0.8, cn=0.8, ipa=0.7),
    dict(S, name="steel_C1", mode="base", init="steel_init", seed=61, denoise=0.75, cn=0.8, ipa=0.7),
]
steel2 = [
    dict(S, name="steel_C2", mode="base", init="steel_init_shift", seed=62, denoise=0.55, cn=0.8, ipa=0.6),
    dict(S, name="steel_B3", mode="partial", init="steel_init_shift", seed=53, denoise=0.7, cn=0.8, ipa=0.6),
]
