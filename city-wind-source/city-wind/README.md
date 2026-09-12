# 城市起風

Original Three.js city and scroll-driven narrative, inspired by PeakQi's dark presentation, warm accents, strong headlines and chapter-based structure.

## Run and maintain

This is a buildless static site. Serve `dist/` through any HTTP server. Three.js 0.180.0 is vendored locally; typography uses a Google Fonts stylesheet with system fallbacks. No npm installation is required.

- `dist/city.js`: deterministic original city geometry, ten architectural material/style families plus landmark silhouettes, roads, bridges, trees, five road-locked traffic routes, animated water, 45 citizens, survey lines and wind paths.
- `dist/props.js`: animated document texture, PBR appraiser figure and a magnifier with restrained screen-space optical distortion.
- `dist/app.js`: the single animation loop and integration layer; the original UI, chapter copy and document sequence remain unchanged.
- `dist/systems/state.js`: `ScrollController`, six-state scene machine and spline-based `CameraDirector`.
- `dist/systems/materials.js`: procedural PBR material library, asphalt maps, window temperatures and shared foliage wind shader.
- `dist/systems/lighting.js`: time of day, sun/moon/sky lighting and a pooled street-light manager.
- `dist/systems/parcel.js`: persistent target parcel, screen-space orange line and cadastral crossfade layer.
- `dist/systems/life.js`: crowd behaviours, SkinnedMesh/LOD people, three bird ranges, aircraft events and flags.
- `dist/systems/postprocessing.js`: artifact-safe emissive bloom, transition DOF and neutral finishing pass without depth-edge sampling.
- `dist/systems/quality.js`: HIGH, MEDIUM and LOW profiles plus adaptive resolution.
- `dist/style.css`: desktop, portrait and short landscape layouts.

The lens samples the rendered scene itself, with approximately 1.9× central magnification, radial distortion and subtle chromatic separation. Its optical centre remains locked to parcel 0128 during the inspection hold, then exits after the hold. The camera enters at street height before the survey close-up and moves continuously toward the document and appraisal scenes. Native page scrolling and reverse scrolling are preserved.

Scroll input is damped through a spring response and is never assigned directly to the camera. The camera follows centripetal spline keyframes with restrained inertia across `CITY_REVEAL`, `CITY_DISTRICT`, `STREET_LEVEL`, `TARGET_BLOCK`, `TARGET_PARCEL` and `CADASTRAL_VIEW`. Each state controls FOV, fog, exposure, sun/moon balance, parcel emphasis, cadastral opacity, building LOD, crowd density, birds and postprocessing. Rapid scroll and reverse scroll retain continuous interpolation.

The target parcel is a persistent independent layer using a custom screen-space polyline, so its `#FF7A18` outline stays approximately 2.8 CSS pixels on desktop instead of depending on `LineBasicMaterial.linewidth`. It includes a low-opacity fill, separate soft glow, polygon offset, disabled depth writing and high render order. The urban massing flattens while cadastral graphics fade in, producing a continuous crossfade rather than a visibility cut.

Scroll progress also controls a morning-to-night lighting timeline. The procedural sun drives the primary shadow light, while night adds cool moon/sky illumination. All 48 full street fixtures include a legible pole, arm, housing and emissive core plus inexpensive ground footprints; only the nearest 4–8 receive pooled realtime spot lights and only 1–4 cast shadows according to quality. Building windows are seeded per building at approximately 20–55% lit, split across 2700K–4000K groups with very slow, gentle switching. Sedans, taxis, vans, buses and scooters travel independently in both directions around multiple city blocks. Their rounded routes follow the road centre-lines and only turn inside intersections.

The asphalt is a dry, non-metallic PBR surface using procedural base-colour, roughness and normal detail at 128–256 px. Its power-of-two textures use trilinear mipmaps and anisotropic filtering to prevent shallow-angle moire. Night wetness lowers roughness to approximately 0.43 without becoming a mirror. Road markings gain restrained emissive response at night, and vehicle headlights add small additive road footprints. Concrete, brick, glass, metal, painted vehicles and cloth use intentionally different roughness/metalness/clearcoat/sheen responses under a generated environment map. Coplanar terrain decals and dense facade details do not enter the directional-light shadow pass, eliminating shadow-acne stripes; the document is also isolated from city shadows.

The streets include 45 independently phased pedestrians distributed across 18 professions. Behaviour includes walking, standing, phone checking, paired conversation, couple walking, waiting, sitting, cycling, dog walking and signal-aware road crossing. Building setbacks preserve continuous pedestrian clearance, ordinary NPCs remain on sidewalks, and crossing NPCs wait at the curb before walking only on marked crosswalks. Character +Z is aligned to path direction so animated figures walk forward instead of sliding sideways. Near figures use animated SkinnedMesh torsos, medium figures update less often, and far figures use billboard impostors. Only camera-near people cast shadows. Added landmarks include a cylindrical teal tower, a sawtooth-roof civic hall, a clock tower, stepped commercial roofs, rooftop water tanks and pyramid-roof blocks.

Birds are divided into animated near birds, a lower-cost mid flock and far silhouettes. Spline motion combines altitude/speed variation, shared wind, cohesion and short-range separation; morning and sunset density is higher and night density approaches zero. A high-altitude aircraft event occurs at randomized 40–120 second intervals, with red/green navigation lights and intermittent white strobes at night. Foliage and flags share one subtle wind direction and shader-driven timing.

Quality is selected automatically as HIGH, MEDIUM or LOW. Device pixel ratio is capped at 1.7, 1.25 or 1.0 respectively, then adaptive resolution can step down further when sustained FPS misses the profile target. The lower profiles also reduce realtime lights, shadow lights, crowd count, bird density, postprocessing and detail LOD. The project continues to use WebGL as the broad compatibility path; WebGPU/TSL/IES was intentionally not introduced because it would replace the current lightweight static renderer and weaken unsupported-device fallback.

All cadastral geometry, parcel numbers, document fields and comparison indices are illustrative. The document is an animation, not a data collection or submission form. The city is an original conceptual model rather than an accurate New Taipei survey.

The final scene currently uses the agency's name. The official emblem has not been substituted or recreated. Its reference page is https://www.land.ntpc.gov.tw/cp.aspx?n=12 . An official SVG or transparent PNG can be inserted in `#agency` when provided.

There is currently no external model loader or GLB asset set: the city is procedural and locally vendored, so no model-download waterfall is introduced. Geometry still uses InstancedMesh for repeated static parts, frustum culling, three crowd LOD tiers and small procedural textures; GLB compression, Meshopt/Draco and KTX2 would apply only when external hero models are added later.

Validation: JavaScript syntax, module references, state interpolation, adaptive DPR profiles, scene construction, NPC behaviours, crosswalk paths and animated vehicle routes were checked. Sampled vehicle positions stayed inside the road corridors, and sampled crossing NPCs stayed on designated crosswalks. The expanded scene contains approximately 150,000 triangles, 27 vehicles, 45 pedestrians, 12 SkinnedMesh figures and 10 far impostors before the narrative props. Browser-level visual QA is still recommended on representative physical devices.

Three.js is MIT-licensed; see `dist/THREE-LICENSE.txt`.
