/**
 * Isles of Britain — 3D terrain viewer (Three.js, CDN, no build).
 * Heightmaps: data/terrain/{id}.json (Mapzen Terrarium DEM).
 */

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

/** Showcase islands with pre-generated terrain tiles. */
const SHOWCASE_3D_IDS = new Set([
  "staffa",
  "iona",
  "st-kilda",
  "lindisfarne",
  "lundy",
  "brownsea",
  "rathlin",
  "burgh-island",
  "fair-isle",
  "inchcailloch",
]);

export const SHOWCASE_3D_ISLAND_META = [
  { id: "staffa", name: "Staffa", nation: "Scotland" },
  { id: "iona", name: "Iona", nation: "Scotland" },
  { id: "st-kilda", name: "St Kilda", nation: "Scotland" },
  { id: "lindisfarne", name: "Lindisfarne", nation: "England" },
  { id: "lundy", name: "Lundy", nation: "England" },
  { id: "brownsea", name: "Brownsea Island", nation: "England" },
  { id: "rathlin", name: "Rathlin Island", nation: "Northern Ireland" },
  { id: "burgh-island", name: "Burgh Island", nation: "England" },
  { id: "fair-isle", name: "Fair Isle", nation: "Scotland" },
  { id: "inchcailloch", name: "Inchcailloch", nation: "Scotland" },
];

const TERRAIN_BASE = "data/terrain";
const instances = new WeakMap();

let _manifestIds = null;
let _manifestPromise = null;

function loadTerrainManifest() {
  if (!_manifestPromise) {
    _manifestPromise = fetch(`${TERRAIN_BASE}/manifest.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => {
        const ids = Array.isArray(m?.islands)
          ? m.islands.map((x) => (typeof x === "string" ? x : x?.id)).filter(Boolean)
          : [];
        _manifestIds = new Set(ids);
        return _manifestIds;
      })
      .catch(() => {
        _manifestIds = new Set();
        return _manifestIds;
      });
  }
  return _manifestPromise;
}

loadTerrainManifest();

/**
 * @param {string} id
 * @returns {boolean}
 */
export function isShowcase3DIsland(id) {
  if (!id) return false;
  if (SHOWCASE_3D_IDS.has(id)) return true;
  if (_manifestIds) return _manifestIds.has(id);
  return false;
}

/**
 * @param {number} lat1
 * @param {number} lon1
 * @param {number} lat2
 * @param {number} lon2
 * @returns {number} metres
 */
export function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

/**
 * @param {object} terrain
 * @returns {{ widthM: number, depthM: number }}
 */
function geographicExtentsM(terrain) {
  const b = terrain.bounds;
  const widthM = haversineM(b.south, b.west, b.south, b.east);
  const depthM = haversineM(b.south, b.west, b.north, b.west);
  return { widthM: Math.max(widthM, 1), depthM: Math.max(depthM, 1) };
}

/**
 * @param {number} minElev
 * @param {number} maxElev
 * @param {number} extentM
 * @returns {number}
 */
function reliefExaggeration(minElev, maxElev, extentM) {
  const relief = Math.max(maxElev - minElev, 0);
  const ratio = relief / Math.max(extentM * 0.02, 1);
  if (ratio < 0.04) return 1.8;
  if (ratio < 0.12) return 1.5;
  return 1.2;
}

/**
 * @param {number} t 0–1 normalised elevation
 * @returns {THREE.Color}
 */
function elevationColor(t) {
  const clamped = Math.max(0, Math.min(1, t));
  const low = new THREE.Color(0x3d5c3a);
  const mid = new THREE.Color(0x6b5b4a);
  const rock = new THREE.Color(0x7a828c);
  const snow = new THREE.Color(0xe8eef5);

  if (clamped < 0.35) return low.clone().lerp(mid, clamped / 0.35);
  if (clamped < 0.72) return mid.clone().lerp(rock, (clamped - 0.35) / 0.37);
  return rock.clone().lerp(snow, (clamped - 0.72) / 0.28);
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
}

function setContainerState(container, state, message = "") {
  container.classList.remove(
    "island-3d-view--loading",
    "island-3d-view--ready",
    "island-3d-view--error",
  );
  if (state) container.classList.add(`island-3d-view--${state}`);
  let status = container.querySelector(".island-3d-view__status");
  if (!message) {
    status?.remove();
    return;
  }
  if (!status) {
    status = document.createElement("p");
    status.className = "island-3d-view__status";
    status.setAttribute("role", "status");
    container.appendChild(status);
  }
  status.textContent = message;
}

/**
 * @param {string} islandId
 * @returns {Promise<object>}
 */
/** Normalise terrain JSON from build_island_terrain.py or legacy shapes. */
function normalizeTerrain(raw) {
  const cols = raw.cols ?? raw.gridW ?? raw.width;
  const rows = raw.rows ?? raw.gridH ?? raw.height;
  let bounds = raw.bounds;
  if (Array.isArray(bounds) && bounds.length >= 4) {
    bounds = { west: bounds[0], south: bounds[1], east: bounds[2], north: bounds[3] };
  }
  const flat = raw.elevations ?? raw.heights;
  if (!cols || !rows || !bounds || !Array.isArray(flat) || flat.length !== cols * rows) {
    throw new Error("Invalid terrain payload");
  }
  const land = flat.filter((v) => v != null && Number.isFinite(v));
  if (!land.length) throw new Error("Terrain has no land cells");
  const minElev = Number.isFinite(raw.minElev) ? raw.minElev : Math.min(...land);
  const maxElev = Number.isFinite(raw.maxElev) ? raw.maxElev : Math.max(...land);
  const seaLevel = minElev < 0 ? minElev : 0;
  const mask = flat.map((v) => v != null && Number.isFinite(v));
  const elevations = flat.map((v, i) =>
    mask[i] ? v : seaLevel - 0.5,
  );
  return {
    ...raw,
    cols,
    rows,
    bounds,
    elevations,
    mask,
    minElev,
    maxElev,
    seaLevel,
  };
}

async function fetchTerrain(islandId) {
  const res = await fetch(`${TERRAIN_BASE}/${islandId}.json`);
  if (!res.ok) throw new Error(`Terrain not found (${res.status})`);
  return normalizeTerrain(await res.json());
}

/**
 * @param {object} terrain
 * @returns {THREE.BufferGeometry}
 */
function buildTerrainGeometry(terrain) {
  const cols = terrain.cols ?? terrain.width;
  const rows = terrain.rows ?? terrain.height;
  if (!cols || !rows) throw new Error("Terrain grid size missing");

  const flat = terrain.elevations;
  const mask = terrain.mask;
  if (flat.length !== cols * rows) {
    throw new Error(`Elevation count ${flat.length} ≠ ${cols}×${rows}`);
  }

  let minElev = terrain.minElev;
  let maxElev = terrain.maxElev;
  if (!Number.isFinite(minElev) || !Number.isFinite(maxElev)) {
    minElev = Infinity;
    maxElev = -Infinity;
    for (let i = 0; i < flat.length; i++) {
      if (mask && !mask[i]) continue;
      const v = flat[i];
      if (v < minElev) minElev = v;
      if (v > maxElev) maxElev = v;
    }
  }

  const { widthM, depthM } = geographicExtentsM(terrain);
  const extentM = Math.max(widthM, depthM);
  const yScale = reliefExaggeration(minElev, maxElev, extentM);
  const seaLevel = Number.isFinite(terrain.seaLevel) ? terrain.seaLevel : 0;
  const waterColor = new THREE.Color(0x2a6a9e);

  const geo = new THREE.PlaneGeometry(widthM, depthM, cols - 1, rows - 1);
  geo.rotateX(-Math.PI / 2);

  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const elevRange = Math.max(maxElev - minElev, 1);

  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const dataIdx = row * cols + col;
      const elev = flat[dataIdx];
      const geoRow = rows - 1 - row;
      const posIdx = geoRow * cols + col;
      pos.setY(posIdx, (elev - seaLevel) * yScale);

      const onLand = !mask || mask[dataIdx];
      const c = onLand ? elevationColor((elev - minElev) / elevRange) : waterColor;
      colors[posIdx * 3] = c.r;
      colors[posIdx * 3 + 1] = c.g;
      colors[posIdx * 3 + 2] = c.b;
    }
  }

  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  pos.needsUpdate = true;
  geo.computeVertexNormals();

  return { geo, minElev, maxElev, seaLevel, yScale, widthM, depthM };
}

/**
 * @param {HTMLElement} container
 * @param {{ id?: string, name?: string, lat?: number, lng?: number }} island
 * @param {{ autoRotate?: boolean }} [options]
 */
export async function mountIsland3D(container, island, options = {}) {
  if (!container) return;
  destroyIsland3D(container);

  const islandId = island?.id;
  if (!islandId) {
    setContainerState(container, "error", "No island id");
    return;
  }

  setContainerState(container, "loading", "Loading terrain…");

  let terrain;
  try {
    terrain = await fetchTerrain(islandId);
  } catch (err) {
    setContainerState(
      container,
      "error",
      err?.message?.includes("404") || err?.message?.includes("not found")
        ? "Terrain tile not generated yet"
        : "Could not load terrain",
    );
    return;
  }

  if (!container.isConnected) return;

  const reducedMotion = prefersReducedMotion();
  const autoRotate = !reducedMotion && options.autoRotate !== false;

  let renderer;
  let scene;
  let controls;
  let frameId;
  let ro;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  } catch (err) {
    setContainerState(container, "error", "WebGL unavailable in this browser");
    return;
  }

  try {
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x0f1620, 1);
  container.appendChild(renderer.domElement);

  scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0f1620, 800, 3200);

  const { geo, seaLevel, yScale, widthM, depthM } = buildTerrainGeometry(terrain);
  const material = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: 0.85,
    metalness: 0.05,
    flatShading: false,
  });
  const mesh = new THREE.Mesh(geo, material);
  mesh.position.set(-widthM / 2, 0, depthM / 2);
  scene.add(mesh);

  const waterY = 0;
  const waterGeo = new THREE.PlaneGeometry(widthM * 1.08, depthM * 1.08);
  waterGeo.rotateX(-Math.PI / 2);
  const water = new THREE.Mesh(
    waterGeo,
    new THREE.MeshStandardMaterial({
      color: 0x2a6a9e,
      transparent: true,
      opacity: 0.42,
      roughness: 0.2,
      metalness: 0.1,
      depthWrite: false,
    }),
  );
  water.position.set(-widthM / 2, waterY, depthM / 2);
  scene.add(water);

  const amb = new THREE.AmbientLight(0xb8c8e0, 0.55);
  const sun = new THREE.DirectionalLight(0xfff4e6, 0.95);
  sun.position.set(widthM * 0.4, Math.max(terrain.maxElev * yScale * 2, 120), -depthM * 0.3);
  scene.add(amb, sun);

  const aspect = Math.max(container.clientWidth, 1) / Math.max(container.clientHeight, 1);
  const camera = new THREE.PerspectiveCamera(42, aspect, 0.5, 8000);
  const span = Math.max(widthM, depthM);
  camera.position.set(span * 0.35, span * 0.55, span * 0.85);
  camera.lookAt(0, span * 0.08, 0);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.target.set(0, span * 0.06, 0);
  controls.maxPolarAngle = Math.PI / 2 - 0.05;
  controls.minDistance = span * 0.25;
  controls.maxDistance = span * 3.5;
  controls.autoRotate = autoRotate;
  controls.autoRotateSpeed = reducedMotion ? 0 : 0.35;

  const resize = () => {
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w < 1 || h < 1) return;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  };

  ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
  ro?.observe(container);
  resize();
  if (container.clientWidth < 1 || container.clientHeight < 1) {
    requestAnimationFrame(resize);
  }

  frameId = 0;
  const animate = () => {
    frameId = requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  };
  animate();

  const disposeList = [];
  const track = (obj) => {
    disposeList.push(obj);
    return obj;
  };
  track(geo);
  track(material);
  track(waterGeo);
  track(water.material);
  track(amb);
  track(sun);

  const instance = {
    renderer,
    scene,
    controls,
    frameId,
    resizeObserver: ro,
    disposeList,
    stop() {
      cancelAnimationFrame(frameId);
      controls.dispose();
      ro?.disconnect();
      disposeList.forEach((o) => {
        if (o?.dispose) o.dispose();
      });
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
    },
  };

  instances.set(container, instance);
  setContainerState(container, "ready");
  } catch (err) {
    console.warn("3D terrain render failed", islandId, err);
    renderer?.dispose?.();
    if (renderer?.domElement?.parentNode === container) {
      container.removeChild(renderer.domElement);
    }
    setContainerState(
      container,
      "error",
      err?.message?.includes("Invalid terrain")
        ? "Terrain data invalid"
        : "Could not render 3D terrain",
    );
  }
}

/**
 * @param {HTMLElement} container
 */
export function destroyIsland3D(container) {
  if (!container) return;
  const inst = instances.get(container);
  if (inst) {
    inst.stop();
    instances.delete(container);
  }
  setContainerState(container, null);
  container.querySelector(".island-3d-view__status")?.remove();
}
