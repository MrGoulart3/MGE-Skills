"""Salt dissolving: trajetória em Å, Geometry Nodes e timing externo.

Utilitários copiados/adaptados de agua_gas.py (sem importar a cena original).
Dados sintéticos servem apenas para revisão visual, nunca para alegações de MD.
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
OUTPUT = DIRECTORY.parents[1] / "render" / "sal_en"
SEED = 104524
STYLE = json.loads((DIRECTORY / "style.json").read_text())
RADII = {"Na": 0.62, "Cl": 1.05, "O": 0.40, "H": 0.24}


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
        for name, names in {"A": ["reveal"], "B": ["label_ions", "charges"], "C": ["delta_minus", "delta_plus"], "D": ["orient"], "E": ["detach", "shell"], "F": ["title"]}.items():
            previous = scenes[name][0]
            for event in names:
                value = events[event]
                if not math.isfinite(value) or not previous <= value < scenes[name][1]:
                    raise ValueError(f"Evento {event} inválido.")
                previous = value
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



class Trajectory:
    """Valida o contrato e interpola coordenadas já desdobradas."""

    def __init__(self, path: Path, events_path: Path | None) -> None:
        with np.load(path, allow_pickle=False) as data:
            self.positions = np.array(data['positions'], dtype=np.float32)
            self.times = np.array(data['time_ps'], dtype=float)
            self.elements = data['element'].astype(str)
            self.molecules = np.array(data['molecule'], dtype=int)
            self.box = np.array(data['box'], dtype=float)
            self.synthetic = bool(data['synthetic']) if 'synthetic' in data else path.stem.endswith('_fake')
        p = self.positions
        if p.ndim != 3 or p.shape[2] != 3 or len(p) < 4 or self.times.shape != (len(p),):
            raise ValueError('positions/time_ps com formato inválido.')
        if self.elements.shape != (p.shape[1],) or self.molecules.shape != self.elements.shape:
            raise ValueError('element/molecule com formato inválido.')
        if not np.isfinite(p).all() or not np.isfinite(self.times).all() or not (np.diff(self.times) > 0).all():
            raise ValueError('Coordenadas inválidas ou tempos não crescentes.')
        if self.box.shape != (3,) or not np.isfinite(self.box).all() or not (self.box > 0).all():
            raise ValueError('box inválida.')
        if set(self.elements) != set(RADII):
            raise ValueError('São necessários Na, Cl, O e H, sem sítios virtuais.')
        self.groups = {e: np.flatnonzero(self.elements == e) for e in RADII}
        self.ions = np.flatnonzero(np.isin(self.elements, ['Na', 'Cl']))
        waters = []
        for oxygen in self.groups['O']:
            members = np.flatnonzero(self.molecules == self.molecules[oxygen])
            hydrogens = members[self.elements[members] == 'H']
            if len(members) != 3 or len(hydrogens) != 2:
                raise ValueError('Cada água deve conter um O e dois H.')
            waters.append([oxygen, *hydrogens])
        self.waters = np.array(waters, dtype=int)
        if len(self.groups['H']) != 2 * len(waters):
            raise ValueError('H sem molécula de água válida.')
        # Filtro suave apenas nas translações: não altera a geometria rígida.
        oxygen_positions = p[:, self.waters[:, 0]].copy()
        padded = np.pad(oxygen_positions, ((1, 1), (0, 0), (0, 0)), mode='edge')
        filtered = .15 * padded[:-2] + .70 * padded[1:-1] + .15 * padded[2:]
        for column in range(3):
            self.positions[:, self.waters[:, column]] += filtered - oxygen_positions
        events_path = events_path or path.with_name('events_fake.json' if self.synthetic else 'events.json')
        payload = json.loads(events_path.read_text())
        events = payload if isinstance(payload, list) else payload['events']
        self.events = sorted([e for e in events if e['kind'] == 'detach'], key=lambda e: e['time_ps'])
        if len(self.events) < 2:
            raise ValueError('São necessários ao menos dois eventos detach.')
        for e in self.events:
            index, frame = e['index'], e['frame']
            if not 0 <= index < p.shape[1] or not 0 <= frame < len(p):
                raise ValueError('Índice/frame inválido em events.json (base zero).')
            if self.elements[index] != e['ion'] or e['ion'] not in ('Na', 'Cl'):
                raise ValueError('Espécie do evento incompatível.')
            if abs(self.times[frame] - e['time_ps']) > 1e-4:
                raise ValueError('frame/time_ps incompatíveis no evento.')
        if self.events[0]['index'] == self.events[1]['index'] or self.events[0]['time_ps'] >= self.events[1]['time_ps']:
            raise ValueError('Os dois primeiros detach devem ser distintos e ordenados.')
        self.focus = [int(e['index']) for e in self.events[:2]]
        self.crystal = np.array([i for i in self.ions if i not in self.focus])
        first = self.sample(self.events[0]['time_ps'])
        candidates = np.flatnonzero(self.shell(first, self.focus[0]))
        if not len(candidates):
            raise ValueError('Íon 1 não tem águas na primeira camada.')
        direction = np.array([-.7, -1., .65])
        # Prefere uma água na camada e à frente do cristal para a cena C.
        score = first[self.waters[candidates, 0]] @ direction
        self.hero = self.waters[candidates[np.argmax(score)]]

    def sample(self, time: float) -> np.ndarray:
        i = int(np.clip(np.searchsorted(self.times, time) - 1, 0, len(self.times) - 2))
        u = float(np.clip((time - self.times[i]) / (self.times[i + 1] - self.times[i]), 0, 1))
        p0, p1, p2, p3 = self.positions[np.clip([i - 1, i, i + 1, i + 2], 0, len(self.times) - 1)]
        # Hermite Catmull–Rom com tangentes ajustadas a intervalos não uniformes.
        dt = self.times[i + 1] - self.times[i]
        a, b = max(i - 1, 0), min(i + 2, len(self.times) - 1)
        m1 = (p2 - p0) * dt / (self.times[i + 1] - self.times[a])
        m2 = (p3 - p1) * dt / (self.times[b] - self.times[i])
        return ((2*u**3 - 3*u**2 + 1)*p1 + (u**3 - 2*u**2 + u)*m1
                + (-2*u**3 + 3*u**2)*p2 + (u**3 - u**2)*m2)

    def shell(self, positions: np.ndarray, ion: int) -> np.ndarray:
        w = positions[self.waters]
        if self.elements[ion] == 'Na':
            return np.linalg.norm(w[:, 0] - positions[ion], axis=-1) < 3.2
        return (np.linalg.norm(w[:, 1:] - positions[ion], axis=-1) < 2.9).any(axis=1)

    def bound_ions(self, positions: np.ndarray) -> np.ndarray:
        distances = np.linalg.norm(positions[self.ions, None] - positions[self.ions], axis=-1)
        bound = self.ions[((distances <= 3.6) & (distances > 0)).sum(axis=1) >= 3]
        if not len(bound):
            raise ValueError('Nenhum íon ligado ao cristal neste instante MD.')
        return bound


class TimeMap:
    """Hermite monotônico C1: sincroniza os eventos MD à palavra detach."""

    def __init__(self, timeline: Timeline, trajectory: Trajectory) -> None:
        t, md = timeline, trajectory
        early = md.events[0]['time_ps']
        second = md.events[1]['time_ps']
        initial = md.times[0]
        if early <= initial or second >= md.times[-1]:
            raise ValueError('Eventos precisam de margem inicial/final na trajetória.')
        self.x = np.array([0, t.at('D', 1), t.events['detach'] + min(4 / t.fps, (t.at('E', .88) - t.events['detach']) * .15),
                           t.at('E', .88), t.duration])
        self.y = np.array([initial, initial + .28 * (early - initial), early, second, md.times[-1]])
        if not (np.diff(self.x) > 0).all():
            raise ValueError('Timing não comporta os eventos detach.')
        h, delta = np.diff(self.x), np.diff(self.y) / np.diff(self.x)
        self.slopes = np.zeros(len(self.x))
        self.slopes[0], self.slopes[-1] = delta[0], delta[-1]
        for i in range(1, len(self.x) - 1):
            w1, w2 = 2*h[i] + h[i-1], h[i] + 2*h[i-1]
            self.slopes[i] = (w1 + w2) / (w1 / delta[i-1] + w2 / delta[i])

    def __call__(self, seconds: float) -> float:
        i = int(np.clip(np.searchsorted(self.x, seconds) - 1, 0, len(self.x) - 2))
        h = self.x[i+1] - self.x[i]
        u = float(np.clip((seconds - self.x[i]) / h, 0, 1))
        return float((2*u**3 - 3*u**2 + 1)*self.y[i] + (u**3 - 2*u**2 + u)*h*self.slopes[i]
                     + (-2*u**3 + 3*u**2)*self.y[i+1] + (u**3 - u**2)*h*self.slopes[i+1])

    def inverse(self, md_time: float) -> float:
        low, high = self.x[0], self.x[-1]
        for _ in range(50):
            middle = (low + high) / 2
            if self(middle) < md_time:
                low = middle
            else:
                high = middle
        return float((low + high) / 2)


def atom_material(element: str) -> bpy.types.Material:
    color = '#8F6BFF' if element == 'Na' else STYLE['elements'][element]
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
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    blend = nodes.new('ShaderNodeMixShader')
    links.new(attrs['fade'], blend.inputs[0]); links.new(transparent.outputs[0], blend.inputs[1])
    links.new(shader.outputs[0], blend.inputs[2])
    links.new(blend.outputs[0], nodes.get('Material Output').inputs['Surface'])
    return result


def point_object(element: str, count: int, mat: bpy.types.Material) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(element + ' pontos')
    mesh.from_pydata([(0., 0., 0.)] * count, [], [])
    for name in ('highlight', 'glow', 'fade'):
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
    fade.inputs['Name'].default_value = 'fade'
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
    profile.inputs['Radius'].default_value = .09; profile.inputs['Resolution'].default_value = 8
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
    scene.cycles.samples = 64 if args.final else 16
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


def padded_bounds(points: np.ndarray, radius: float) -> list[Vector]:
    low, high = points.min(axis=0) - radius, points.max(axis=0) + radius
    return [Vector((x, y, z)) for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])]


def hero_bounds(md: Trajectory, positions: np.ndarray, rotation: object) -> list[Vector]:
    axes = [rotation @ Vector(axis) for axis in ((1, 0, 0), (0, 1, 0))]
    return [Vector(positions[index]) + axis*sign*RADII[md.elements[index]]
            for index in md.hero for axis in axes for sign in (-1, 1)]


class Animation:
    """Um handler atualiza malhas e a câmera, inclusive em subframes."""

    def __init__(self, scene: bpy.types.Scene, t: Timeline, md: Trajectory, mapping: TimeMap) -> None:
        self.scene, self.t, self.md, self.mapping = scene, t, md, mapping
        self.objects = {e: point_object(e, len(indices), atom_material(e)) for e, indices in md.groups.items()}
        self.bonds = bond_object(md)
        camera = bpy.data.cameras.new('Câmera contínua'); camera.lens = 52; camera.clip_start = .05; camera.clip_end = 300
        camera.dof.use_dof = True; camera.dof.aperture_fstop = 2.8; camera.dof.aperture_blades = 7
        scene.camera = bpy.data.objects.new('Câmera contínua', camera); scene.collection.objects.link(scene.camera)
        self.direction = Vector((-.7, -1., .65)).normalized()
        self.knots = []
        self.camera_samples = None
        for name, height, x in [('A', .35, .5), ('B', .70, .5), ('C', .22, .5), ('D', .55, .5), ('E', .40, .5), ('F', .40, .68)]:
            seconds = t.at(name, .5 if name != 'F' else .65)
            p = md.sample(mapping(seconds))
            if name == 'C':
                bounds = hero_bounds(md, p, (-self.direction).to_track_quat('-Z', 'Y'))
                center = Vector(p[md.hero].mean(axis=0))
            elif name == 'E':
                bounds = padded_bounds(p[md.focus], 3.2); center = Vector(p[md.focus].mean(axis=0))
            else:
                bound = md.bound_ions(p)
                bounds = padded_bounds(p[bound], 1.05); center = Vector(p[bound].mean(axis=0))
            location, target = solve_framing(scene, bounds, center, self.direction, height, x)
            focus = (location - center).length
            self.knots.append((seconds, location, target, focus))
        # Mantém o mesmo enquadramento no início e no encerramento.
        first = self.knots[0]
        opening = first[2] + (first[1] - first[2]) * 1.08
        self.knots.insert(0, (0., opening, first[2], first[3] * 1.08))
        self.knots.append((t.duration, *self.knots[-1][1:]))
        surface = md.positions[0]
        for element in ('Na', 'Cl'):
            indices = md.groups[element]
            self.__dict__['label_' + element.lower()] = int(indices[np.argmax(surface[indices] @ np.array(self.direction))])
        self.positions = md.sample(mapping(0))
        samples = []
        for frame in range(t.frames+1):
            seconds = frame/t.fps
            self.camera_pose(seconds, md.sample(mapping(seconds)))
            camera = scene.camera
            samples.append((camera.location.copy(), camera.rotation_quaternion.copy(), camera.data.dof.focus_distance))
        self.camera_samples = samples

    def camera_pose(self, seconds: float, p: np.ndarray) -> None:
        scene, camera = self.scene, self.scene.camera
        if self.camera_samples is not None:
            fractional = float(np.clip(seconds*self.t.fps, 0, len(self.camera_samples)-1))
            index = min(int(fractional), len(self.camera_samples)-2)
            first, last = self.camera_samples[index:index+2]
            u = fractional-index
            camera.location = first[0].lerp(last[0], u)
            camera.rotation_quaternion = first[1].slerp(last[1], u)
            camera.data.dof.focus_distance = (1-u)*first[2]+u*last[2]
            bpy.context.view_layer.update()
            return
        for first, last in zip(self.knots, self.knots[1:]):
            if seconds <= last[0]:
                ratio = ease(seconds, first[0], last[0])
                location = first[1].lerp(last[1], ratio)
                target = first[2].lerp(last[2], ratio)
                focus = (1-ratio)*first[3] + ratio*last[3]
                break
        else:
            _, location, target, focus = self.knots[-1]
        # D/E seguem o canto em movimento; a correção de área segura é contínua.
        e0, e1 = self.t.scenes['E']
        follow = ease(seconds, e0, self.t.at('E', .15)) * (1-ease(seconds, e1, self.t.at('F', .35)))
        if follow:
            center = Vector(p[self.md.focus].mean(axis=0))
            bounds = padded_bounds(p[self.md.focus], 3.2)
            safe_location, safe_target = solve_framing(scene, bounds, center, self.direction, .44, .5)
            location = location.lerp(safe_location, follow)
            target = target.lerp(safe_target, follow)
            focus = (1-follow)*focus + follow*(location - Vector(p[self.md.focus[0]])).length
        for name, height, x in [('A', .35, .5), ('B', .70, .5), ('D', .55, .5), ('F', .40, .68)]:
            start, end = self.t.scenes[name]
            weight = ease(seconds, start, self.t.at(name, .2))
            if name != 'F':
                weight *= 1-ease(seconds, self.t.at(name, .8), end)
            if start <= seconds <= end and weight:
                bound = self.md.bound_ions(p)
                center = Vector(p[bound].mean(axis=0))
                framed, aimed = solve_framing(scene, padded_bounds(p[bound], 1.05), center, self.direction, height, x)
                location = location.lerp(framed, weight)
                target = target.lerp(aimed, weight)
                focus = (1-weight)*focus + weight*(location-center).length
        hero_focus = ease(seconds, self.t.at('B', .85), self.t.at('C', .15)) * (1-ease(seconds, self.t.at('C', .85), self.t.at('D', .3)))
        focus = (1-hero_focus)*focus + hero_focus*(location-Vector(p[self.md.hero].mean(axis=0))).length
        camera.location = location
        camera.rotation_quaternion = (target-location).to_track_quat('-Z', 'Y')
        reveal = self.t.events['reveal']
        camera.data.dof.focus_distance = focus + 16*(1-ease(seconds, max(0., reveal-.5), reveal+.8))
        camera.data.dof.aperture_fstop = 2.8
        bpy.context.view_layer.update()

    def attributes(self, seconds: float, p: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        md, t = self.md, self.t
        highlight = np.zeros(len(md.elements), dtype=np.float32)
        glow = highlight.copy(); fade = np.zeros(len(highlight), dtype=np.float32)
        highlight[md.ions], fade[md.ions] = 1., 1.
        amount = ease(seconds, t.events['orient'] - .5, t.events['orient'] + .5)
        weights = np.zeros(len(md.waters), dtype=np.float32)
        for ion in md.focus:
            water = p[md.waters]
            if md.elements[ion] == 'Na':
                distances = np.linalg.norm(water[:, 0] - p[ion], axis=-1)
                cutoff = 3.2
            else:
                distances = np.linalg.norm(water[:, 1:] - p[ion], axis=-1).min(axis=1)
                cutoff = 2.9
            u = np.clip((cutoff + .15 - distances) / .30, 0, 1)
            weights = np.maximum(weights, u*u*(3-2*u))
        members = md.waters.ravel()
        highlight[members] = np.repeat(weights, 3)*amount
        name = next((name for name, (start, end) in t.scenes.items() if start <= seconds < end), 'F')
        # E: crystal + leaving ions keep their water (the crystal never looks bare); F: every ion keeps its
        # hydration, so the hydrated ions are seen "spreading out".
        if name == 'E':
            subject = np.union1d(md.bound_ions(p), md.focus)
        elif name == 'F':
            subject = md.ions
        else:
            subject = md.bound_ions(p)
        centers = p[md.waters].mean(axis=1)
        distances = np.linalg.norm(centers[:, None] - p[subject], axis=-1).min(axis=1)
        haze = np.clip((12.-distances)/4.5, 0., 1.)
        visibility = haze*haze*(3-2*haze)
        camera = np.array(self.scene.camera.location)
        target = p[md.hero].mean(axis=0) if name == 'C' else p[md.focus].mean(axis=0) if name == 'E' else p[md.bound_ions(p)].mean(axis=0)
        ray = target-camera
        length = np.linalg.norm(ray)
        direction = ray/length
        along = (centers-camera) @ direction
        radial = np.linalg.norm(centers-camera-along[:, None]*direction, axis=-1)
        in_front = (along > 0) & (along < length)
        cull = np.clip((radial-6.)/.75, 0., 1.)
        visibility *= np.where(in_front, cull*cull*(3-2*cull), 1.)
        if name == 'E':
            first_shell = np.logical_or.reduce([md.shell(p, ion) for ion in md.focus])
            visibility[first_shell] = 1.
            highlight[members] = np.repeat(np.maximum(weights*amount, first_shell.astype(float)), 3)
        hero_amount = ease(seconds, t.at('B', .85), t.at('C', .15)) * (1-ease(seconds, t.at('C', .85), t.at('D', .3)))
        near_hero = np.linalg.norm(centers-p[md.hero].mean(axis=0), axis=-1) <= 7.5
        visibility[near_hero] *= 1-hero_amount
        fade[members] = np.repeat(visibility, 3)
        highlight[md.hero] = np.maximum(highlight[md.hero], hero_amount)
        fade[md.hero] = np.maximum(fade[md.hero], hero_amount)
        pulse_start = t.events['charges']
        width = (t.at('B', 1) - pulse_start) * .75
        u = np.clip((seconds-pulse_start)/width, 0, 1)
        glow[md.ions] = np.sin(np.pi*u)**2
        for index, event in [(md.hero[0], 'delta_minus'), (md.hero[1], 'delta_plus'), (md.hero[2], 'delta_plus')]:
            glow[index] = ease(seconds, t.events[event], t.events[event] + (t.at('C', 1)-t.events[event])*.35) * hero_amount
        return highlight, glow, fade

    def update(self, frame: float) -> None:
        seconds = float(np.clip(self.t.seconds(frame), 0, self.t.duration))
        p = self.md.sample(self.mapping(seconds)); self.positions = p
        self.camera_pose(seconds, p)
        attrs = self.attributes(seconds, p)
        for element, indices in self.md.groups.items():
            mesh = self.objects[element].data
            mesh.vertices.foreach_set('co', np.asarray(p[indices], dtype=np.float32).ravel())
            for name, values in zip(('highlight', 'glow', 'fade'), attrs):
                mesh.attributes[name].data.foreach_set('value', values[indices])
            mesh.update()
        indices = self.md.waters.ravel(); mesh = self.bonds.data
        mesh.vertices.foreach_set('co', np.asarray(p[indices], dtype=np.float32).ravel())
        for name, values in zip(('highlight', 'glow', 'fade'), attrs):
            mesh.attributes[name].data.foreach_set('value', values[indices])
        mesh.update()
        # Em F, as águas de fundo deixam espaço legível para a composição do título.
        title = ease(seconds, self.t.at('F', 0), self.t.events['title'])
        if title:
            water_indices = self.md.waters.ravel()
            fade = attrs[2].copy()
            for index in water_indices:
                projected = world_to_camera_view(self.scene, self.scene.camera, Vector(p[index]))
                left = 1-ease(projected.x, .40, .58)
                fade[index] *= 1-.97*title*left
            for element in ('O', 'H'):
                mesh = self.objects[element].data
                mesh.attributes['fade'].data.foreach_set('value', fade[self.md.groups[element]])
                mesh.update()
            self.bonds.data.attributes['fade'].data.foreach_set('value', fade[water_indices])
            self.bonds.data.update()

    def anchors(self) -> dict:
        p, md, scene = self.positions, self.md, self.scene
        points = {'crystal_center': p[md.crystal].mean(axis=0), 'label_na': p[self.label_na],
                  'label_cl': p[self.label_cl], 'hero_o': p[md.hero[0]], 'hero_h1': p[md.hero[1]],
                  'hero_h2': p[md.hero[2]], 'ion1': p[md.focus[0]], 'ion2': p[md.focus[1]]}
        return {name: project_anchor(scene, Vector(position)) for name, position in points.items()}


ACTIVE: Animation | None = None


@persistent
def update_trajectory(scene: bpy.types.Scene, depsgraph: object = None) -> None:
    if ACTIVE is not None:
        ACTIVE.update(float(scene.frame_current) + scene.frame_subframe)


def export_anchors(animation: Animation) -> None:
    scene, t = animation.scene, animation.t
    frames = {}
    for frame in range(1, t.frames+1):
        scene.frame_set(frame)
        frames[str(frame)] = {**animation.anchors(), 'md_time_ps': animation.mapping(t.seconds(frame))}
    payload = {'fps': t.fps, 'width': 1920, 'height': 1080, 'synthetic': animation.md.synthetic,
               'trajectory': str(animation.md_path), 'frames': frames}
    (DIRECTORY / 'anchors.json').write_text(json.dumps(payload, indent=2)+'\n')


def projected_radius(scene: bpy.types.Scene, position: np.ndarray, radius: float) -> float:
    center = Vector(position)
    up = scene.camera.rotation_quaternion @ Vector((0, radius, 0))
    a, b = world_to_camera_view(scene, scene.camera, center), world_to_camera_view(scene, scene.camera, center+up)
    return abs(a.y-b.y)*1080


def water_visibility_metrics(animation: Animation, subject: np.ndarray) -> tuple[int, float]:
    """Conta instâncias e estima a união projetada à frente do sujeito em 384×216."""
    scene, md, p = animation.scene, animation.md, animation.positions
    fades = np.empty(len(md.waters), dtype=np.float32)
    animation.objects['O'].data.attributes['fade'].data.foreach_get('value', fades)
    # A ordem dos oxigênios segue md.groups, que pode diferir da ordem das águas.
    oxygen_order = np.searchsorted(md.groups['O'], md.waters[:, 0])
    fades = fades[oxygen_order]
    camera = scene.camera
    subject_depth = world_to_camera_view(scene, camera, Vector(subject)).z
    coverage = np.zeros((216, 384), dtype=bool)
    for water, fade in zip(md.waters, fades):
        if fade <= .001:
            continue
        for index in water:
            point = world_to_camera_view(scene, camera, Vector(p[index]))
            if not camera.data.clip_start < point.z < subject_depth:
                continue
            radius = projected_radius(scene, p[index], RADII[md.elements[index]]*float(fade))/5
            x, y = point.x*384, point.y*216
            left, right = max(0, math.floor(x-radius)), min(384, math.ceil(x+radius))
            bottom, top = max(0, math.floor(y-radius)), min(216, math.ceil(y+radius))
            if right <= left or top <= bottom:
                continue
            yy, xx = np.ogrid[bottom:top, left:right]
            coverage[bottom:top, left:right] |= (xx+.5-x)**2 + (yy+.5-y)**2 <= radius**2
    return int((fades > .001).sum()), float(coverage.mean())


def estimate_mean_brightness(animation: Animation) -> float:
    """Estimativa em sRGB de área projetada + iluminação; não é medição de render."""
    scene, md, p = animation.scene, animation.md, animation.positions
    # Usa o fundo efetivo e a cobertura projetada de discos; sobreposição saturada.
    background = np.mean([np.array([int(c.lstrip('#')[i:i+2], 16)/255 for i in (0,2,4)])
                          for c in (STYLE['background']['top'], STYLE['background']['bottom'])], axis=0)
    lum = float(background @ np.array([.2126, .7152, .0722]))
    light = sum(obj.data.energy for obj in scene.objects if obj.type == 'LIGHT')
    illumination = min(1., light/(4*math.pi*25**2))
    contributions = []
    highlight, _, fade = animation.attributes(animation.t.seconds(scene.frame_current), p)
    for index in range(len(p)):
        projected = world_to_camera_view(scene, scene.camera, Vector(p[index]))
        if projected.z > 0 and 0 <= projected.x <= 1 and 0 <= projected.y <= 1:
            element = md.elements[index]; r = projected_radius(scene, p[index], RADII[element])
            color = STYLE['elements'][element].lstrip('#')
            value = sum(int(color[i:i+2],16)/255*w for i,w in zip((0,2,4),(.2126,.7152,.0722)))
            area = min(.1, math.pi*r*r/(1920*1080)) * float(fade[index])
            contributions.append(area*(value*(.48+.52*highlight[index])*illumination-lum))
    return lum + sum(contributions)/(1+sum(abs(c) for c in contributions))


def validate(animation: Animation) -> None:
    scene, t, md, mapping = animation.scene, animation.t, animation.md, animation.mapping
    failures = []
    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)
    print('DADOS:', 'SINTÉTICOS (QA visual)' if md.synthetic else 'MD real', flush=True)
    print('ESPÉCIES:', dict(Counter(md.elements)), flush=True)
    p = md.positions[0]
    distance = np.linalg.norm(p[md.groups['Na'], None]-p[md.groups['Cl']], axis=-1).min()
    bonds = np.linalg.norm(p[md.waters[:, 1:]]-p[md.waters[:, 0], None], axis=-1)
    print(f'GEOMETRIA: Na–Cl mínimo={distance:.4f} Å; O–H={bonds.mean():.4f} Å ({bonds.min():.4f}–{bonds.max():.4f})')
    require(2.5 < distance < 3.1, 'Na–Cl fora de ≈2,8 Å')
    require(np.max(np.abs(bonds-.9572)) < .08, 'O–H fora de ≈0,96 Å')
    # Dados reais flutuam ps a ps: usa a mediana da 1ª camada nos 10 ps após a saída (Na 5–7, Cl 5–9).
    detach = md.events[0]
    counts = [int(md.shell(md.sample(detach['time_ps'] + k), md.focus[0]).sum()) for k in range(0, 11)]
    count = int(np.median(counts))
    print(f'HIDRATAÇÃO ion1 ({detach["ion"]}): mediana {count} águas em {detach["time_ps"]:.0f}–{detach["time_ps"]+10:.0f} ps; série {counts}')
    require(5 <= count <= (7 if detach['ion'] == 'Na' else 9), 'ion1 fora da hidratação esperada')
    for event in md.events[:2]:
        p = md.sample(event['time_ps'])
        other = md.ions[md.ions != event['index']]
        d = float(np.linalg.norm(p[other]-p[event['index']], axis=-1).min())
        print(f'DETACH {event["ion"]}: distância mínima={d:.3f} Å; vídeo={mapping.inverse(event["time_ps"]):.4f} s')
        require(d > 4.95, 'Evento detach não corresponde a saída >5 Å')
    for name in 'ABCDEF':
        seconds = t.at(name, .5 if name != 'F' else .8)
        scene.frame_set(t.frame(seconds)); p = animation.positions
        subject = p[md.hero] if name == 'C' else p[md.focus] if name == 'E' else p[md.bound_ions(p)]
        radius = .4 if name == 'C' else 3.2 if name == 'E' else 1.05
        l,r,b,top = screen_bounds(scene, padded_bounds(subject, radius))
        if name == 'C':
            l,r,b,top = screen_bounds(scene, hero_bounds(md, p, scene.camera.rotation_quaternion))
        brightness = estimate_mean_brightness(animation)
        print(f'CENA {name}: centro=({(l+r)/2:.4f},{(b+top)/2:.4f}), altura={top-b:.4f}, brilho estimado={brightness:.4f}')
        require(brightness >= .03, f'Cena {name} escura')
        visible, occluding = water_visibility_metrics(animation, subject.mean(axis=0))
        print(f'ÁGUAS {name}: {visible} visíveis; cobertura à frente={occluding:.2%} (união projetada estimada)')
        require(visible <= (1200 if name == 'F' else 550), f'Cena {name}: águas visíveis demais ({visible})')
        require(occluding <= .08, f'Cena {name}: águas cobrem mais de 8% do quadro à frente do sujeito')
        if name in 'ABCF':
            goal = {'A':.35,'B':.70,'C':.22,'F':.40}[name]
            # F: com dados reais o cristal se desfaz durante a cena; tolerância maior.
            require(abs(top-b-goal) < (.11 if name == 'F' else .035), f'Enquadramento {name} fora da meta')
        if name == 'F':
            require(abs((l+r)/2-.68) < .025, 'Cristal fora do terço direito em F')
        if name == 'B':
            pixels = projected_radius(scene, p[animation.label_na], .62)
            print(f'Na⁺ B: raio={pixels:.2f} px'); require(pixels >= 14, 'Na B <14 px')
        if name == 'C':
            pixels = projected_radius(scene, p[md.hero[0]], .4)
            print(f'Hero O C: raio={pixels:.2f} px'); require(pixels >= 40, 'Hero C <40 px')
            bounds = hero_bounds(md, p, scene.camera.rotation_quaternion)
            _, _, bottom, top = screen_bounds(scene, bounds)
            print(f'HERO C KEYFRAMED: altura={top-bottom:.2%}')
            require(top-bottom >= .18, 'Hero C ocupa menos de 18% da altura do quadro')
            focus = (scene.camera.location-Vector(p[md.hero].mean(axis=0))).length
            require(abs(scene.camera.data.dof.focus_distance-focus) < .1, 'Hero C fora do foco')
            nearby = np.linalg.norm(p[md.waters].mean(axis=1)-p[md.hero].mean(axis=0), axis=-1) <= 7.5
            nearby[np.all(md.waters == md.hero, axis=1)] = False
            fades = np.empty(len(md.groups['O']), dtype=np.float32)
            animation.objects['O'].data.attributes['fade'].data.foreach_get('value', fades)
            require(np.all(fades[np.searchsorted(md.groups['O'], md.waters[nearby, 0])] <= .001), 'Hero C sem isolamento')
        if name == 'E':
            for ion in md.focus:
                shell = md.waters[md.shell(p, ion)].ravel()
                highlight, _, fade = animation.attributes(t.seconds(scene.frame_current), p)
                require(np.all(fade[shell] == 1) and np.all(highlight[shell] == 1), f'Primeira camada de {ion} sem destaque integral em E')
    safe = [1., 0., 1., 0.]
    for frame in range(t.frame(t.at('E',0)), t.frame(t.at('E',1))):
        scene.frame_set(frame)
        for name in ('ion1','ion2'):
            a = animation.anchors()[name]; x,y = a['x']/1920, a['y']/1080
            safe = [min(safe[0],x),max(safe[1],x),min(safe[2],y),max(safe[3],y)]
            require(a['visivel'] and .2 <= x <= .8 and .2 <= y <= .8, f'{name} fora da área segura no quadro {frame}')
    print('ÁREA SEGURA E (x mín/máx, y mín/máx):', [round(v,4) for v in safe])
    print('MAPEAMENTO (vídeo s → MD ps):', list(zip(mapping.x.tolist(), mapping.y.tolist())))
    times = np.array([mapping(t.seconds(f)) for f in range(1,t.frames+1)])
    require((np.diff(times) >= 0).all(), 'Mapeamento MD não monotônico')
    scene.frame_set(t.frame(t.at('E',.5)), subframe=.5)
    require(np.allclose(animation.positions, md.sample(mapping(t.seconds(scene.frame_current+.5)))), 'Handler sem suporte a subframes')
    if failures:
        raise AssertionError('\n'.join(dict.fromkeys(failures)))
    print('CHECK OK — sem render; brilho é estimativa, revisão visual pendente.', flush=True)


def parse_arguments(timeline: Timeline) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for name in ('check','preview','motion','final'):
        modes.add_argument('--'+name, action='store_true')
    parser.add_argument('--frames', type=frame_range, default=None)
    parser.add_argument('--threads', type=thread_count, default=4)
    parser.add_argument('--traj', type=Path, default=None)
    parser.add_argument('--events', type=Path, default=None)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    args.check = args.check or not (args.preview or args.motion or args.final)
    if args.frames and args.frames[1] > timeline.frames:
        parser.error(f'--frames excede {timeline.frames}.')
    return args


def main() -> None:
    global ACTIVE
    timeline = Timeline.read(DIRECTORY/'timing/timing.json'); args = parse_arguments(timeline)
    path = args.traj or DIRECTORY/'md/traj.npz'
    if args.traj is None and not path.exists():
        path = DIRECTORY/'md/traj_fake.npz'
        print('AVISO: MD real ausente; usando trajetória SINTÉTICA.', flush=True)
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
        for name in ('location', 'rotation_quaternion'):
            scene.camera.keyframe_insert(data_path=name, frame=frame)
        scene.camera.data.dof.keyframe_insert(data_path='focus_distance', frame=frame)
    for owner in (scene.camera, scene.camera.data):
        if owner.animation_data and owner.animation_data.action:
            for curve in owner.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = 'LINEAR'
    # Verificação pós-keyframes: a câmera que o render usa precisa ser a mesma que foi validada.
    moved = []
    for name in 'ABCDEF':
        frame = timeline.frame(timeline.at(name, .5))
        scene.frame_set(frame)
        expected = Vector(ACTIVE.camera_samples[min(int(round(timeline.seconds(frame)*timeline.fps)), len(ACTIVE.camera_samples)-1)][0])
        error = (scene.camera.matrix_world.translation - expected).length
        moved.append(scene.camera.matrix_world.translation.copy())
        print(f'CÂMERA KEYFRAMED {name}: quadro {frame}, erro vs. amostra={error:.3f} Å', flush=True)
        if error > 0.5:
            raise AssertionError(f'Câmera keyframed diverge da validada na cena {name}')
    if max((m - moved[0]).length for m in moved) < 5:
        raise AssertionError('Câmera parada: keyframes iguais em todas as cenas')
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
