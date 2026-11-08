// The barge in 3D: the game's models as tools/web_export.py writes them (build/web/models), turned and zoomed with the mouse.
// Not the game's renderer: simple light, base colour and normal map only (no material map, no faction colours, no emissive).

import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';

// Places in three.js axes: the game's x is mirrored (tools/web_export.py, to_gltf). The port is cut at game x 0.9..2.05, y 0.45..1.98, z 5.0..6.5 (data/hull_parts.json);
// this view looks at the side whose port the drawing shows, bow to the left as on the panel.
const PORT = new THREE.Vector3(1.5, 1.2, 5.75);
const PORT_CAMERA = new THREE.Vector3(7.5, 2.6, 7.2);
const ALL_TARGET = new THREE.Vector3(0, 7, -1.5);
const ALL_CAMERA = new THREE.Vector3(34, 14, 16);
// target, a point the camera looks from, the radius the view must hold. The game's left side is three.js +x (x is mirrored).
const VIEWS = {
    port: [PORT, PORT_CAMERA, 2.6],
    port_right: [new THREE.Vector3(-PORT.x, PORT.y, PORT.z), new THREE.Vector3(-PORT_CAMERA.x, PORT_CAMERA.y, PORT_CAMERA.z), 2.6],     // only by ?view=port_right
    all: [ALL_TARGET, ALL_CAMERA, 17],
    left: [ALL_TARGET, new THREE.Vector3(40, 9, -1.5), 15],
    right: [ALL_TARGET, new THREE.Vector3(-40, 9, -1.5), 15],
    // close looks from the left side, bow to the left as on the drawing; only by ?view= (comparing the drawing with the model)
    drive: [new THREE.Vector3(2.5, 2.2, -7.6), new THREE.Vector3(40, 2.4, -7.6), 3.6],
    bow: [new THREE.Vector3(2.5, 1.6, 5.2), new THREE.Vector3(40, 1.8, 5.2), 3.4],
    waist: [new THREE.Vector3(2.5, 2.6, 0.6), new THREE.Vector3(40, 2.8, 0.6), 5.2],
    bomb: [new THREE.Vector3(2.8, 3.1, 4.66), new THREE.Vector3(40, 3.3, 4.66), 1.3],
    bomb_aft: [new THREE.Vector3(2.8, 2.0, -2.73), new THREE.Vector3(40, 2.2, -2.73), 1.1],
    below: [new THREE.Vector3(0, 1, -1.5), new THREE.Vector3(6, -40, -1.4), 12],
};

export class Viewer {
    constructor(host) {
        this.host = host;
        this.renderer = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true});
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.outputColorSpace = THREE.SRGBColorSpace;
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.0;
        host.appendChild(this.renderer.domElement);
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x7d8a94);
        this.camera = new THREE.PerspectiveCamera(35, 1, 0.1, 500);
        this.scene.add(new THREE.HemisphereLight(0xdfe8f0, 0x4a3a2a, 1.6));
        const sun = new THREE.DirectionalLight(0xfff1dc, 2.4);
        sun.position.set(20, 30, 14);
        this.scene.add(sun);
        const fill = new THREE.DirectionalLight(0xc8d4e0, 0.7);
        fill.position.set(-20, 8, -14);
        this.scene.add(fill);
        const under = new THREE.DirectionalLight(0xc8d4e0, 0.6);     // so that the bottom is seen from below
        under.position.set(4, -30, 2);
        this.scene.add(under);
        this.controls = new OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = false;     // no drift after the mouse lets go
        this.controls.minDistance = 2;
        this.controls.maxDistance = 120;
        this.models = {};
        this.current = null;
        this.wanted = null;
        new ResizeObserver(() => this.resize()).observe(host);
        this.resize();
        this.view('all');
        const loop = () => { this.controls.update(); this.renderer.render(this.scene, this.camera); requestAnimationFrame(loop); };
        loop();
    }

    resize() {
        const w = this.host.clientWidth, h = this.host.clientHeight;
        if (!w || !h) return;
        this.renderer.setSize(w, h);
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
    }

    async load(name, url) {
        const gltf = await new GLTFLoader().loadAsync(url);
        const root = gltf.scene;
        root.traverse(o => {
            if (o.isMesh && o.material.normalMap) {
                // The game's normal maps are DirectX style (green down); three.js reads them OpenGL style
                o.material.normalScale.set(1, -1);
            }
        });
        root.visible = false;
        root.name = name;
        this.scene.add(root);
        this.models[name] = root;
        if (this.wanted === name) this.show(name);
        return root;
    }

    // The hull shown: hull_base, or hull_stock for a look at the stock ship
    show(name) {
        this.wanted = name;
        this.current = name;
        if (this.models[name]) this.models[name].visible = true;
    }

    // A detail on or off: its own model, and the nodes of the hull it replaces (the port's plug, the hatch covers) the other way round
    setPart(name, on, hides = []) {
        if (this.models[name]) this.models[name].visible = on;
        const hull = this.models[this.current];
        if (!hull) return;
        for (const node of hides) {
            const o = hull.getObjectByName(node);
            if (o) o.visible = !on;
        }
    }

    // The frame on its slip as a scheme of primitives (a keel, the stem and stern posts, U-shaped frames, a few planks on the ground): there is no model of it.
    showFrameScheme(on) {
        if (on && !this.frameScheme) {
            const g = new THREE.Group();
            const wood = new THREE.MeshStandardMaterial({color: 0xb07a45, roughness: 0.9});
            const keel = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.4, 16), wood);
            keel.position.set(0, 0.6, -0.4);
            g.add(keel);
            for (let z = -7.5; z <= 7.01; z += 1.0) {
                const t = z / 8.6;
                const r = 2.6 * Math.sqrt(Math.max(0.15, 1 - t * t));
                const rib = new THREE.Mesh(new THREE.TorusGeometry(r, 0.09, 6, 28, Math.PI), wood);
                rib.rotation.z = Math.PI;          // the arc's open side up: a U across the ship
                rib.position.set(0, 0.8 + r, z);
                g.add(rib);
            }
            for (const [z, h] of [[8.0, 4.2], [-8.6, 4.3]]) {
                const post = new THREE.Mesh(new THREE.BoxGeometry(0.3, h, 0.3), wood);
                post.position.set(0, 0.8 + h / 2, z);
                g.add(post);
            }
            for (const z of [-5, 0, 5]) {
                const blockM = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.4, 0.6), wood);
                blockM.position.set(0, 0.2, z);
                g.add(blockM);
            }
            for (let i = 0; i < 3; i++) {
                const plank = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.08, 4.5), wood);
                plank.position.set(4.2, 0.04 + i * 0.09, -1 + i * 0.1);
                g.add(plank);
            }
            const ground = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.MeshStandardMaterial({color: 0x6b5a44, roughness: 1}));
            ground.rotation.x = -Math.PI / 2;
            g.add(ground);
            this.scene.add(g);
            this.frameScheme = g;
        }
        if (this.frameScheme) this.frameScheme.visible = on;
        if (on && !this.frameViewSet) {
            this.frameViewSet = true;
            // the whole frame (a ball of radius 10 round it) in view whatever the shape of the window, from the left side and a little above
            const target = new THREE.Vector3(0, 2, 0), dir = new THREE.Vector3(16, 7, 6).normalize();
            const vfov = THREE.MathUtils.degToRad(this.camera.fov), hfov = 2 * Math.atan(Math.tan(vfov / 2) * this.camera.aspect);
            this.controls.target.copy(target);
            this.camera.position.copy(target).addScaledVector(dir, 10 / Math.sin(Math.min(vfov, hfov) / 2));
            this.controls.update();
        }
    }

    hiddenNodes() {
        const out = [];
        const hull = this.models[this.current];
        if (hull) hull.traverse(o => { if (o !== hull && !o.visible) out.push(o.name); });
        return out;
    }

    // The camera from the direction of eye to target, as far as the view needs to hold a ball of this radius whatever the shape of the window
    view(which) {
        const [target, eye, radius] = VIEWS[which];
        const vfov = THREE.MathUtils.degToRad(this.camera.fov);
        const hfov = 2 * Math.atan(Math.tan(vfov / 2) * this.camera.aspect);
        const distance = radius / Math.sin(Math.min(vfov, hfov) / 2);
        const dir = eye.clone().sub(target).normalize();
        this.controls.target.copy(target);
        this.camera.position.copy(target).addScaledVector(dir, distance);
        this.lastView = which;
        this.controls.update();
    }
}
