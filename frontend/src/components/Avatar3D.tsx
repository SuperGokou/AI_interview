import * as THREE from 'three';
import { useEffect, useRef } from 'react';

interface Avatar3DProps {
  size?: number;
  speaking?: boolean;
  className?: string;
}

export default function Avatar3D({
  size = 360,
  speaking = false,
  className,
}: Avatar3DProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Use a ref so toggling `speaking` never tears down/recreates the scene
  const speakingRef = useRef(speaking);

  // Keep speakingRef in sync without recreating the scene
  useEffect(() => {
    speakingRef.current = speaking;
  }, [speaking]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // ── Reduced-motion detection ──────────────────────────────────────────
    const prefersReduced =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ── Renderer ──────────────────────────────────────────────────────────
    // Guard against jsdom / headless environments where WebGL is unavailable.
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas,
        alpha: true,
        antialias: true,
      });
    } catch {
      // No WebGL support (test / SSR environment) — bail out gracefully.
      return;
    }
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    renderer.setSize(size, size, false);

    // ── Scene ─────────────────────────────────────────────────────────────
    const scene = new THREE.Scene();
    // No scene.background → stays transparent

    // ── Camera ────────────────────────────────────────────────────────────
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    camera.position.set(0, 0.15, 4.3);

    // ── Lights ────────────────────────────────────────────────────────────
    const ambient = new THREE.AmbientLight(0xffffff, 0.75);
    scene.add(ambient);

    const dirA = new THREE.DirectionalLight(0xffffff, 0.95);
    dirA.position.set(-2.5, 3, 4);
    scene.add(dirA);

    const dirB = new THREE.DirectionalLight(0xb9bcff, 0.55);
    dirB.position.set(3, 1.5, -2);
    scene.add(dirB);

    // ── Materials ─────────────────────────────────────────────────────────
    const skinMat = new THREE.MeshStandardMaterial({
      color: 0xf2c6a3,
      roughness: 0.62,
    });
    const hairMat = new THREE.MeshStandardMaterial({
      color: 0xcaa15a,
      roughness: 0.75,
    });
    const eyeWhiteMat = new THREE.MeshStandardMaterial({ color: 0xffffff });
    const irisMat = new THREE.MeshStandardMaterial({ color: 0x2c2c38 });
    const lipMat = new THREE.MeshStandardMaterial({ color: 0xc67a6a });
    const topMat = new THREE.MeshStandardMaterial({ color: 0x16171f });

    // Collect all disposables for cleanup
    const geos: THREE.BufferGeometry[] = [];
    const mats: THREE.Material[] = [
      skinMat,
      hairMat,
      eyeWhiteMat,
      irisMat,
      lipMat,
      topMat,
    ];

    function makeMesh(
      geo: THREE.BufferGeometry,
      mat: THREE.Material
    ): THREE.Mesh {
      geos.push(geo);
      return new THREE.Mesh(geo, mat);
    }

    // ── Avatar group ──────────────────────────────────────────────────────
    const A = new THREE.Group();

    // Head
    const headGeo = new THREE.SphereGeometry(1, 48, 48);
    const head = makeMesh(headGeo, skinMat);
    head.scale.set(0.8, 0.98, 0.84);
    head.position.set(0, 0.45, 0);
    A.add(head);

    // Jaw
    const jawGeo = new THREE.SphereGeometry(0.7, 32, 32);
    const jaw = makeMesh(jawGeo, skinMat);
    jaw.scale.set(0.82, 0.7, 0.8);
    jaw.position.set(0, 0.02, 0.05);
    A.add(jaw);

    // Hair back
    const hairBackGeo = new THREE.SphereGeometry(1.06, 40, 40);
    const hairBack = makeMesh(hairBackGeo, hairMat);
    hairBack.scale.set(0.96, 1.16, 0.92);
    hairBack.position.set(0, 0.56, -0.12);
    A.add(hairBack);

    // Side locks
    function makeSideLock(sideX: number): THREE.Mesh {
      const lockGeo = new THREE.SphereGeometry(0.42, 24, 24);
      const lock = makeMesh(lockGeo, hairMat);
      lock.scale.set(0.55, 1.5, 0.6);
      lock.position.set(sideX, 0.18, 0.06);
      return lock;
    }
    A.add(makeSideLock(-0.74));
    A.add(makeSideLock(0.74));

    // Fringe
    const fringeGeo = new THREE.SphereGeometry(0.9, 32, 32);
    const fringe = makeMesh(fringeGeo, hairMat);
    fringe.scale.set(0.86, 0.52, 0.62);
    fringe.position.set(0, 1.04, 0.18);
    A.add(fringe);

    // Eyes (L/R) — collect groups for blink
    const eyeGroups: THREE.Group[] = [];
    function makeEye(sideX: number): THREE.Group {
      const eyeGroup = new THREE.Group();
      eyeGroup.position.set(sideX, 0.5, 0.7);
      eyeGroup.scale.set(1, 1, 0.55);

      const whiteGeo = new THREE.SphereGeometry(0.115, 24, 24);
      const white = makeMesh(whiteGeo, eyeWhiteMat);
      eyeGroup.add(white);

      const irisGeo = new THREE.SphereGeometry(0.058, 16, 16);
      const iris = makeMesh(irisGeo, irisMat);
      iris.position.set(0, 0, 0.07);
      eyeGroup.add(iris);

      return eyeGroup;
    }
    const eyeL = makeEye(-0.27);
    const eyeR = makeEye(0.27);
    eyeGroups.push(eyeL, eyeR);
    A.add(eyeL);
    A.add(eyeR);

    // Brows
    function makeBrow(sideX: number, rotZ: number): THREE.Mesh {
      const browGeo = new THREE.BoxGeometry(0.24, 0.045, 0.06);
      const brow = makeMesh(browGeo, hairMat);
      brow.position.set(sideX, 0.67, 0.76);
      brow.rotation.z = rotZ;
      return brow;
    }
    A.add(makeBrow(-0.27, 0.08));
    A.add(makeBrow(0.27, -0.08));

    // Nose
    const noseGeo = new THREE.ConeGeometry(0.075, 0.2, 14);
    const nose = makeMesh(noseGeo, skinMat);
    nose.rotation.x = Math.PI;
    nose.position.set(0, 0.38, 0.82);
    A.add(nose);

    // Mouth
    const mouthGeo = new THREE.TorusGeometry(0.16, 0.038, 12, 28, Math.PI);
    const mouth = makeMesh(mouthGeo, lipMat);
    mouth.rotation.z = Math.PI;
    mouth.position.set(0, 0.14, 0.78);
    A.add(mouth);

    // Neck
    const neckGeo = new THREE.CylinderGeometry(0.27, 0.33, 0.5, 24);
    const neck = makeMesh(neckGeo, skinMat);
    neck.position.set(0, -0.42, 0);
    A.add(neck);

    // Torso
    const torsoGeo = new THREE.SphereGeometry(1, 32, 32);
    const torso = makeMesh(torsoGeo, topMat);
    torso.scale.set(1.55, 0.95, 0.82);
    torso.position.set(0, -1.5, 0);
    A.add(torso);

    A.position.y = -0.15;
    scene.add(A);

    // ── Animation loop ────────────────────────────────────────────────────
    let t = 0;
    let lastBlink = 0;
    let blinking = false;
    let blinkStart = 0;
    let rafId = 0;

    function animate() {
      rafId = requestAnimationFrame(animate);

      // Idle body sway
      A.rotation.y = Math.sin(t * 0.5) * 0.13;
      A.rotation.x = Math.sin(t * 0.4 + 1) * 0.03;
      A.position.y = -0.15 + Math.sin(t * 1.3) * 0.02;

      // Blink every ~4.2 s
      if (!blinking && t - lastBlink > 4.2) {
        blinking = true;
        blinkStart = t;
      }
      if (blinking) {
        const blinkElapsed = t - blinkStart;
        const BLINK_DUR = 0.12; // seconds @ 60fps (0.016 * frames)
        if (blinkElapsed < BLINK_DUR) {
          const scaleY = 0.12;
          eyeGroups.forEach((eg) => (eg.scale.y = scaleY));
        } else {
          eyeGroups.forEach((eg) => (eg.scale.y = 1));
          blinking = false;
          lastBlink = t;
        }
      }

      // Mouth animation
      if (speakingRef.current) {
        const factor = Math.abs(Math.sin(t * 5.5));
        mouth.scale.y = 1 + factor * 0.5;
        mouth.scale.x = 1 + factor * 0.1;
      } else {
        mouth.scale.y = 1 + Math.abs(Math.sin(t * 1.2)) * 0.06;
        mouth.scale.x = 1;
      }

      renderer.render(scene, camera);
      t += 0.016;
    }

    if (prefersReduced) {
      // Render one static frame only
      renderer.render(scene, camera);
    } else {
      animate();
    }

    // ── Cleanup ───────────────────────────────────────────────────────────
    return () => {
      cancelAnimationFrame(rafId);
      geos.forEach((g) => g.dispose());
      mats.forEach((m) => m.dispose());
      renderer.dispose();
    };
    // Re-run only when `size` changes (not `speaking` — that goes through speakingRef)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size]);

  return (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label="AI 面试官 菜鸟庆 3D 形象"
      className={className}
      style={{ width: size, height: size, display: 'block' }}
    />
  );
}
