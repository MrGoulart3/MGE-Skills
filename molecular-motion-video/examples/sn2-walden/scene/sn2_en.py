"""SN2: trajetória reativa em Å, Geometry Nodes e timing externo.

Utilitários de timeline, câmera e geometria independentes de outras cenas.
A cena exige a trajetória real e os eventos calculados.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys

import bpy
from bpy.app.handlers import persistent
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import numpy as np

DIRECTORY = Path(__file__).resolve().parent
PROJECT = DIRECTORY.parent
OUTPUT = PROJECT / "render" / "sn2_en"
SEED = 104524
STYLE = json.loads((DIRECTORY / "style.json").read_text())
RADII = {"C": .55, "Br": 1.05, "Cl": .95, "H": .30, "O": .40}


@dataclass(frozen=True)
class Timeline:
    fps: int
    scenes: dict[str, tuple[float, float]]
    events: dict[str, float]
    duration: float
    frames: int

    @classmethod
    def read(cls, path: Path) -> Timeline:
        payload = json.loads(path.read_text())
        fps, duration, frames = payload["fps"], float(payload["duration"]), payload["frames"]
        if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 120:
            raise ValueError("fps inválido.")
        if isinstance(frames, bool) or not isinstance(frames, int) or frames < 1:
            raise ValueError("frames inválido.")
        scenes, previous = {}, 0.
        for name in "ABCDEF":
            start, end = map(float, payload["scenes"][name])
            if not all(math.isfinite(v) for v in (start, end)) or abs(start - previous) > 1e-6 or end - start < 2 / fps:
                raise ValueError(f"Cena {name} inválida/descontínua.")
            scenes[name], previous = (start, end), end
        if not math.isfinite(duration) or abs(duration - previous) > 1e-6 or abs(frames - duration * fps) > 1:
            raise ValueError("duration/frames incompatíveis.")
        events = {k: float(v) for k, v in payload["events"].items()}
        for name, value in events.items():
            if not math.isfinite(value) or not 0 <= value < duration:
                raise ValueError(f"Evento {name} inválido.")
        return cls(fps, scenes, events, duration, frames)

    def frame(self, seconds: float) -> int:
        return min(self.frames, max(1, round(seconds * self.fps) + 1))

    def seconds(self, frame: float) -> float:
        return (frame - 1) / self.fps

    def at(self, name: str, fraction: float) -> float:
        start, end = self.scenes[name]
        return start + (end - start) * fraction

    def preview_frames(self) -> list[int]:
        # Limites de cenas e palavras ancoradas (~12–20 quadros).
        return sorted({1, self.frames, *(self.frame(v[0]) for v in self.scenes.values()),
                       *(self.frame(v) for v in self.events.values())})


def ease(value: float, start: float, end: float) -> float:
    if end <= start:
        raise ValueError("Intervalo de interpolação inválido.")
    ratio = min(1.0, max(0.0, (value - start) / (end - start)))
    return ratio ** 3 * (ratio * (ratio * 6 - 15) + 10)


def sample_path(seconds: float, knots: list[tuple[float, Vector]]) -> Vector:
    if seconds <= knots[0][0]:
        return knots[0][1].copy()
    for (start, first), (end, last) in zip(knots, knots[1:]):
        if seconds <= end:
            return first.lerp(last, ease(seconds, start, end))
    return knots[-1][1].copy()


def linear_color(hex_color: str) -> tuple[float, float, float, float]:
    value = hex_color.lstrip("#")
    values = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
                 for v in values) + (1.0,)


def material(name: str, color: str, roughness: float = 0.45,
             transmission: float = 0.0, subsurface: float = 0.0,
             sheen: float = 0.0, emission: float = 0.0,
             ior: float = 1.5) -> bpy.types.Material:
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    rgba = linear_color(color)
    result.diffuse_color = rgba
    shader = result.node_tree.nodes.get("Principled BSDF")
    for socket, value in {"Base Color": rgba, "Roughness": roughness, "IOR": ior,
                          "Transmission Weight": transmission,
                          "Subsurface Weight": subsurface, "Sheen Weight": sheen,
                          "Emission Color": rgba, "Emission Strength": emission}.items():
        shader.inputs[socket].default_value = value
    return result




def screen_bounds(scene: bpy.types.Scene, bounds: list[Vector]) -> tuple[float, ...]:
    points = [world_to_camera_view(scene, scene.camera, p) for p in bounds]
    return min(p.x for p in points), max(p.x for p in points), min(p.y for p in points), max(p.y for p in points)


def solve_framing(scene: bpy.types.Scene, bounds: list[Vector], center: Vector,
                  direction: Vector, height: float, center_x: float) -> tuple[Vector, Vector]:
    camera = scene.camera
    distance, target = 45.0, center.copy()
    camera.rotation_mode = "QUATERNION"
    for _ in range(300):
        camera.location = center + direction * distance
        camera.rotation_quaternion = (target - camera.location).to_track_quat("-Z", "Y")
        bpy.context.view_layer.update()
        left, right, bottom, top = screen_bounds(scene, bounds)
        ratio, horizontal, vertical = (top - bottom) / height, (left + right) / 2, (bottom + top) / 2
        if max(abs(ratio - 1), abs(horizontal - center_x), abs(vertical - 0.5)) < 1e-4:  # ~0,1 px em 1080p
            break
        extent = (camera.location - target).length * camera.data.sensor_width / camera.data.lens
        target -= camera.rotation_quaternion @ Vector((extent * (center_x - horizontal),
                                                       extent * 9 / 16 * (0.5 - vertical), 0))
        distance *= ratio
    else:
        raise AssertionError("O enquadramento não convergiu.")
    return camera.location.copy(), target.copy()




def project_anchor(scene: bpy.types.Scene, position: Vector) -> dict:
    point = world_to_camera_view(scene, scene.camera, position)
    return {"x": round(point.x * 1920, 4), "y": round((1 - point.y) * 1080, 4),
            "visivel": scene.camera.data.clip_start < point.z < scene.camera.data.clip_end
            and 0 <= point.x <= 1 and 0 <= point.y <= 1,
            "profundidade": round(point.z, 5)}




def frame_range(value: str) -> tuple[int, int]:
    try:
        first, last = (int(part) for part in value.split("-"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use --frames a-b, por exemplo 1-120.") from error
    if not 1 <= first <= last:
        raise argparse.ArgumentTypeError("Os quadros devem satisfazer 1 <= a <= b.")
    return first, last


def thread_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--threads exige um inteiro.") from error
    if not 1 <= count <= 1024:
        raise argparse.ArgumentTypeError("--threads deve estar entre 1 e 1024.")
    return count



def atom_material(element: str) -> bpy.types.Material:
    color = STYLE['elements'][element]
    result = material(element, color, roughness=.26,
                      subsurface=.055 if element in ('Na', 'Cl') else .02,
                      sheen=.20 if element == 'Na' else .12, emission=.05)
    nodes, links = result.node_tree.nodes, result.node_tree.links
    shader = nodes.get('Principled BSDF')
    attrs = {}
    for name in ('highlight', 'glow', 'fade'):
        node = nodes.new('ShaderNodeAttribute')
        node.attribute_name = name
        # GN instancia por ponto: atributos são lidos do instanciador.
        node.attribute_type = 'INSTANCER'
        attrs[name] = node.outputs['Fac']
    mix = nodes.new('ShaderNodeMixRGB')
    mix.inputs[1].default_value = linear_color(color)
    charge = STYLE['charges'].get(element, STYLE['charges']['delta_minus' if element == 'O' else 'delta_plus'])
    mix.inputs[2].default_value = linear_color(charge)
    links.new(attrs['glow'], mix.inputs[0])
    links.new(mix.outputs[0], shader.inputs['Emission Color'])
    facing = nodes.new('ShaderNodeLayerWeight')
    rim = nodes.new('ShaderNodeMath'); rim.operation = 'POWER'; rim.inputs[1].default_value = 3
    links.new(facing.outputs['Facing'], rim.inputs[0])
    add = nodes.new('ShaderNodeMath'); add.operation = 'ADD'
    links.new(attrs['highlight'], add.inputs[0]); links.new(attrs['glow'], add.inputs[1])
    strength = nodes.new('ShaderNodeMath'); strength.operation = 'MULTIPLY'
    links.new(add.outputs[0], strength.inputs[0]); links.new(rim.outputs[0], strength.inputs[1])
    lift = nodes.new('ShaderNodeMath'); lift.operation = 'MULTIPLY_ADD'
    lift.inputs[1].default_value = .7; lift.inputs[2].default_value = .16 if element == 'Na' else .06
    links.new(strength.outputs[0], lift.inputs[0]); links.new(lift.outputs[0], shader.inputs['Emission Strength'])
    dim = nodes.new('ShaderNodeMixRGB')
    dim.inputs[1].default_value = tuple(v * .48 for v in linear_color(color)[:3]) + (1.,)
    dim.inputs[2].default_value = linear_color(color)
    links.new(attrs['highlight'], dim.inputs[0]); links.new(dim.outputs[0], shader.inputs['Base Color'])
    water_dim = nodes.new('ShaderNodeMixRGB')
    water_dim.blend_type = 'MULTIPLY'
    water_dim.inputs[0].default_value = 1.
    water_dim.inputs[2].default_value = (.6, .6, .6, 1.)
    water_mask = nodes.new('ShaderNodeMath'); water_mask.operation = 'LESS_THAN'
    water_mask.inputs[1].default_value = .9
    links.new(attrs['fade'], water_mask.inputs[0])
    links.new(water_mask.outputs[0], water_dim.inputs[0])
    links.new(dim.outputs[0], water_dim.inputs[1])
    links.new(water_dim.outputs[0], shader.inputs['Base Color'])
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    blend = nodes.new('ShaderNodeMixShader')
    links.new(attrs['fade'], blend.inputs[0]); links.new(transparent.outputs[0], blend.inputs[1])
    links.new(shader.outputs[0], blend.inputs[2])
    links.new(blend.outputs[0], nodes.get('Material Output').inputs['Surface'])
    return result


def point_object(element: str, count: int, mat: bpy.types.Material) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(element + ' pontos')
    mesh.from_pydata([(0., 0., 0.)] * count, [], [])
    for name in ('highlight', 'glow', 'fade', 'radius_scale'):
        mesh.attributes.new(name, 'FLOAT', 'POINT')
    obj = bpy.data.objects.new(element, mesh); bpy.context.scene.collection.objects.link(obj)
    obj.cycles.use_deform_motion = True
    tree = bpy.data.node_groups.new(element + ' instâncias', 'GeometryNodeTree')
    tree.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    tree.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    nodes, links = tree.nodes, tree.links
    incoming, outgoing = nodes.new('NodeGroupInput'), nodes.new('NodeGroupOutput')
    sphere = nodes.new('GeometryNodeMeshUVSphere')
    sphere.inputs['Segments'].default_value = 24; sphere.inputs['Rings'].default_value = 16
    sphere.inputs['Radius'].default_value = RADII[element]
    smooth = nodes.new('GeometryNodeSetShadeSmooth')
    links.new(sphere.outputs['Mesh'], smooth.inputs['Geometry'])
    set_mat = nodes.new('GeometryNodeSetMaterial'); set_mat.inputs['Material'].default_value = mat
    links.new(smooth.outputs['Geometry'], set_mat.inputs['Geometry'])
    instances = nodes.new('GeometryNodeInstanceOnPoints')
    links.new(incoming.outputs['Geometry'], instances.inputs['Points'])
    links.new(set_mat.outputs['Geometry'], instances.inputs['Instance'])
    fade = nodes.new('GeometryNodeInputNamedAttribute'); fade.data_type = 'FLOAT'
    fade.inputs['Name'].default_value = 'radius_scale'
    links.new(fade.outputs['Attribute'], instances.inputs['Scale'])
    links.new(instances.outputs['Instances'], outgoing.inputs['Geometry'])
    obj.modifiers.new('Instâncias por espécie', 'NODES').node_group = tree
    return obj


def bond_object(trajectory: Trajectory) -> bpy.types.Object:
    mesh = bpy.data.meshes.new('O–H arestas')
    count = len(trajectory.waters)
    edges = [(i*3, i*3+j) for i in range(count) for j in (1, 2)]
    mesh.from_pydata([(0., 0., 0.)] * (count*3), edges, [])
    for name in ('highlight', 'glow', 'fade'):
        mesh.attributes.new(name, 'FLOAT', 'POINT')
    obj = bpy.data.objects.new('Ligações O–H', mesh); bpy.context.scene.collection.objects.link(obj)
    obj.cycles.use_deform_motion = True
    tree = bpy.data.node_groups.new('Arestas → curvas → tubos', 'GeometryNodeTree')
    tree.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    tree.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    nodes, links = tree.nodes, tree.links
    incoming, outgoing = nodes.new('NodeGroupInput'), nodes.new('NodeGroupOutput')
    curves = nodes.new('GeometryNodeMeshToCurve')
    fade = nodes.new('GeometryNodeInputNamedAttribute'); fade.data_type = 'FLOAT'
    fade.inputs['Name'].default_value = 'fade'
    hidden = nodes.new('ShaderNodeMath'); hidden.operation = 'LESS_THAN'
    hidden.inputs[1].default_value = .001
    links.new(fade.outputs['Attribute'], hidden.inputs[0])
    delete = nodes.new('GeometryNodeDeleteGeometry'); delete.domain = 'EDGE'
    links.new(incoming.outputs['Geometry'], delete.inputs['Geometry'])
    links.new(hidden.outputs[0], delete.inputs['Selection'])
    radius = nodes.new('GeometryNodeSetCurveRadius')
    profile = nodes.new('GeometryNodeCurvePrimitiveCircle')
    profile.inputs['Radius'].default_value = .0675; profile.inputs['Resolution'].default_value = 8
    tubes = nodes.new('GeometryNodeCurveToMesh')
    links.new(delete.outputs['Geometry'], curves.inputs['Mesh'])
    links.new(curves.outputs['Curve'], radius.inputs['Curve'])
    links.new(fade.outputs['Attribute'], radius.inputs['Radius'])
    links.new(radius.outputs['Curve'], tubes.inputs['Curve'])
    links.new(profile.outputs['Curve'], tubes.inputs['Profile Curve'])
    mat = atom_material('H')
    for node in mat.node_tree.nodes:
        if node.type == 'ATTRIBUTE':
            node.attribute_type = 'GEOMETRY'
    set_mat = nodes.new('GeometryNodeSetMaterial'); set_mat.inputs['Material'].default_value = mat
    links.new(tubes.outputs['Mesh'], set_mat.inputs['Geometry'])
    smooth = nodes.new('GeometryNodeSetShadeSmooth')
    links.new(set_mat.outputs['Geometry'], smooth.inputs['Geometry'])
    links.new(smooth.outputs['Geometry'], outgoing.inputs['Geometry'])
    obj.modifiers.new('Tubos O–H', 'NODES').node_group = tree
    return obj


def world_and_compositor(scene: bpy.types.Scene) -> None:
    world = bpy.data.worlds.new('Petróleo → índigo'); scene.world = world; world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    output, background = nodes.new('ShaderNodeOutputWorld'), nodes.new('ShaderNodeBackground')
    coords, separate, ramp = nodes.new('ShaderNodeTexCoord'), nodes.new('ShaderNodeSeparateXYZ'), nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.interpolation = 'EASE'
    ramp.color_ramp.elements[0].color = linear_color(STYLE['background']['bottom'])
    ramp.color_ramp.elements[1].color = linear_color(STYLE['background']['top'])
    background.inputs['Strength'].default_value = .8
    links.new(coords.outputs['Window'], separate.inputs[0]); links.new(separate.outputs['Y'], ramp.inputs[0])
    links.new(ramp.outputs[0], background.inputs['Color']); links.new(background.outputs[0], output.inputs['Surface'])
    world.mist_settings.start, world.mist_settings.depth = 15, 70
    world.mist_settings.falloff, world.mist_settings.use_mist = 'QUADRATIC', True
    scene.use_nodes = True
    nodes, links = scene.node_tree.nodes, scene.node_tree.links; nodes.clear()
    layers = nodes.new('CompositorNodeRLayers')
    strength = nodes.new('CompositorNodeMath'); strength.operation = 'MULTIPLY'; strength.inputs[1].default_value = .22
    mist = nodes.new('CompositorNodeMixRGB'); mist.inputs[2].default_value = linear_color(STYLE['background']['bottom'])
    glare = nodes.new('CompositorNodeGlare'); glare.glare_type = 'FOG_GLOW'; glare.quality = 'HIGH'
    glare.threshold, glare.size, glare.mix = 1.2, 7, -.65
    output = nodes.new('CompositorNodeComposite')
    links.new(layers.outputs['Mist'], strength.inputs[0]); links.new(strength.outputs[0], mist.inputs[0])
    links.new(layers.outputs['Image'], mist.inputs[1]); links.new(mist.outputs[0], glare.inputs['Image'])
    links.new(glare.outputs[0], output.inputs['Image'])
    for name, position, energy, size, color in (
            ('Principal', (-12, -18, 18), 2600, 12, STYLE['elements']['H']),
            ('Contraluz', (12, 8, 14), 3200, 10, STYLE['ui']['label_border']),
            ('Preenchimento', (-10, 12, -2), 1000, 12, '#7FD0EC')):
        data = bpy.data.lights.new(name, 'AREA'); data.energy, data.shape, data.size = energy, 'DISK', size
        data.color = linear_color(color)[:3]
        obj = bpy.data.objects.new(name, data); scene.collection.objects.link(obj); obj.location = position
        obj.rotation_euler = (-obj.location).to_track_quat('-Z', 'Y').to_euler()
    rng = np.random.default_rng(SEED)
    mat = material('Bokeh azul', '#7FD0EC', emission=.22, roughness=.4)
    for index in range(12):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=float(rng.uniform(.25, .65)),
                                            location=(rng.uniform(-30, 30), rng.uniform(28, 38), rng.uniform(-20, 20)))
        obj = bpy.context.object; obj.name = f'Bokeh {index:02d}'; obj.data.materials.append(mat)
        for face in obj.data.polygons:
            face.use_smooth = True


def configure_render(scene: bpy.types.Scene, args: argparse.Namespace, timeline: Timeline) -> None:
    scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'
    scene.render.threads_mode, scene.render.threads = 'FIXED', args.threads
    scene.render.fps = timeline.fps; scene.frame_start, scene.frame_end = 1, timeline.frames
    scene.render.resolution_x, scene.render.resolution_y = (1920, 1080) if args.final or args.check else (640, 360)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '16' if args.final else '8'
    scene.render.film_transparent = False; scene.render.use_file_extension = True
    scene.render.use_motion_blur, scene.render.motion_blur_shutter = args.final, .5
    scene.render.use_persistent_data = True
    scene.render.use_overwrite, scene.render.use_placeholder = False, True
    scene.render.use_lock_interface = True
    scene.cycles.samples = args.samples or (64 if args.final else 16)
    scene.cycles.seed, scene.cycles.use_animated_seed = SEED, False
    scene.cycles.use_adaptive_sampling, scene.cycles.adaptive_threshold = True, .02
    scene.cycles.use_denoising = True; scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    scene.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    scene.cycles.max_bounces, scene.cycles.transmission_bounces = 10, 8
    scene.cycles.glossy_bounces, scene.cycles.diffuse_bounces = 4, 2
    scene.cycles.transparent_max_bounces = 16
    scene.cycles.sample_clamp_direct, scene.cycles.sample_clamp_indirect = 4, 3
    scene.cycles.caustics_reflective = scene.cycles.caustics_refractive = False
    scene.view_layers[0].use_pass_mist = True
    scene.view_settings.view_transform = 'AgX'; scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.unit_settings.system = 'NONE'; scene['escala'] = '1 unidade = 1 Å'


class Trajectory:
    """Trajetória original em Å e interpolação local, sem filtragem temporal."""

    def __init__(self, path: Path, events: Path | None = None) -> None:
        with np.load(path, allow_pickle=False) as data:
            self.positions = data['positions'].astype(float)
            self.time = data['time_fs'].astype(float)
            self.elements = data['element'].astype(str)
            self.molecule = data['molecule']
            self.scalars = {k: data[k].astype(float) for k in
                            ('d_CCl', 'd_CBr', 'xi', 'umbrella', 'angle')}
        self.events = json.loads((events or path.with_name('events.json')).read_text())['events']
        if (self.positions.shape != (len(self.time), len(self.elements), 3)
                or not np.isfinite(self.positions).all()
                or not np.all(np.diff(self.time) > 0)
                or list(self.elements[:6]) != ['C', 'Br', 'Cl', 'H', 'H', 'H']):
            raise ValueError('Trajetória inválida ou ordem do soluto incorreta.')
        self.groups = {e: np.flatnonzero(self.elements == e) for e in set(self.elements)}
        self.waters = []
        for identifier in np.unique(self.molecule[6:]):
            ids = np.flatnonzero(self.molecule == identifier)
            oxygen = ids[self.elements[ids] == 'O']
            hydrogen = ids[self.elements[ids] == 'H']
            if len(oxygen) != 1 or len(hydrogen) != 2:
                raise ValueError('Água sem topologia O–H–H.')
            self.waters.append([oxygen[0], *hydrogen])
        self.waters = np.asarray(self.waters, dtype=int).reshape(-1, 3)

    def sample(self, time: float) -> np.ndarray:
        i = int(np.clip(np.searchsorted(self.time, time, side='right') - 1,
                        0, len(self.time) - 2))
        u = float(np.clip((time-self.time[i])/(self.time[i+1]-self.time[i]), 0, 1))
        a, b, c, d = self.positions[np.clip([i-1, i, i+1, i+2], 0, len(self.time)-1)]
        return .5*((2*b)+(-a+c)*u+(2*a-5*b+4*c-d)*u*u+(-a+3*b-3*c+d)*u**3)

    def values(self, time: float) -> dict:
        return {k: float(np.interp(time, self.time, v)) for k, v in self.scalars.items()}


class TimeMap:
    """Mapa vídeo (s) → DM (fs): PCHIP (Fritsch–Carlson) pelas âncoras, monotônico e com derivada contínua.
    Âncoras = eventos calculados (events.json) presos a palavras da narração; câmera lenta em torno do TS."""

    def __init__(self, timeline: Timeline, md: Trajectory) -> None:
        e, ev = timeline.events, md.events
        ts = ev['ts']['time_fs']
        self.pins = [(0., md.time[0]),
                     (e['label_cl'], ev['approach']['time_fs']),
                     (e['axis'], ev['backside']['time_fs']),
                     (e['bonds'], ts-60.), (e['stretch'], ts-25.), (e['ts'], ts),
                     (e['flat'], ts+12.), (e['flip'], ts+30.),
                     (e['leave'], ev['leave']['time_fs']),
                     (timeline.duration, min(md.time[-1], ts+250.))]
        self.x, self.y = (np.array(v, dtype=float) for v in zip(*self.pins))
        if not (np.all(np.diff(self.x) > 0) and np.all(np.diff(self.y) > 0)):
            raise ValueError('Timing incompatível com a ordem dos eventos físicos.')
        h = np.diff(self.x); d = np.diff(self.y)/h
        m = np.empty_like(self.y); m[0], m[-1] = d[0], d[-1]
        for k in range(1, len(m)-1):
            w1, w2 = 2*h[k]+h[k-1], h[k]+2*h[k-1]
            m[k] = (w1+w2)/(w1/d[k-1]+w2/d[k])  # média harmônica ponderada (Fritsch–Butland): > 0, monotônico
        self.h, self.m = h, m

    def __call__(self, seconds: float) -> float:
        i = int(np.clip(np.searchsorted(self.x, seconds, side='right')-1, 0, len(self.x)-2))
        h = self.h[i]; u = float(np.clip((seconds-self.x[i])/h, 0, 1))
        h00, h10, h01, h11 = 2*u**3-3*u**2+1, u**3-2*u**2+u, -2*u**3+3*u**2, u**3-u**2
        return float(h00*self.y[i]+h10*h*self.m[i]+h01*self.y[i+1]+h11*h*self.m[i+1])


class Animation:
    """Atualiza pontos, tubos e câmera também nos subquadros do Cycles."""

    def __init__(self, scene, timeline, md, mapping) -> None:
        self.scene, self.timeline, self.md, self.mapping = scene, timeline, md, mapping
        self.objects = {e: point_object(e, len(ids), atom_material(e))
                        for e, ids in md.groups.items()}
        self.water = bond_object(md)
        self.axis_dashes = []
        axis_mat = material('Eixo de ataque', '#7FD0EC', emission=.2)
        for index in range(14):
            bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=1, depth=1)
            obj = bpy.context.object
            obj.name = f'Eixo tracejado {index}'
            obj.data.materials.append(axis_mat)
            self.axis_dashes.append(obj)
        self.bonds = []
        for index in range(1, 6):
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=1, depth=1)
            obj = bpy.context.object
            obj.name = f'C–{index}'
            mat = material(obj.name, STYLE['elements'][md.elements[index]], roughness=.3)
            obj.data.materials.append(mat)
            if index <= 2:
                nodes, links = mat.node_tree.nodes, mat.node_tree.links
                coords = nodes.new('ShaderNodeTexCoord')
                separate = nodes.new('ShaderNodeSeparateXYZ')
                ramp = nodes.new('ShaderNodeValToRGB')
                ramp.color_ramp.elements[0].position = .48
                ramp.color_ramp.elements[1].position = .52
                ramp.color_ramp.elements[0].color = linear_color(STYLE['elements']['Cl'])
                ramp.color_ramp.elements[1].color = linear_color(STYLE['elements']['Br'])
                links.new(coords.outputs['Generated'], separate.inputs[0])
                links.new(separate.outputs['Z'], ramp.inputs[0])
                shader = nodes.get('Principled BSDF')
                links.new(ramp.outputs['Color'], shader.inputs['Base Color'])
                links.new(ramp.outputs['Color'], shader.inputs['Emission Color'])
            self.bonds.append(obj)
        data = bpy.data.cameras.new('Câmera SN2')
        self.camera = bpy.data.objects.new('Câmera SN2', data)
        scene.collection.objects.link(self.camera); scene.camera = self.camera
        data.lens, data.clip_start, data.clip_end = 48, .1, 400
        data.dof.use_dof, data.dof.aperture_fstop = True, 5.6
        self.camera.rotation_mode = 'QUATERNION'
        self.camera_samples = []

    def camera_pose(self, seconds, positions) -> None:
        t = self.timeline
        axis = Vector(positions[1]-positions[2]).normalized()
        ts_positions = self.md.sample(self.md.events['ts']['time_fs'])
        normal = Vector(ts_positions[3]-ts_positions[0])
        normal -= axis*normal.dot(axis)
        if normal.length < .1:
            normal = axis.cross(Vector((0, 1, 0)))
        normal.normalize()
        # Coloca Cl à esquerda e Br à direita no referencial da câmera.
        orbit = math.radians(35)*ease(seconds, *t.scenes['D'])
        normal = normal*math.cos(orbit)+axis.cross(normal)*math.sin(orbit)
        direction = normal*math.cos(math.radians(20)*(1-ease(seconds, t.scenes['C'][0], t.scenes['D'][0])))
        direction += axis*math.sin(math.radians(20)*(1-ease(seconds, t.scenes['C'][0], t.scenes['D'][0])))
        direction.normalize()
        center = Vector(positions[:3].mean(axis=0))
        span = float(np.linalg.norm(positions[1]-positions[2]))+2.1
        width = span / (.60 + .08*ease(seconds, t.scenes['B'][0], t.scenes['C'][0]))
        width *= 1.35-.35*ease(seconds, 0, t.scenes['B'][0])
        end = ease(seconds, t.scenes['F'][0], t.events['title'])
        width *= (1+.12*ease(seconds, *t.scenes['E']))*(1+end*.65)
        center += axis*(.16*ease(seconds, t.scenes['E'][0], t.events['leave']))
        target = center-axis*(width*.16*end)
        self.camera.location = target+direction*(width*self.camera.data.lens/self.camera.data.sensor_width)
        # Roll explícito: eixo de reação horizontal, mantendo continuidade.
        right = axis-direction*axis.dot(direction); right.normalize()
        from mathutils import Matrix
        true_up = direction.cross(right).normalized()
        self.camera.rotation_quaternion = Matrix((right, true_up, direction)).transposed().to_quaternion()
        # Corrige a média projetada dos três átomos, inclusive com perspectiva.
        for _ in range(3):
            depths = [(Vector(p)-self.camera.location).dot(-direction) for p in positions[:3]]
            projected = [.5+(Vector(p)-self.camera.location).dot(right)
                         *self.camera.data.lens/self.camera.data.sensor_width/depth
                         for p, depth in zip(positions[:3], depths)]
            correction = (.5+.16*end-sum(projected)/3)
            self.camera.location -= right*(correction*width)
        self.camera.data.dof.focus_distance = (Vector(positions[0])-self.camera.location).length

    def water_fades(self) -> np.ndarray:
        """Aplica névoa e libera os três raios de visão do soluto."""
        centers = self.positions[self.md.waters].mean(axis=1)
        camera = np.array(self.camera.location)
        distance = np.linalg.norm(centers-self.positions[0], axis=1)
        close_view = self.timeline.seconds(self.scene.frame_current) >= self.timeline.scenes['B'][0]
        haze = np.clip((13.-distance)/4. if close_view else (10.-distance)/3., 0., 1.)
        visibility = haze*haze*(3-2*haze)
        near_radius = 8. if close_view else 6.
        cull_radius = 6. if close_view else 4.5
        fade_width = 1. if close_view else .75
        near = np.clip((np.linalg.norm(centers-camera, axis=1)-near_radius)/fade_width, 0., 1.)
        visibility *= near*near*(3-2*near)
        for target in self.positions[:3]:
            ray = target-camera
            length = np.linalg.norm(ray)
            direction = ray/length
            along = (centers-camera) @ direction
            radial = np.linalg.norm(centers-camera-along[:, None]*direction, axis=1)
            cull = np.clip((radial-cull_radius)/fade_width, 0., 1.)
            visibility *= np.where((along > 0) & (along < length), cull*cull*(3-2*cull), 1.)
        fades = np.ones(len(self.md.elements))
        fades[self.md.waters.ravel()] = np.repeat((.35 if close_view else .22)*visibility, 3)
        return fades

    def update(self, frame: float) -> None:
        seconds = self.timeline.seconds(frame)
        self.t_fs = self.mapping(seconds)
        self.positions = self.md.sample(self.t_fs)
        self.camera_pose(seconds, self.positions)
        fades = self.water_fades()
        glow = 1-ease(abs(seconds-self.timeline.events['ts']), 0, .8)
        for element, ids in self.md.groups.items():
            mesh = self.objects[element].data
            mesh.vertices.foreach_set('co', self.positions[ids].ravel())
            fade = fades[ids]
            mesh.attributes['fade'].data.foreach_set('value', fade)
            water_scale = .65 if seconds >= self.timeline.scenes['B'][0] else .75
            scales = np.where(ids >= 6, water_scale, 1.)
            mesh.attributes['radius_scale'].data.foreach_set('value', scales)
            mesh.attributes['highlight'].data.foreach_set('value', np.ones(len(ids)))
            mesh.attributes['glow'].data.foreach_set('value', np.where(ids == 0, glow, 0.))
            mesh.update()
        water = self.water.data
        water.vertices.foreach_set('co', self.positions[self.md.waters.ravel()].ravel())
        for name, value in [('fade', .35), ('highlight', .35), ('glow', 0.)]:
            values = fades[self.md.waters.ravel()] if name == 'fade' else np.full(len(water.vertices), value)
            water.attributes[name].data.foreach_set('value', values)
        water.update()
        for index, obj in enumerate(self.axis_dashes):
            delta = Vector(self.positions[1]-self.positions[2])
            obj.hide_render = not (self.timeline.events['axis'] <= seconds < self.timeline.events['bonds'])
            obj.location = Vector(self.positions[2])+delta*((index+.25)/14)
            obj.rotation_euler = delta.to_track_quat('Z', 'Y').to_euler()
            obj.scale = (.025, .025, delta.length/28)
        for index, obj in enumerate(self.bonds, 1):
            delta = Vector(self.positions[index]-self.positions[0]); distance = delta.length
            r0 = 1.95 if index == 1 else 1.79 if index == 2 else 1.09
            order = math.exp((r0-distance)/.30)
            visible = order > (.06 if index <= 2 else .08)
            obj.hide_render = not visible
            obj.location = (self.positions[index]+self.positions[0])/2
            obj.rotation_euler = delta.to_track_quat('Z', 'Y').to_euler()
            radius = .05+.11*min(order, 1) if index <= 2 else .16*min(order, 1)
            obj.scale = (radius, radius, distance)
            shader = obj.data.materials[0].node_tree.nodes.get('Principled BSDF')
            shader.inputs['Alpha'].default_value = (1. if index <= 2 else min(order, 1)) if visible else 0
            shader.inputs['Emission Strength'].default_value = min(order, 1)*(.05+glow*(index <= 2))
        bpy.context.view_layer.update()

    def anchors(self) -> dict:
        bpy.context.view_layer.update()
        p = self.positions
        points = dict(zip(('C', 'Br', 'Cl', 'H1', 'H2', 'H3'), p[:6]))
        points.update(mid_CCl=(p[0]+p[2])/2, mid_CBr=(p[0]+p[1])/2)
        return {**{k: project_anchor(self.scene, Vector(v)) for k, v in points.items()},
                't_fs': self.t_fs, **self.md.values(self.t_fs)}


ACTIVE = None


@persistent
def update_trajectory(scene, depsgraph=None) -> None:
    if ACTIVE is not None:
        ACTIVE.update(scene.frame_current+scene.frame_subframe)


def export_anchors(animation) -> None:
    frames = {}
    for frame in range(1, animation.timeline.frames+1):
        animation.scene.frame_set(frame)
        frames[str(frame)] = animation.anchors()
    payload = dict(fps=animation.timeline.fps, width=1920, height=1080, frames=frames)
    (PROJECT/'anchors.json').write_text(json.dumps(payload, indent=2)+'\n')


def water_visibility_metrics(animation: Animation, *, raw: bool = False) -> float:
    """Mede oclusão do soluto por fração do quadro; raw retorna a união bruta."""
    scene, p, md = animation.scene, animation.positions, animation.md
    bpy.context.view_layer.update()
    camera = scene.camera
    subject_depth = max(world_to_camera_view(scene, camera, Vector(v)).z for v in p[:3])
    coverage = np.zeros((216, 384), dtype=bool)
    fades = animation.water_fades()[md.waters[:, 0]]
    up = camera.rotation_quaternion @ Vector((0, 1, 0))
    silhouette = np.zeros_like(coverage)
    if not raw:
        yy, xx = np.ogrid[:216, :384]
        projected = []
        for position in p[:3]:
            center = Vector(position)
            point = world_to_camera_view(scene, camera, center)
            edge = world_to_camera_view(scene, camera, center+up*.5)
            radius_px = abs(edge.y-point.y)*216
            x, y = point.x*384, point.y*216
            projected.append((x, y, radius_px))
            silhouette |= (xx+.5-x)**2+(yy+.5-y)**2 <= radius_px**2
        for index in (1, 2):
            x, y, radius = projected[0]
            end_x, end_y, end_radius = projected[index]
            dx, dy = end_x-x, end_y-y
            length_squared = dx*dx+dy*dy
            if length_squared <= 1e-12:
                continue
            along = np.clip(((xx+.5-x)*dx+(yy+.5-y)*dy)/length_squared, 0., 1.)
            segment_radius = radius+along*(end_radius-radius)
            silhouette |= ((xx+.5-x-along*dx)**2
                           +(yy+.5-y-along*dy)**2 <= segment_radius**2)
    for water, fade in zip(md.waters, fades):
        if fade <= (.001 if raw else .05):
            continue
        center = Vector(p[water].mean(axis=0))
        # Esfera envolvente inclui os átomos e os tubos O–H; não reduz raio pela opacidade.
        radius = max((Vector(p[i])-center).length+.75*RADII[md.elements[i]] for i in water)
        point = world_to_camera_view(scene, camera, center)
        if point.z+radius <= camera.data.clip_start or point.z-radius >= subject_depth:
            continue
        if point.z <= radius:
            coverage[:] = True
            break
        edge = world_to_camera_view(scene, camera, center+up*radius)
        radius_px = abs(edge.y-point.y)*216*point.z/(point.z-radius)
        x, y = point.x*384, point.y*216
        left, right = max(0, math.floor(x-radius_px)), min(384, math.ceil(x+radius_px))
        bottom, top = max(0, math.floor(y-radius_px)), min(216, math.ceil(y+radius_px))
        if right > left and top > bottom:
            yy, xx = np.ogrid[bottom:top, left:right]
            coverage[bottom:top, left:right] |= (xx+.5-x)**2+(yy+.5-y)**2 <= radius_px**2
    return float((coverage if raw else coverage & silhouette).mean())


def validate(animation) -> None:
    md, t, mapping = animation.md, animation.timeline, animation.mapping
    ch = np.linalg.norm(md.positions[:, 3:6]-md.positions[:, :1], axis=2).mean()
    print(f'C–H médio: {ch:.5f} Å')
    assert abs(ch-1.09) <= .08, 'C–H fora do intervalo'
    assert md.scalars['d_CBr'][0] < 2.4 and md.scalars['d_CCl'][0] > 4.5
    assert md.scalars['d_CCl'][-1] < 2.2 and md.scalars['d_CBr'][-1] > 5
    ts = md.events['ts']['frame']
    print('TS:', {k: float(v[ts]) for k, v in md.scalars.items()})
    assert md.scalars['angle'][ts] > 160 and abs(md.scalars['umbrella'][ts]) < .1
    assert np.all(np.diff([mapping(v) for v in np.linspace(0, mapping.x[-1], 10001)]) > 0)
    for seconds, fs in mapping.pins:
        assert abs(mapping(seconds)-fs) < 1e-6
    for name in 'ABCDEF':
        animation.scene.frame_set(t.frame(t.at(name, .5)))
        entries = animation.anchors()
        xs = [entries[k]['x']/1920 for k in ('Cl', 'C', 'Br')]
        print(f'ENQUADRAMENTO {name}: x={xs}, foco={animation.camera.data.dof.focus_distance:.3f}')
        assert all(entries[k]['visivel'] for k in ('Cl', 'C', 'Br'))
        if name == 'F':
            assert .64 < sum(xs)/3 < .68
    for name, (start, end) in t.scenes.items():
        maximum = 0.
        raw_maximum = 0.
        for frame in range(t.frame(start), t.frames+1 if name == 'F' else t.frame(end)):
            animation.scene.frame_set(frame)
            entries = animation.anchors()
            for atom in ('Cl', 'C', 'Br', 'mid_CCl', 'mid_CBr'):
                assert entries[atom]['visivel'], f'Âncora {atom} fora da tela: quadro {frame}'
            maximum = max(maximum, water_visibility_metrics(animation))
            raw_maximum = max(raw_maximum, water_visibility_metrics(animation, raw=True))
        print(f'ÁGUAS {name}: oclusão máxima={maximum:.2%}; bruta={raw_maximum:.2%}')
        limit = .16 if name == 'A' else .05  # A: plano geral, nuvem de águas ambiente
        assert maximum <= limit, f'Cena {name}: águas cobrem mais de {limit:.0%} do quadro'
    for frame, (location, rotation, focus) in enumerate(animation.camera_samples, 1):
        animation.scene.frame_set(frame)
        assert (animation.camera.location-Vector(location)).length < 1e-4
        assert abs(animation.camera.rotation_quaternion.dot(rotation)) > .99999
        assert abs(animation.camera.data.dof.focus_distance-focus) < 1e-4
    curves = animation.camera.animation_data.action.fcurves
    assert all(len(curve.keyframe_points) == t.frames for curve in curves)


def parse_arguments(timeline: Timeline) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for name in ('check','preview','motion','final'):
        modes.add_argument('--'+name, action='store_true')
    parser.add_argument('--frames', type=frame_range, default=None)
    parser.add_argument('--threads', type=thread_count, default=4)
    parser.add_argument('--samples', type=int, default=None)  # v2: amostras Cycles (padrão 64 final / 16 prévia)
    parser.add_argument('--traj', type=Path, default=None)
    parser.add_argument('--events', type=Path, default=None)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    args.check = args.check or not (args.preview or args.motion or args.final)
    if args.samples is not None and args.samples < 1:
        parser.error('--samples deve ser positivo.')
    if args.frames and args.frames[1] > timeline.frames:
        parser.error(f'--frames excede {timeline.frames}.')
    return args


def main() -> None:
    global ACTIVE
    timeline = Timeline.read(PROJECT/'timing/timing.json'); args = parse_arguments(timeline)
    path = args.traj or PROJECT/'md/traj.npz'
    trajectory = Trajectory(path, args.events)
    mapping = TimeMap(timeline, trajectory)
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene; configure_render(scene,args,timeline); world_and_compositor(scene)
    for handler in list(bpy.app.handlers.frame_change_pre):
        if getattr(handler, '__name__', '') == 'update_trajectory':
            bpy.app.handlers.frame_change_pre.remove(handler)
    ACTIVE = Animation(scene,timeline,trajectory,mapping); ACTIVE.md_path = path.resolve()
    bpy.app.handlers.frame_change_pre.append(update_trajectory)
    scene.frame_set(1)
    # Câmera com curvas explícitas para que Cycles também avalie seu motion blur.
    for frame in range(1, timeline.frames+1):
        scene.frame_set(frame)
        # As F-curves já criadas sobrescrevem a pose do handler em frame_set: reaplica antes de gravar.
        ACTIVE.camera_pose(timeline.seconds(frame), ACTIVE.positions)
        ACTIVE.camera_samples.append((tuple(scene.camera.location), scene.camera.rotation_quaternion.copy(), scene.camera.data.dof.focus_distance))
        for name in ('location', 'rotation_quaternion'):
            scene.camera.keyframe_insert(data_path=name, frame=frame)
        scene.camera.data.dof.keyframe_insert(data_path='focus_distance', frame=frame)
    for owner in (scene.camera, scene.camera.data):
        if owner.animation_data and owner.animation_data.action:
            for curve in owner.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = 'LINEAR'
    validate(ACTIVE)
    export_anchors(ACTIVE)
    if args.check:
        return
    mode = 'final' if args.final else 'motion' if args.motion else 'preview'
    if args.frames:
        frames = range(args.frames[0],args.frames[1]+1)
    else:
        frames = timeline.preview_frames() if args.preview else range(1,timeline.frames+1)
    directory = OUTPUT/mode; directory.mkdir(parents=True,exist_ok=True)
    for frame in frames:
        scene.frame_set(frame); scene.render.filepath = str(directory/f'{frame:04d}.png')
        bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    main()
