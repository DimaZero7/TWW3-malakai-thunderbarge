"""Grey-view snapshots for the solid hull work in a live Blender (run through Blender MCP). Blender axes.

shoot(eye, target, path) renders with Workbench: grey single colour, studio light, grey matcap, a striped reflection matcap (zebra: bends show bumps), or a raking sun light
(EEVEE, grey diffuse, one sun grazing the hull: shows dents the way a low sun does);
"tex" and "texrake" are the same with the objects' own textured materials (soft world, or the low sun alone). Only objects passed in `show` are visible during the shot.
"""
import bpy
from mathutils import Vector


def _cam(s):
    cam = s.objects.get("CAM-view")
    if cam is None:
        cam = bpy.data.objects.new("CAM-view", bpy.data.cameras.new("CAM-view"))
        s.collection.objects.link(cam)
    s.camera = cam
    return cam


def shoot(eye, target, path, show, size=(640, 480), lens=50, ortho=None, look="studio", light_dir=(0.2, 0.9, 0.35)):
    s = bpy.context.scene
    s.render.engine = "BLENDER_WORKBENCH"
    sh = s.display.shading
    sh.color_type = "SINGLE"
    sh.single_color = (0.72, 0.72, 0.72)
    sh.show_specular_highlight = look != "raking"
    sh.show_cavity = False
    sh.show_shadows = False
    if look in ("matcap", "zebra"):
        sh.light = "MATCAP"
        sh.studio_light = "basic_grey.exr" if look == "matcap" else "check_reflection_horizontal.exr"
    elif look in ("raking", "tex", "texrake"):
        _raking(s, light_dir, textured=look != "raking", world=0.06 if look != "tex" else 0.45)
    else:
        sh.light = "STUDIO"
    s.render.film_transparent = False
    s.render.resolution_x, s.render.resolution_y = size
    s.render.resolution_percentage = 100
    s.render.image_settings.file_format = "PNG"
    cam = _cam(s)
    cam.data.clip_start = 0.01
    cam.data.clip_end = 200
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    else:
        cam.data.type = "PERSP"
        cam.data.lens = lens
    e, t = Vector(eye), Vector(target)
    cam.location = e
    cam.rotation_euler = (t - e).to_track_quat("-Z", "Y").to_euler()
    hidden = {}
    for ob in s.objects:
        if ob.type == "MESH":
            hidden[ob.name] = ob.hide_render
            ob.hide_render = ob.name not in show
    s.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    for name, h in hidden.items():
        s.objects[name].hide_render = h
    if look in ("raking", "tex", "texrake"):
        s.view_layers[0].material_override = None
        s.objects["LGT-rake"].hide_render = True
    return str(path)


def _raking(s, light_dir, textured=False, world=0.06):
    """EEVEE, plain grey diffuse override, one sun grazing the surface from light_dir (towards the light), dim world."""
    s.render.engine = "BLENDER_EEVEE"
    mat = bpy.data.materials.get("MAT-rake")
    if mat is None:
        mat = bpy.data.materials.new("MAT-rake")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1)
        bsdf.inputs["Roughness"].default_value = 0.9
    s.view_layers[0].material_override = None if textured else mat
    sun = s.objects.get("LGT-rake")
    if sun is None:
        sun = bpy.data.objects.new("LGT-rake", bpy.data.lights.new("LGT-rake", "SUN"))
        s.collection.objects.link(sun)
    sun.hide_render = False
    sun.data.energy = 4.0 if world < 0.2 else 3.0
    sun.data.angle = 0.02
    sun.data.use_shadow = False      # shading by normals only: cast shadows of the low-poly hull hide the surface
    sun.rotation_euler = Vector(light_dir).normalized().to_track_quat("Z", "Y").to_euler()
    if s.world is None:
        s.world = bpy.data.worlds.new("WLD-dim")
    s.world.use_nodes = True
    bg = s.world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (world, world, world, 1)
    bg.inputs[1].default_value = 1.0
    for o in s.objects:
        if o.type == "LIGHT" and o.name != "LGT-rake":
            o.hide_render = True


PORT = (1.559, 5.769, 1.223)


def views(side):
    """Named camera setups around the bow gun port of one side (side = 1 for +x, -1 for -x): eye, target, kwargs."""
    s = side
    px, py, pz = PORT
    t = (s * px, py, pz)
    return {
        "close": ((s * (px + 6.5), py + 2.5, pz - 2.6), t, dict(ortho=2.8)),
        "side": ((s * 14, py, pz + 0.6), (s * px, py, pz + 0.6), dict(ortho=4.5)),
        "fwd": ((s * (px + 3.2), py + 4.2, pz + 0.9), t, dict(lens=40)),
        "aft": ((s * (px + 3.6), py - 3.6, pz + 0.4), t, dict(lens=40)),
        "far": ((s * 16, py + 9, pz + 6), (0, py - 2, pz + 1), dict(lens=50)),
    }


def pair(side, view, out_dir, tag, objs=("STOCK-lod0", "GEO-lod0"), size=(400, 400), look="matcap", **kw):
    eye, tgt, opt = views(side)[view]
    opt = dict(opt, **kw)
    paths = []
    for ob in objs:
        p = f"{out_dir}/{tag}_{view}_{'R' if side > 0 else 'L'}_{ob}.png"
        shoot(eye, tgt, p, [ob], size=size, look=look, **opt)
        paths.append(p)
    return paths
