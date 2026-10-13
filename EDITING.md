# Update project images and team details

The website is served from `public/`. Commit changes to `main` in the existing GitHub repository; Cloudflare Pages automatically publishes them to https://plc-vlc.pages.dev/. No paid image service, CMS or subscription is needed.

## Add a gallery photograph

1. Open https://github.com/NduvhoEdward/plc_vlc/tree/main/public/assets and choose **Add file → Upload files**. Upload a descriptive filename such as `plc-adapters.webp` or `team-bench.jpg`, then commit. Keep filenames lowercase with hyphens and no spaces.
2. For quick phone loading, export photographs as WebP or JPEG, around 1,200 pixels wide and ideally below 300 KB. Keep a larger original separately. Upload PNG for circuit drawings when crisp labels matter.
3. Open https://github.com/NduvhoEdward/plc_vlc/edit/main/public/index.html. Find `<div class="gallery">` in the `id="gallery"` section. Copy an existing complete `<figure>...</figure>` and replace its image paths, alt text, title, caption and number. Both `href` and `src` must point to the uploaded file. Example:

```html
<figure>
  <a href="assets/plc-adapters.webp" target="_blank" rel="noopener">
    <img src="assets/plc-adapters.webp"
         alt="Our two PLC adapters connected to the router and gateway on the bench"
         width="1200" height="800" loading="lazy">
  </a>
  <figcaption>
    <span>05 / BENCH PHOTOGRAPH</span>
    <h3>The PLC connection</h3>
    <p>Our actual adapters carry data between the router and gateway through the mains wiring.</p>
  </figcaption>
</figure>
```

Set `width` and `height` to the image's real dimensions so the phone layout reserves the right space. Alt text describes what is visible; the caption explains why it matters. Label illustrations as illustrations, and photographs as photographs. The two PLC SVGs already on the site are conceptual drawings, not photographs of our hardware.

4. Once bench images are included, update or remove the `photo-pending` block beneath the gallery. Commit and check the live gallery on your phone after the Pages deployment finishes.

## Add the team

1. Upload portraits to `public/assets/` in the same way. Use a square crop, approximately 600 × 600 pixels, ideally below 150 KB. Example filename: `team-firstname.webp`.
2. Edit `public/index.html`, find the section `id="team"`, and replace the paragraph beginning **Team names, supervisor details…** with the following. Repeat the `<article>` for each member and replace all bracketed values before publishing:

```html
<div class="team-members">
  <article class="team-member">
    <img src="assets/team-firstname.webp" alt="Portrait of [Full name]"
         width="600" height="600" loading="lazy">
    <h3>[Full name]</h3>
    <p class="team-role">[Role, e.g. PLC integration and gateway]</p>
    <p>[One or two sentences about this person's contribution.]</p>
  </article>
</div>
<p><strong>Supervisor:</strong> [Name and title]</p>
<p><a href="mailto:project@example.com">Contact the project team</a></p>
```

Remove the contact paragraph if you do not have a public project email. A portrait is optional: remove the `<img>` and the card still works. The `.team-members` and `.team-member` styles are already included and stack on phones. The affiliation text is in the first half of the same section; edit it there if needed.

## Update the project explanation

The `id="purpose"` section holds the purpose, challenge and solution text. The `id="how"` section has the three signal-path cards. The `id="findings"` section holds measured results; add a date, test route and source whenever you change a measurement.

`public/project.js` drives the short handoff illustration. Its eight slots, six-packet bursts and two-packet output steps are teaching values, not firmware settings. `public/buffer.js` drives the separate longer buffer simulator. Neither controls the rig. Do not change studio payload limits to match illustration values.

## Preview before publishing

For local changes, double-click `launch-preview.cmd` and open http://127.0.0.1:4173. Test a narrow phone layout, tap the new images, and run the handoff comparison. Check portrait and landscape for horizontal scrolling. If editing on GitHub, use a branch and pull request for a larger update so it can be reviewed before merging.

If the live page still shows old content, check the **Deployments** tab of the existing `plc-vlc` Cloudflare Pages project, then refresh the phone page. The correct output directory remains `public`; there is no frontend build command.
