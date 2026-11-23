# AI Asset Finisher: implementation plan

Goal: turn an AI generation or photoscan (millions of faces, baked-in colour, no UVs) into a game-ready asset:
under 15K triangles, clean quads, sensible seams and UVs, and the original detail re-baked into the new UVs.

Each step is shippable and testable on its own. We only start the next one when the previous one is verified on a real shoe.

| Step | Scope | Done when | Status |
|---|---|---|---|
| **1. Clean retopology** | Cleanup, debris removal, quad remesh to a triangle budget, hard cap of 15K tris, quality report | Real shoe photoscan lands under 15K tris, all quads, 0 non-manifold edges, mean deviation < 0.5% of object size | **Shipped in v0.2.0, awaiting test on the shoe** |
| 2. Seams and UVs | Seam placement (angle islands + hard edges + boundary), unwrap, uniform texel density, packing | UVs in 0-1, no overlaps, coverage > 70%, stretch under a threshold, seams hidden on the sole, tongue and inner edges | Prototype exists (smart project + island seams), not tuned |
| 3. Bake | Normal, base colour, roughness, metallic, AO from high to low into the new UVs; cage and ray distance; edge padding | Re-lit low-poly matches the high-poly, no seam artefacts, no black or blown-out patches | Prototype exists, verified on a figurine only |
| 4. Material and export | Clean PBR material, OpenGL/DirectX normals, PNG maps, GLB/FBX export with textures | Opens correctly in Unity, Unreal and glTF viewers | Prototype exists, export untested |
| 5. Polish | Presets (Footwear, Apparel), batch mode over folders, progress UI, optional edge-flow guidance (hard-surface parts like soles and eyelets), symmetry | A folder of hundreds of models runs unattended | Not started |

## Step 1 detail (what is in v0.2.0)

1. Duplicate the high-poly as `<name>_low`; the original is never touched.
2. Clean: weld vertices, drop degenerate faces, close small holes (needed for a clean remesh), recalc normals.
3. If over 150K faces: collapse-decimate to 120K first (a photoscan of several million faces would make Quadriflow take forever), then clean again.
4. Delete floating debris smaller than 0.5% of the largest piece (scan floaters, AI specks).
5. Quad remesh (Quadriflow) aimed at the triangle budget (default 12K, which is 6K quads). Quadriflow can overshoot, so if the result is over the cap it retries with a lower target, up to 4 times.
6. Fallbacks: voxel remesh then Quadriflow, then collapse decimate. The result is never above the hard cap (default 15K).
7. Report in the panel: triangles, faces, quads, ngons, non-manifold edges, and shape deviation vs the original (mean, 99th percentile, max, as % of object size).

Settings: target triangles, hard cap, drop-debris %, preserve sharp edges, preserve boundaries, hole-fill size, weld distance, smooth angle, triangulate.

Verified so far (headless):
- 40K-face AI figurine, Blender 5.0: 12,096 tris, all quads, 0 non-manifold edges, mean deviation 0.01%, 4 s.
- Imitated noisy photoscans of 0.5M and 1.9M faces (debris + surface noise), Blender 5.0: 12.4K and 11.5K tris, all quads, 0 non-manifold edges, mean deviation 0.02%, 20 s and 76 s. Quadriflow rejects these directly, so the add-on rebuilds a watertight surface with a voxel remesh (coarse to fine) and quad-remeshes that.

Not yet verified: your real photoscan, and Blender 4.2.

## Install

Blender, Edit > Preferences > Add-ons > down arrow > Install from Disk, pick `blender_addon/dist/ai_asset_finisher.zip` (rebuild with `python blender_addon/build_zip.py`).
Then in the 3D viewport press N, open the **AI Asset** tab, pick the high-poly, open "1. Retopology" and click Retopologize.
