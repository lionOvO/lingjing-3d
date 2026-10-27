<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { configureInspectionControls, inspectionDistance } from '../utils/inspectionCamera'

export type DisplayMode = 'material' | 'solid' | 'wireframe' | 'normals'
export type ViewerBackground = 'inspection' | 'night' | 'studio' | 'transparent'
export type ModelTransformMode = 'translate' | 'rotate'

const props = withDefaults(defineProps<{
  modelUrl?: string
  modelFormat?: string
  displayMode?: DisplayMode
  autoRotate?: boolean
  panMode?: boolean
  modelMoveMode?: boolean
  modelTransformMode?: ModelTransformMode
  background?: ViewerBackground
  showGrid?: boolean
  roughness?: number
  metalness?: number
  ambientIntensity?: number
  keyLightIntensity?: number
}>(), {
  modelUrl: '',
  modelFormat: 'glb',
  displayMode: 'material',
  autoRotate: false,
  panMode: false,
  modelMoveMode: false,
  modelTransformMode: 'translate',
  background: 'inspection',
  showGrid: false,
  roughness: 1,
  metalness: 1,
  ambientIntensity: 1.1,
  keyLightIntensity: 2.8,
})

const emit = defineEmits<{
  loading: []
  loaded: []
  error: [message: string]
  selection: [selected: boolean]
}>()

const host = ref<HTMLElement>()
const status = ref<'idle' | 'loading' | 'loaded' | 'error'>('idle')
const hint = ref('等待模型文件')
const interacting = ref(false)
const selected = ref(false)

let scene: THREE.Scene | undefined
let camera: THREE.PerspectiveCamera | undefined
let renderer: THREE.WebGLRenderer | undefined
let controls: OrbitControls | undefined
let transformControls: TransformControls | undefined
let observer: ResizeObserver | undefined
let frame = 0
let activeModel: THREE.Object3D | undefined
let ambient: THREE.AmbientLight | undefined
let keyLight: THREE.DirectionalLight | undefined
let selectionHelper: THREE.BoxHelper | undefined
let grid: THREE.GridHelper | undefined
let removePointerGuards: (() => void) | undefined
const originalMaterials = new WeakMap<THREE.MeshStandardMaterial, {
  map: THREE.Texture | null; color: THREE.Color; roughness: number; metalness: number; flatShading: boolean
}>()

const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()
let pointerStart: { x: number; y: number } | undefined

function release(object?: THREE.Object3D) {
  object?.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return
    node.geometry.dispose()
    ;(Array.isArray(node.material) ? node.material : [node.material]).forEach((material) => material.dispose())
  })
}

function applyMaterials() {
  activeModel?.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return
    ;(Array.isArray(node.material) ? node.material : [node.material]).forEach((material) => {
      if (!(material instanceof THREE.MeshStandardMaterial || material instanceof THREE.MeshPhysicalMaterial)) return
      if (!originalMaterials.has(material)) originalMaterials.set(material, {
        map: material.map, color: material.color.clone(), roughness: material.roughness,
        metalness: material.metalness, flatShading: material.flatShading,
      })
      const original = originalMaterials.get(material)!
      material.wireframe = props.displayMode === 'wireframe'
      material.roughness = original.roughness * props.roughness
      material.metalness = original.metalness * props.metalness
      material.flatShading = props.displayMode === 'normals' || original.flatShading
      material.map = props.displayMode === 'material' ? original.map : null
      material.color.copy(original.color)
      if (props.displayMode !== 'material') {
        material.map = null
        material.color.set(props.displayMode === 'normals' ? 0x9c93d5 : 0xd9d4eb)
      }
      material.needsUpdate = true
    })
  })
}

function fitCamera(object: THREE.Object3D) {
  if (!camera || !controls) return
  const box = new THREE.Box3().setFromObject(object)
  if (box.isEmpty()) return

  const center = box.getCenter(new THREE.Vector3())
  const size = box.getSize(new THREE.Vector3())
  const radius = Math.max(size.length() * .5, .25)
  const distance = inspectionDistance(radius,camera.fov,camera.aspect)

  camera.near = Math.max(radius / 100, .01)
  camera.far = Math.max(radius * 30, 100)
  camera.position.copy(center).add(new THREE.Vector3(1,.58,1).normalize().multiplyScalar(distance))
  camera.lookAt(center)
  controls.target.copy(center)
  controls.minDistance = Math.max(radius * .18, .08)
  controls.maxDistance = Math.max(radius * 18, 8)
  controls.update()
}

function setSelection(value: boolean) {
  selected.value = value
  if (selectionHelper) {
    selectionHelper.visible = value
    if (value && activeModel) selectionHelper.setFromObject(activeModel)
  }
  if (value && props.modelMoveMode && activeModel) transformControls?.attach(activeModel)
  else transformControls?.detach()
  emit('selection', value)
}

function resetCamera() {
  if (activeModel) fitCamera(activeModel)
}

async function loadModel(url = props.modelUrl) {
  if (!scene || !url) return

  const suffix = url.split('?')[0].toLowerCase()
  const format = props.modelFormat.toLowerCase()
  const nonPreviewFormat = suffix.match(/\.(obj|fbx|stl)$/)
  if (nonPreviewFormat || (!['glb', 'gltf'].includes(format) && !suffix.match(/\.(glb|gltf)$/))) {
    status.value = 'error'
    hint.value = '当前浏览器仅支持预览 GLB / GLTF 文件，请下载该格式模型查看。'
    emit('error', hint.value)
    return
  }

  status.value = 'loading'
  hint.value = '模型加载中…'
  emit('loading')
  setSelection(false)

  if (activeModel) {
    scene.remove(activeModel)
    release(activeModel)
    activeModel = undefined
  }

  try {
    const gltf = await new GLTFLoader().loadAsync(url)
    activeModel = gltf.scene
    activeModel.traverse((node) => {
      if (node instanceof THREE.Mesh) {
        node.castShadow = true
        node.receiveShadow = true
      }
    })
    scene.add(activeModel)

    selectionHelper?.removeFromParent()
    selectionHelper = new THREE.BoxHelper(activeModel, 0xa9c7e8)
    selectionHelper.visible = false
    selectionHelper.material.depthTest = false
    selectionHelper.material.transparent = true
    selectionHelper.material.opacity = .9
    selectionHelper.renderOrder = 10
    scene.add(selectionHelper)

    applyMaterials()
    fitCamera(activeModel)
    status.value = 'loaded'
    hint.value = '单击模型选中 · 拖拽旋转 / 平移视角 · 滚轮缩放'
    emit('loaded')
  } catch (error) {
    console.error('3D model loading failed', { url, error })
    status.value = 'error'
    const reason = error instanceof Error && error.message ? `（${error.message}）` : ''
    hint.value = `模型加载失败，请确认文件链接有效后重试。${reason}`
    emit('error', hint.value)
  }
}

function updateScene() {
  if (!scene || !renderer) return
  const color = props.background === 'studio' ? 0x454a50 : props.background === 'night' ? 0x191d22 : 0x2b3036
  // An opaque, neutral stage keeps the page wallpaper out of material checks.
  scene.background = props.background === 'transparent' ? null : new THREE.Color(color)
  renderer.setClearColor(color, props.background === 'transparent' ? 0 : 1)
  if(grid)grid.visible=props.showGrid
  if (ambient) ambient.intensity = props.ambientIntensity
  if (keyLight) keyLight.intensity = props.keyLightIntensity
  applyMaterials()
}

function capture() {
  if (!renderer) return
  const link = document.createElement('a')
  link.download = `moonlit-model-${Date.now()}.png`
  link.href = renderer.domElement.toDataURL('image/png')
  link.click()
}

async function toggleFullscreen() {
  if (!host.value) return
  if (document.fullscreenElement) await document.exitFullscreen()
  else await host.value.requestFullscreen()
}

function updateMouseButtons() {
  if (!controls) return
  configureInspectionControls(controls,THREE.MOUSE,props.panMode)
}

function updateModelMoveMode() {
  if (!controls || !transformControls) return
  transformControls.enabled = props.modelMoveMode
  if (props.modelMoveMode && selected.value && activeModel) {
    transformControls.setMode(props.modelTransformMode)
    transformControls.attach(activeModel)
  } else {
    // A detached and disabled transform helper must not retain pointer focus.
    // This hands the canvas back to OrbitControls immediately.
    transformControls.detach()
  }
  controls.enabled = true
}

function selectAt(event: PointerEvent) {
  if (!renderer || !camera || !activeModel || event.button !== 0) return
  const bounds = renderer.domElement.getBoundingClientRect()
  if (!bounds.width || !bounds.height) return

  pointer.set(
    ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
    -((event.clientY - bounds.top) / bounds.height) * 2 + 1,
  )
  raycaster.setFromCamera(pointer, camera)
  setSelection(raycaster.intersectObject(activeModel, true).length > 0)
}

function installPointerGuards() {
  if (!renderer) return
  const canvas = renderer.domElement
  const preventContextMenu = (event: MouseEvent) => event.preventDefault()
  const onPointerDown = (event: PointerEvent) => {
    if (event.button === 0) pointerStart = { x: event.clientX, y: event.clientY }
  }
  const onPointerUp = (event: PointerEvent) => {
    const start = pointerStart
    pointerStart = undefined
    if (!start || event.button !== 0) return
    const distance = Math.hypot(event.clientX - start.x, event.clientY - start.y)
    // A short click picks the model. A real drag remains owned by OrbitControls.
    if (distance <= 6) selectAt(event)
  }

  updateMouseButtons()
  canvas.addEventListener('contextmenu', preventContextMenu, true)
  canvas.addEventListener('pointerdown', onPointerDown, true)
  canvas.addEventListener('pointerup', onPointerUp, true)
  removePointerGuards = () => {
    canvas.removeEventListener('contextmenu', preventContextMenu, true)
    canvas.removeEventListener('pointerdown', onPointerDown, true)
    canvas.removeEventListener('pointerup', onPointerUp, true)
  }
}

onMounted(async () => {
  if (!host.value) return
  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(42, 1, .01, 1000)
  camera.position.set(3.5, 2.4, 4.8)
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  host.value.appendChild(renderer.domElement)
  renderer.domElement.setAttribute('aria-label', '3D 模型预览画布')
  renderer.domElement.style.touchAction = 'none'

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = .06
  controls.enableRotate = true
  controls.enableZoom = true
  controls.enablePan = true
  controls.screenSpacePanning = true
  controls.rotateSpeed = .85
  controls.zoomSpeed = 1.1
  controls.panSpeed = .9
  controls.target.set(0, .75, 0)
  controls.maxDistance = 35
  controls.addEventListener('start', () => { interacting.value = true })
  controls.addEventListener('end', () => { interacting.value = false })

  transformControls = new TransformControls(camera, renderer.domElement)
  transformControls.setMode(props.modelTransformMode)
  transformControls.setSpace('world')
  transformControls.enabled = props.modelMoveMode
  transformControls.addEventListener('dragging-changed', (event) => {
    if (controls) controls.enabled = !event.value
    interacting.value = event.value
  })
  transformControls.addEventListener('objectChange', () => {
    if (activeModel && selectionHelper) selectionHelper.setFromObject(activeModel)
  })
  scene.add(transformControls)
  installPointerGuards()

  grid=new THREE.GridHelper(16, 16, 0x626970, 0x42484f)
  grid.visible=props.showGrid
  for(const material of Array.isArray(grid.material)?grid.material:[grid.material]){material.transparent=true;material.opacity=.28}
  scene.add(grid)
  ambient = new THREE.AmbientLight(0xffffff, props.ambientIntensity)
  scene.add(ambient)
  keyLight = new THREE.DirectionalLight(0xffffff, props.keyLightIntensity)
  keyLight.position.set(4, 6, 5)
  scene.add(keyLight)
  const rim = new THREE.DirectionalLight(0xffffff, 1.8)
  rim.position.set(-4, 2, -3)
  scene.add(rim)
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(24, 24),
    new THREE.ShadowMaterial({ color: 0x050815, opacity: .28 }),
  )
  floor.rotation.x = -Math.PI / 2
  scene.add(floor)

  const resize = () => {
    if (!host.value || !camera || !renderer) return
    const { clientWidth: width, clientHeight: height } = host.value
    if (!width || !height) return
    camera.aspect = width / height
    camera.updateProjectionMatrix()
    renderer.setSize(width, height, false)
  }
  observer = new ResizeObserver(resize)
  observer.observe(host.value)
  resize()
  updateScene()

  const render = () => {
    if (controls) {
      controls.autoRotate = props.autoRotate && !matchMedia('(prefers-reduced-motion: reduce)').matches
      controls.update()
    }
    if (selected.value && activeModel && selectionHelper) selectionHelper.setFromObject(activeModel)
    renderer?.render(scene!, camera!)
    frame = requestAnimationFrame(render)
  }
  render()

  await nextTick()
  if (props.modelUrl) loadModel()
})

watch(() => props.modelUrl, (url) => {
  if (url) loadModel(url)
  else {
    setSelection(false)
    status.value = 'idle'
    hint.value = '等待模型文件'
  }
})
watch(() => props.panMode, updateMouseButtons)
watch(() => [props.modelMoveMode, props.modelTransformMode], updateModelMoveMode)
watch(() => [props.displayMode, props.background, props.showGrid, props.roughness, props.metalness, props.ambientIntensity, props.keyLightIntensity], updateScene)

onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
  removePointerGuards?.()
  transformControls?.detach()
  transformControls?.dispose()
  controls?.dispose()
  selectionHelper?.removeFromParent()
  release(activeModel)
  renderer?.dispose()
})

defineExpose({ resetCamera, capture, toggleFullscreen, reload: loadModel })
</script>

<template>
  <div
    ref="host"
    class="model-canvas"
    :class="[`canvas-${background}`, { interacting, selected, 'pan-mode': panMode }]"
    @contextmenu.prevent
  >
    <div v-if="status !== 'loaded'" class="canvas-state" :class="status">
      <span v-if="status === 'loading'" class="canvas-spinner"></span>
      <strong>{{ hint }}</strong>
      <small v-if="status === 'idle'">完成任务后将自动载入模型</small>
    </div>
    <div v-if="status === 'loaded'" class="canvas-selection-status" :class="{ selected, editing: modelMoveMode }" aria-live="polite">
      <i></i>{{ modelMoveMode ? (selected ? `${modelTransformMode === 'rotate' ? '旋转' : '移动'}模型 · 拖动三轴手柄` : '模型编辑已开启 · 单击模型显示三轴手柄') : (selected ? '模型已选中' : '单击模型即可选中') }}
    </div>
    <div v-if="status === 'loaded'" class="canvas-interaction-hint" :class="{ faded: interacting }" aria-hidden="true">
      <span>{{ panMode ? '平移模式 · 左键拖拽移动视角' : '左键拖拽旋转视角' }}</span>
      <i></i>
      <span>右键 / 中键 / Shift + 左键平移</span>
      <i></i>
      <span>滚轮缩放</span>
    </div>
    <div class="canvas-caption" :class="{ error: status === 'error' }">{{ hint }}</div>
  </div>
</template>

<style scoped>
/* Keep each viewer in its own layout box, including when embedded directly. */
.model-canvas {
  position: relative;
  inset: auto;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  isolation: isolate;
}
.model-canvas :deep(canvas) {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
}
.model-canvas.canvas-inspection{background:#2b3036}
.model-canvas.canvas-night{background:#191d22}
.model-canvas.canvas-studio{background:#454a50}
.model-canvas.canvas-transparent{background:repeating-conic-gradient(#32373d 0% 25%,#40464d 0% 50%) 50%/20px 20px}
</style>
