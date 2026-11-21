"use client";
/* Núcleo holográfico leve (Three.js). Respeita reduced-motion, sem WebGL -> SVG estático. */
import { useEffect, useRef } from "react";

export function HoloCore({ activity = 0, className }: { activity?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const act = useRef(activity);
  const svg = useRef<SVGSVGElement>(null);
  useEffect(() => {
    act.current = activity;
  }, [activity]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const gl = document.createElement("canvas").getContext("webgl2");
    if (reduce || !gl) return;
    let stop = false;
    let cleanup = () => {};
    import("three").then((THREE) => {
      if (stop) return;
      const w = el.clientWidth || 220;
      const h = el.clientHeight || 220;
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
      renderer.setSize(w, h);
      el.appendChild(renderer.domElement);
      if (svg.current) svg.current.style.display = "none";
      const scene = new THREE.Scene();
      const cam = new THREE.PerspectiveCamera(45, w / h, 0.1, 100);
      cam.position.z = 4.2;
      const core = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 1),
        new THREE.MeshBasicMaterial({ color: 0x22d3ee, wireframe: true, transparent: true, opacity: 0.55 }));
      const shell = new THREE.Mesh(new THREE.IcosahedronGeometry(1.45, 2),
        new THREE.MeshBasicMaterial({ color: 0x8b5cf6, wireframe: true, transparent: true, opacity: 0.18 }));
      const ring = new THREE.Mesh(new THREE.TorusGeometry(1.85, 0.008, 8, 160),
        new THREE.MeshBasicMaterial({ color: 0x3b82f6, transparent: true, opacity: 0.7 }));
      ring.rotation.x = Math.PI / 2.4;
      const pts = new Float32Array(600 * 3);
      for (let i = 0; i < pts.length; i++) pts[i] = (Math.random() - 0.5) * 6;
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(pts, 3));
      const dust = new THREE.Points(geo, new THREE.PointsMaterial({ color: 0x67e8f9, size: 0.015, transparent: true, opacity: 0.6 }));
      scene.add(core, shell, ring, dust);
      let raf = 0;
      let visible = true;
      const io = new IntersectionObserver(([e]) => (visible = e.isIntersecting));
      io.observe(el);
      const tick = () => {
        raf = requestAnimationFrame(tick);
        if (!visible || document.hidden) return;
        const speed = 0.003 + Math.min(act.current, 5) * 0.004;
        core.rotation.y += speed * 2;
        core.rotation.x += speed;
        shell.rotation.y -= speed;
        ring.rotation.z += speed * 1.5;
        dust.rotation.y += speed * 0.3;
        renderer.render(scene, cam);
      };
      tick();
      cleanup = () => {
        cancelAnimationFrame(raf);
        io.disconnect();
        renderer.dispose();
        geo.dispose();
        el.removeChild(renderer.domElement);
      };
    }).catch(() => {
      if (svg.current) svg.current.style.display = "";
    });
    return () => {
      stop = true;
      cleanup();
    };
  }, []);

  return (
    <div ref={ref} className={className} aria-hidden>
      {(
        <svg ref={svg} viewBox="0 0 100 100" className="size-full">
          <circle cx="50" cy="50" r="30" fill="none" stroke="#22d3ee" strokeOpacity=".6" strokeDasharray="3 3" />
          <circle cx="50" cy="50" r="42" fill="none" stroke="#8b5cf6" strokeOpacity=".3" />
          <circle cx="50" cy="50" r="6" fill="#22d3ee" fillOpacity=".5" />
        </svg>
      )}
    </div>
  );
}
