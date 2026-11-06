"""Renders what the live 3D view shows (OpenGL, view_context) to a PNG, at the region's size; render settings restored.
Used when the window screenshot is unavailable (window covered or minimised) and for before/after sheets.

  import blender_skill_viewshot as vs; vs.shot(path)                       the user's view as it is
  vs.shot(path, loc=..., rot=..., dist=...)                                another view, the user's restored afterwards
  vs.shot(path, rake=True)                                                 grazing light: scene lights and world (LGT-rake)
  vs.shot(path, scale=3)                                                   same framing, 3x the pixels (for close crops)
"""
import bpy


def _area():
    area = [a for a in bpy.context.screen.areas if a.type == "VIEW_3D"][0]
    return area, [r for r in area.regions if r.type == "WINDOW"][0]


def shot(path, loc=None, rot=None, dist=None, rake=False, scale=1):
    sc = bpy.context.scene
    area, region = _area()
    rv, sp = area.spaces[0].region_3d, area.spaces[0]
    keep_view = (rv.view_location.copy(), rv.view_rotation.copy(), rv.view_distance)
    keep_r = (sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage, sc.render.image_settings.file_format)
    sh = sp.shading
    keep_sh = (sh.use_scene_lights, sh.use_scene_world, sh.studio_light if not sh.use_scene_world else None)
    try:
        if loc is not None:
            rv.view_location = loc
        if rot is not None:
            rv.view_rotation = rot
        if dist is not None:
            rv.view_distance = dist
        if rake:
            sh.use_scene_lights, sh.use_scene_world = True, True
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = region.width * scale, region.height * scale, 100
        sc.render.image_settings.file_format = "PNG"
        with bpy.context.temp_override(area=area, region=region):
            bpy.ops.render.opengl(view_context=True)
        bpy.data.images["Render Result"].save_render(path)
    finally:
        rv.view_location, rv.view_rotation, rv.view_distance = keep_view
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage, sc.render.image_settings.file_format = keep_r
        sh.use_scene_lights, sh.use_scene_world = keep_sh[0], keep_sh[1]
    return path
