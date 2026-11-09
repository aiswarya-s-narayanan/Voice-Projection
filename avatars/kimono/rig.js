/*
 * Rig for the "Indigo Kimono" character (avatar.jpg).
 *
 * The character is one flat picture, so the rig tells the engine where each part
 * is. All positions are pixels in the 941 x 1672 artwork (avatar.jpg is 2x that).
 * "Left" and "right" mean the viewer's left and right.
 */
(function (root, factory) {
  var rig = factory();
  if (typeof module === 'object' && module.exports) module.exports = rig;
  else (root.VoiceProjectionRigs = root.VoiceProjectionRigs || {})[rig.name] = rig;
})(typeof self !== 'undefined' ? self : this, function () {
  return {
    name: 'kimono',
    size: [941, 1672],

    // Flat background that gets cut away so the avatar floats on the page.
    background: { color: [254, 254, 254], tolerance: 16 },

    // Mesh density: `step` px inside the `fine` box (the face), `coarse` px elsewhere.
    mesh: { fine: [395, 130, 515, 275], step: 1.5, coarse: 6 },

    face: {
      origin: [455, 195],
      angle: -11.8, // the head leans to the left: the right eye sits higher
      eyes: [
        { outer: [402.7, 181.7], inner: [438.5, 181.2], top: [422.5, 171.3], bottom: [420.3, 185.0] },
        { inner: [472.0, 173.5], outer: [500.6, 163.0], top: [486.3, 157.0], bottom: [485.2, 173.5] },
      ],
      brows: [
        { center: [421.4, 155.9], inner: [433.0, 154.0] },
        { center: [483.0, 144.3], inner: [466.0, 149.0] },
      ],
      cheeks: [[418, 200], [488, 186]],
    },

    mouth: {
      // Line where the lips meet, from the left corner to the right corner.
      seam: [[440.6, 230.0], [442.5, 230.25], [450, 231.5], [460, 231.5], [470, 230.0], [480, 226.9], [487.5, 220.6], [488.5, 219.8]],
      maxOpen: 6.5, // how far the jaw drops for a wide "ah" (reduced for natural, subtle movement)
      jawHalfWidth: 40,
      chin: 34, // distance from the lips down to the bottom of the chin
    },

    head: {
      pivot: [468, 280], // top of the neck
      // Hat area: centre, brim angle, and [half-length along the brim, height above it, depth below it].
      hat: { center: [445.5, 152], angle: -15, radii: [210, 150, 95] },
      // Hanging charm: pivot = attachment point on hat brim; box = [x0,y0,x1,y1] tight around the tassel.
      // The charm swings as a pendulum when the head tilts.
      charm: { pivot: [557.5, 114], box: [545, 108, 578, 265] },
      // Face, hair and neck below the brim follow the head down to `top`, fading out by `bottom`.
      neck: { top: 262, bottom: 292, x: 478, halfWidth: 80 },
    },

    hands: {
      // Raised hand (viewer's left). It is drawn as its own layer so it can wave in
      // front of the kimono. `mask` is the box that holds the hand; it fades out over
      // `fade` (the wrist) into the forearm. `pivot` is the wrist.
      // `elbow` swings the forearm and the sleeve opening; its weight fades over the ranges given.
      wave: {
        pivot: [305, 410],
        mask: { rect: [200, 248, 336, 432], fade: [398, 430] },
        elbow: { pivot: [292, 560], right: [326, 340], top: [242, 256], bottom: [440, 540] },
      },
      // Open palm (viewer's right). The wrist bends at the cuff; the elbow sits inside the sleeve.
      palm: {
        pivot: [748, 618], left: [738, 760], top: [548, 568], bottom: [668, 690],
        elbow: { pivot: [640, 565], left: [655, 705], top: [515, 545], bottom: [660, 760] },
      },
    },

    body: { pivot: [470, 1650], sway: [1000, 1650], breath: [560, 760] },

    views: {
      full: { rect: [0, 0, 941, 1672] },
      close: { rect: [215, 5, 500, 500], anchor: 'top' },
    },
  };
});
