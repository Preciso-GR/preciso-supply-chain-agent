import * as THREE from 'three'

const COLORS = [0x78a2ff, 0xb29bff, 0xff7f9d]

export function createOrbitScene(container) {
  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100)
  camera.position.set(0, 0.2, 8.4)

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setClearColor(0x000000, 0)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  container.appendChild(renderer.domElement)

  const system = new THREE.Group()
  system.rotation.set(-0.12, -0.2, 0.08)
  scene.add(system)

  const core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.22, 5),
    new THREE.MeshPhysicalMaterial({
      color: 0x090b14,
      emissive: 0x172b66,
      emissiveIntensity: 1.5,
      metalness: 0.8,
      roughness: 0.18,
      clearcoat: 1,
      clearcoatRoughness: 0.15,
    }),
  )
  system.add(core)

  const innerCore = new THREE.Mesh(
    new THREE.SphereGeometry(0.62, 40, 40),
    new THREE.MeshBasicMaterial({ color: 0xa9bdff }),
  )
  innerCore.scale.set(1, 0.82, 1)
  core.add(innerCore)

  const rings = [
    { rotation: [Math.PI / 2.45, 0.18, 0.12], scale: [1.18, 1, 1] },
    { rotation: [0.24, Math.PI / 2.18, -0.55], scale: [1, 1.1, 1] },
    { rotation: [-0.66, 0.18, Math.PI / 2.55], scale: [1.08, 1, 1] },
  ].map((definition, index) => {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(2.15, 0.055 + index * 0.012, 20, 220),
      new THREE.MeshStandardMaterial({
        color: COLORS[index],
        emissive: COLORS[index],
        emissiveIntensity: 3.2,
        metalness: 0.55,
        roughness: 0.18,
      }),
    )
    ring.rotation.set(...definition.rotation)
    ring.scale.set(...definition.scale)
    system.add(ring)
    return ring
  })

  const particleCount = 220
  const positions = new Float32Array(particleCount * 3)
  for (let index = 0; index < particleCount; index += 1) {
    const radius = 2.8 + Math.random() * 3.5
    const angle = Math.random() * Math.PI * 2
    positions[index * 3] = Math.cos(angle) * radius
    positions[index * 3 + 1] = (Math.random() - 0.5) * 5.2
    positions[index * 3 + 2] = Math.sin(angle) * radius - 1.5
  }
  const particlesGeometry = new THREE.BufferGeometry()
  particlesGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  const particles = new THREE.Points(
    particlesGeometry,
    new THREE.PointsMaterial({ color: 0x9db5ff, size: 0.025, transparent: true, opacity: 0.58 }),
  )
  scene.add(particles)

  scene.add(new THREE.AmbientLight(0x7899ff, 1.2))
  const keyLight = new THREE.PointLight(0xf2f5ff, 22, 20)
  keyLight.position.set(4, 3, 5)
  scene.add(keyLight)
  const coralLight = new THREE.PointLight(0xff6f91, 18, 16)
  coralLight.position.set(-4, -2, 3)
  scene.add(coralLight)

  const pointer = { x: 0, y: 0 }
  const onPointerMove = (event) => {
    const bounds = container.getBoundingClientRect()
    pointer.x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 0.35
    pointer.y = ((event.clientY - bounds.top) / bounds.height - 0.5) * 0.24
  }
  container.addEventListener('pointermove', onPointerMove)

  const resize = () => {
    const width = Math.max(container.clientWidth, 1)
    const height = Math.max(container.clientHeight, 1)
    camera.aspect = width / height
    camera.updateProjectionMatrix()
    renderer.setSize(width, height, false)
  }
  const resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(container)
  resize()

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  let frame = 0
  const clock = new THREE.Clock()
  const animate = () => {
    const elapsed = clock.getElapsedTime()
    system.rotation.y += (pointer.x - system.rotation.y) * 0.025
    system.rotation.x += (-0.12 - pointer.y - system.rotation.x) * 0.025
    if (!reduceMotion) {
      rings[0].rotation.z = 0.12 + elapsed * 0.17
      rings[1].rotation.x = 0.24 - elapsed * 0.11
      rings[2].rotation.y = 0.18 + elapsed * 0.13
      core.rotation.y = elapsed * 0.08
      particles.rotation.y = elapsed * 0.014
    }
    renderer.render(scene, camera)
    frame = requestAnimationFrame(animate)
  }
  animate()

  return () => {
    cancelAnimationFrame(frame)
    resizeObserver.disconnect()
    container.removeEventListener('pointermove', onPointerMove)
    renderer.dispose()
    particlesGeometry.dispose()
    container.replaceChildren()
  }
}
