# Session Handover — 2026-05-31 (Session 3)

## Status
Context near limit. Handover written externally. Two bugs diagnosed, fixes not yet written.

## Project
Portrait-to-3D web app at `/home/sy5/projects/portrait-3d/`

## What Works
- FastAPI backend at port 8787 ✅
- PNG upload → Depth-Anything V2 → trimesh mesh → GLB export ✅ (4.4MB GLB confirmed)
- Vite frontend built to backend/dist/ ✅
- trimesh process=False fix applied ✅

## What's Broken (Mentor Step 4 — in progress)

### Bug 1: THREE is not defined when loading GLB
- Location: `frontend/src/main.js` line ~167
- Code: `child.material.side = THREE ? THREE.DoubleSide : 2;`
- Cause: `THREE` is never imported in main.js — only `GLTFLoader` is imported
- Fix: Add `import * as THREE from 'three';` at top of main.js, OR replace the line with the literal value `child.material.side = 2;` (DoubleSide = 2)

### Bug 2: Vanta.js not visible
- Cause 1: `loadVanta()` called synchronously at module top-level — must defer to DOMContentLoaded or window.load
- Cause 2: vanta@latest CDN returns 200 (confirmed), but script injection timing is off
- Fix: Move `loadVanta()` call inside `window.addEventListener('load', ...)`, add console.error on failure

## Pending After Fixes
- Rebuild frontend: `cd /home/sy5/projects/portrait-3d/frontend && npm run build`
- Hard reload http://localhost:8787
- Verify: Vanta background visible, GLB import button works, terminal viewer renders model

## Mentor Step Counter
- Step 1: Diagnose JSON.parse error ✅
- Step 2: Explain trimesh process=False fix ✅
- Step 3: Implement Vanta + terminal viewer + GLB import ✅ (written, bugs remain)
- Step 4: Fix THREE import + Vanta timing — IN PROGRESS

## Key Files
- `frontend/src/main.js` — needs THREE import fix + Vanta defer fix
- `frontend/src/style.css` — terminal + vanta-bg positioning
- `frontend/index.html` — Vanta script tags
- `backend/mesh_builder.py` — process=False fix already applied

## System Prompt
v0.5.6 active. LSE RAG Tools V2 enabled.

## Next Session Start
Read this handover, then ask user: "Ready to apply the two fixes for Bug 1 and Bug 2?"
Apply fixes → rebuild → verify → index KB entries for lessons learned.
