/*!
 * voice-projection v0.1.0
 * Give it text; the avatar speaks it with lip sync, facial expression and body gestures.
 *
 * Runs in the browser. The character is a single flat image: a WebGL mesh warp bends
 * the eyes, brows, lips, head, hands and body using landmark positions from a rig file.
 * The voice comes from the browser's Web Speech API (speechSynthesis).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(root || {});
  else root.VoiceProjection = factory(root);
})(typeof self !== 'undefined' ? self : (typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this)), function (root) {
  'use strict';

  const VERSION = '0.1.0';
  const DEG = Math.PI / 180;
  const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
  const lerp = (a, b, t) => a + (b - a) * t;
  const smooth01 = (t) => { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); };
  const approach = (cur, target, dt, tau) => cur + (target - cur) * (1 - Math.exp(-dt / tau));
  const envelope = (t, rise, fall, dur) => (t < 0 || t > dur ? 0 : smooth01(t / rise) * smooth01((dur - t) / fall));
  const bump = (t, dur) => (t < 0 || t > dur ? 0 : Math.sin((Math.PI * t) / dur));
  const noise = (t) => 0.6 * Math.sin(1.3 * t) + 0.3 * Math.sin(2.9 * t + 1.7) + 0.1 * Math.sin(5.3 * t + 0.4);
  const nextPow2 = (n) => 2 ** Math.ceil(Math.log2(n));
  const nowSec = () => (typeof performance !== 'undefined' ? performance.now() : Date.now()) / 1000;

  /* ------------------------------------------------------------------ *
   * Text analysis: sentences -> words -> mouth shapes, emotion, gestures
   * ------------------------------------------------------------------ */

  // Mouth shapes as [open 0..1, wide -1..1] (negative wide = rounded lips).
  const VISEME_SHAPES = {
    rest: [0, 0], MBP: [0, -0.05], A: [1, 0.12], E: [0.55, 0.55], I: [0.4, 0.7],
    O: [0.72, -0.62], U: [0.36, -0.9], W: [0.22, -0.95], FV: [0.16, 0.2],
    TH: [0.32, 0.2], L: [0.42, 0.15], SH: [0.3, -0.5], C: [0.28, 0.3],
  };
  // [shape, seconds at normal speed]
  const DIGRAPHS = {
    th: ['TH', 0.08], sh: ['SH', 0.09], ch: ['SH', 0.09], ph: ['FV', 0.08], wh: ['W', 0.07],
    oo: ['U', 0.13], ou: ['O', 0.13], ow: ['O', 0.13], oa: ['O', 0.13], au: ['O', 0.12], aw: ['O', 0.12],
    oi: ['O', 0.12], oy: ['O', 0.12], ee: ['I', 0.12], ea: ['I', 0.12], ie: ['I', 0.11], ai: ['E', 0.12],
    ay: ['E', 0.12], ey: ['E', 0.11], qu: ['W', 0.08], ck: ['C', 0.06], ng: ['C', 0.07], gh: ['C', 0.03],
  };
  const LETTERS = {
    a: ['A', 0.11], e: ['E', 0.09], i: ['I', 0.09], o: ['O', 0.11], u: ['U', 0.09], y: ['I', 0.07],
    m: ['MBP', 0.08], b: ['MBP', 0.07], p: ['MBP', 0.07], f: ['FV', 0.08], v: ['FV', 0.07],
    w: ['W', 0.07], r: ['W', 0.05], l: ['L', 0.06], s: ['C', 0.07], z: ['C', 0.07], x: ['C', 0.08], j: ['SH', 0.08],
  };
  // Non-Latin scripts: no letter rules, so use a natural-looking open/close rhythm.
  const OTHER_CYCLE = ['A', 'C', 'E', 'C', 'O', 'C', 'I', 'MBP'];

  function wordToVisemes(word) {
    const w = String(word).toLowerCase().replace(/['\u2019]/g, '');
    const out = [];
    const push = (v, d) => {
      const last = out[out.length - 1];
      if (last && last.v === v) last.d += d * 0.5;
      else out.push({ v, d });
    };
    for (let i = 0; i < w.length;) {
      const ch = w[i];
      if (ch >= '0' && ch <= '9') { push('A', 0.12); push('C', 0.1); i++; continue; }
      const two = DIGRAPHS[w.substr(i, 2)];
      if (two) { push(two[0], two[1]); i += 2; continue; }
      if (ch === 'e' && i === w.length - 1 && w.length > 2 && !/[aeiouy]/.test(w[i - 1])) { i++; continue; } // silent final e
      const one = LETTERS[ch];
      if (one) push(one[0], one[1]);
      else if (ch >= 'a' && ch <= 'z') push('C', 0.06);
      else push(OTHER_CYCLE[ch.codePointAt(0) % OTHER_CYCLE.length], 0.09);
      i++;
    }
    if (!out.length) out.push({ v: 'C', d: 0.08 });
    let t = 0;
    for (const s of out) { s.t0 = t; t += s.d; s.t1 = t; }
    return { visemes: out, dur: t };
  }

  // stem -> weight. Stems of 5+ letters also match longer words ("thank" -> "thanks").
  const LEXICON = {
    happy: {
      happy: 1, glad: 1, great: 1, love: 1, loved: 1, loves: 1, loving: 1, lovely: 1, awesome: 1, wonderful: 1,
      fantastic: 1, excellent: 1, nice: 1, good: 0.6, thank: 1, welcome: 1, enjoy: 1, fun: 1, beautiful: 1,
      perfect: 1, yay: 1, congrat: 1, smile: 1, smiling: 1, excit: 1, delight: 1, pleased: 1, haha: 1, best: 0.7,
      cute: 1, cool: 0.7, delicious: 1, tasty: 1, yummy: 1, fresh: 0.6, special: 0.5, favorite: 0.8, favourite: 0.8,
      popular: 0.6, sweet: 0.6, recommend: 0.4, ready: 0.4,
    },
    sad: {
      sad: 1, sorry: 1, unfortunate: 1, miss: 0.8, missed: 0.8, lost: 0.8, lonely: 1, cry: 1, crying: 1, bad: 0.8,
      terrible: 1, awful: 1, hurt: 1, pain: 1, painful: 1, tired: 0.8, sick: 0.8, regret: 1, upset: 1, depress: 1,
      disappoint: 1, afraid: 1, worri: 1, worry: 1, unavailable: 1, sold: 0.7, delay: 0.8,
    },
    surprised: {
      wow: 1.2, whoa: 1.2, really: 0.5, omg: 1.2, unbelievabl: 1, incredibl: 1, amazing: 0.8, surpris: 1,
      shock: 1, sudden: 0.6, oh: 0.6,
    },
    thinking: {
      think: 0.8, maybe: 1, perhaps: 1, wonder: 0.8, guess: 1, probabl: 0.8, consider: 0.8, possibl: 0.6,
      suppose: 1, curious: 0.8,
    },
    angry: { angry: 1.2, hate: 1.2, annoy: 1, furious: 1.2, mad: 1, stupid: 1, ridiculous: 1, unacceptabl: 1, outrag: 1 },
  };
  const EMOJI_RULES = [
    ['happy', /(\u{1F600}|\u{1F603}|\u{1F604}|\u{1F601}|\u{1F60A}|\u{1F642}|\u{1F60D}|\u{1F970}|\u2764|\u2665|:-?\)|:D)/u],
    ['sad', /(\u{1F622}|\u{1F62D}|\u{1F61E}|\u2639|\u{1F641}|:-?\()/u],
    ['surprised', /(\u{1F62E}|\u{1F632}|\u{1F62F}|\u{1F92F})/u],
    ['thinking', /\u{1F914}/u],
    ['angry', /(\u{1F620}|\u{1F621}|\u{1F92C})/u],
  ];
  const NEGATIONS = new Set(['not', 'no', 'never', 'dont', 'doesnt', 'didnt', 'isnt', 'wasnt', 'arent', 'cant', 'cannot', 'wont', 'aint', 'hardly']);
  const GREET = new Set(['hi', 'hello', 'hey', 'hiya', 'howdy', 'welcome', 'irasshaimase', 'bye', 'goodbye', 'namaste', 'konnichiwa', 'greetings', 'aloha', 'hola', 'ciao']);
  const WELCOME = new Set(['welcome', 'irasshaimase']);
  const THANKS = new Set(['thank', 'thanks', 'arigato', 'arigatou', 'grateful', 'appreciate']);
  const SORRY = new Set(['sorry', 'apologize', 'apologise', 'apologies']);
  const PRESENT = new Set(['this', 'these', 'here', 'look', 'see', 'show', 'introduce', 'offer', 'our', 'check', 'meet', 'recommend',
    'recommendation', 'choose', 'pick', 'option', 'options']);
  // Words that specifically mean "look at the menu / item" — trigger a pointing gesture instead of an open palm.
  const MENU_POINT = new Set(['menu', 'menus', 'special', 'specials', 'dish', 'dishes', 'item', 'items', 'order', 'orders',
    'today', 'available', 'selection', 'choice', 'choices', 'list']);
  const INVITE = new Set(['please', 'enjoy', 'come', 'try', 'taste']);
  const YES = new Set(['yes', 'yeah', 'yep', 'yup', 'sure', 'absolutely', 'exactly', 'agree', 'correct', 'definitely', 'indeed', 'okay', 'ok', 'certainly']);
  const CONFIRM = new Set(['added', 'confirmed', 'got', 'done', 'noted']);
  const NO = new Set(['no', 'nope', 'nah', 'never']);
  // Gestures that use the hands; two of them are kept a few words apart.
  const HAND_GESTURES = new Set(['welcome', 'wave', 'present', 'invite', 'explain', 'pointMenu']);

  function lexiconHits(word) {
    const hits = [];
    if (/^h+m+$/.test(word)) hits.push(['thinking', 1.2]);
    else if (/^(u+m+|u+h+|e+r+m+)$/.test(word)) hits.push(['thinking', 0.8]);
    for (const emo in LEXICON) {
      const table = LEXICON[emo];
      if (table[word] !== undefined) { hits.push([emo, table[word]]); continue; }
      for (const stem in table) {
        if (stem.length >= 5 && word.length > stem.length && word.startsWith(stem)) { hits.push([emo, table[stem]]); break; }
      }
    }
    return hits;
  }

  function detectLang(text) {
    if (/[\u0D00-\u0D7F]/.test(text)) return 'ml';
    if (/[\u0B80-\u0BFF]/.test(text)) return 'ta';
    if (/[\u0C00-\u0C7F]/.test(text)) return 'te';
    if (/[\u0C80-\u0CFF]/.test(text)) return 'kn';
    if (/[\u0900-\u097F]/.test(text)) return 'hi';
    if (/[\u3040-\u30FF]/.test(text)) return 'ja';
    if (/[\uAC00-\uD7AF]/.test(text)) return 'ko';
    if (/[\u4E00-\u9FFF]/.test(text)) return 'zh';
    if (/[\u0600-\u06FF]/.test(text)) return 'ar';
    return null;
  }

  function splitSentences(text) {
    const clean = String(text || '').replace(/\s+/g, ' ').trim();
    if (!clean) return [];
    const raw = clean.match(/[^.!?\u3002\uFF01\uFF1F\u2026]+(?:[.!?\u3002\uFF01\uFF1F\u2026]+|$)["'\u201D\u2019)\]]*/g) || [clean];
    const out = [];
    for (let s of raw) {
      s = s.trim();
      // Browser voices can cut off very long utterances, so split long sentences at a comma.
      while (s.length > 180) {
        let cut = s.lastIndexOf(',', 180);
        if (cut < 60) cut = s.lastIndexOf(' ', 180);
        if (cut < 1) cut = 180;
        out.push(s.slice(0, cut + 1).trim());
        s = s.slice(cut + 1).trim();
      }
      if (/[\p{L}\p{N}]/u.test(s)) out.push(s);
      else if (s && out.length) out[out.length - 1] += s;
    }
    return out;
  }

  function tokenize(sentence) {
    const re = /[\p{L}\p{N}\p{M}]+(?:['\u2019][\p{L}]+)*/gu;
    const words = [];
    let m;
    while ((m = re.exec(sentence))) {
      const start = m.index, end = start + m[0].length;
      const after = sentence.slice(end, end + 3);
      const pause = /^[,;:]/.test(after) ? 0.22 : /^[.!?\u2026\u3002\uFF01\uFF1F]/.test(after) ? 0.35 : /^\s*[-\u2013\u2014]/.test(after) ? 0.2 : 0.05;
      words.push(Object.assign({ text: m[0], norm: m[0].toLowerCase().replace(/['\u2019]/g, ''), start, end, pause }, wordToVisemes(m[0])));
    }
    return words;
  }

  function analyzeSentence(text) {
    const words = tokenize(text);
    const scores = { happy: 0, sad: 0, surprised: 0, thinking: 0, angry: 0 };
    words.forEach((w, i) => {
      const hits = lexiconHits(w.norm);
      if (GREET.has(w.norm)) hits.push(['happy', 0.6]);
      if (YES.has(w.norm)) hits.push(['happy', 0.5]);
      if (!hits.length) return;
      const negated = [words[i - 1], words[i - 2]].some((p) => p && NEGATIONS.has(p.norm));
      for (const [emo, weight] of hits) {
        if (negated && emo === 'happy') scores.sad += weight;
        else if (negated && (emo === 'sad' || emo === 'angry')) scores.happy += weight * 0.5;
        else scores[emo] += weight;
      }
    });
    for (const [emo, re] of EMOJI_RULES) if (re.test(text)) scores[emo] += 1.5;
    const exclaim = /[!\uFF01]/.test(text);
    const question = /[?\uFF1F]/.test(text);
    if (exclaim) {
      if (scores.surprised) scores.surprised += 0.5;
      if (scores.happy) scores.happy += 0.5;
    }
    let emotion = 'neutral', best = 0;
    for (const k in scores) if (scores[k] > best) { best = scores[k]; emotion = k; }
    if (best < 0.9) emotion = 'neutral';
    const intensity = emotion === 'neutral' ? 0 : clamp(0.55 + 0.18 * (best - 1) + (exclaim ? 0.2 : 0), 0.45, 1);

    // Body language, each bound to the word that triggers it.
    const gestures = [];
    const used = new Set();
    const add = (type, word) => { if (!used.has(type)) { used.add(type); gestures.push({ type, word }); } };
    const handBusy = (i, gap) => gestures.some((g) => HAND_GESTURES.has(g.type) && Math.abs(g.word - i) < gap);
    words.forEach((w, i) => {
      const n = w.norm, next = words[i + 1] ? words[i + 1].norm : '';
      let type = null;
      if (WELCOME.has(n)) type = 'welcome'; // wave, then a polite bow
      else if (GREET.has(n) || (n === 'good' && /^(morning|afternoon|evening|night)$/.test(next))) type = 'wave';
      else if (THANKS.has(n) || SORRY.has(n)) type = 'bow';
      else if (YES.has(n) || CONFIRM.has(n) || (n === 'of' && next === 'course')) type = 'nod';
      else if (NO.has(n)) type = 'shake';
      else if (MENU_POINT.has(n)) type = 'pointMenu'; // point hand toward the menu display
      else if (PRESENT.has(n)) type = 'present';
      else if (INVITE.has(n)) type = 'invite';
      if (!type) return;
      if (HAND_GESTURES.has(type) && handBusy(i, 3)) type = type === 'welcome' ? 'bow' : null;
      if (type) add(type, i);
    });
    if (question) add('tilt', Math.max(0, words.length - 3));
    if (exclaim && !used.has('wave') && !used.has('welcome')) add('emphasis', Math.max(0, words.length - 1));
    // Open each longer sentence with the hands, like someone starting to explain.
    if (words.length >= 4 && !handBusy(1, 3)) gestures.push({ type: 'explain', word: 1 });
    // Beats on stressed words keep both hands talking, alternating between them.
    let sinceBeat = 2, beats = 0;
    words.forEach((w, i) => {
      sinceBeat++;
      if (w.norm.length < 3 || sinceBeat < 2 || handBusy(i, 2) || gestures.some((g) => g.word === i)) return;
      gestures.push({ type: beats % 2 === 1 ? 'beatL' : 'beat', word: i, amp: clamp(0.55 + w.norm.length * 0.07, 0.7, 1.25) });
      sinceBeat = 0;
      beats++;
    });

    const estDuration = words.reduce((sum, w) => sum + w.dur + w.pause, 0);
    return { text, words, emotion, intensity, gestures, estDuration, lang: detectLang(text) };
  }

  function analyzeText(text) {
    return splitSentences(text).map(analyzeSentence);
  }

  /* ------------------------------------------------------------------ *
   * Emotions and gestures
   * ------------------------------------------------------------------ */

  const EMOTIONS = {
    neutral: { smile: 0, browL: 0, browR: 0, inner: 0, furrow: 0, eye: 0, open: 0, roll: 0, headY: 0 },
    happy: { smile: 1, browL: 0.3, browR: 0.3, inner: 0, furrow: 0, eye: 0.16, open: 0, roll: -1.5, headY: -0.6 },
    sad: { smile: -1, browL: 0, browR: 0, inner: 1, furrow: 0, eye: 0.3, open: 0, roll: 2.5, headY: 2.5 },
    surprised: { smile: -0.2, browL: 1, browR: 1, inner: 0.2, furrow: 0, eye: -0.35, open: 3.2, roll: 0, headY: -1.5 },
    thinking: { smile: -0.3, browL: 0.9, browR: 0, inner: 0, furrow: 0.45, eye: 0.14, open: 0, roll: -3.5, headY: 0.5 },
    angry: { smile: -0.7, browL: 0, browR: 0, inner: 0, furrow: 1, eye: 0.22, open: 0, roll: 0, headY: 1.2 },
  };

  // Each gesture adds to arm spring targets (elbowL/R, wristL/R in degrees; the arms reach them
  // with a little overshoot), to waveL/swingL (applied directly), and to roll (deg), x/y (px),
  // brow/browR, smile, eye (extra eye closing) and body (px, + = shoulders up).
  // L = raised hand, R = open palm. The raised hand moves mostly toward her body: swinging it
  // far outward would smear the kimono behind it.
  const GESTURES = {
    wave: {
      dur: 2.2,
      run(t, d, o) {
        const e = envelope(t, 0.3, 0.5, d), w = 2 * Math.PI * 1.9 * t;
        o.elbowL += 1 * e;
        o.swingL += (1.5 + 2.2 * Math.sin(w + 1.2)) * e; // the forearm leads...
        o.waveL += (3.5 + 6 * Math.sin(w)) * e; // ...and the hand follows
        o.smile += 0.35 * e; o.roll -= 1.2 * e; o.brow += 0.2 * e;
        // The raised sleeve pulls the left side of the kimono slightly.
        o.dressSwayL += (0.8 + 0.5 * Math.sin(w)) * e;
      },
    },
    // Polite Japanese bow: the head dips, the shoulders follow, the eyes soften into a smile.
    bow: {
      dur: 1.6,
      run(t, d, o) {
        const e = envelope(t, 0.4, 0.55, d);
        o.y += 6.5 * e; o.roll += 1.5 * e; o.body -= 2 * e;
        o.eye += 0.5 * e; o.smile += 0.4 * e;
        o.elbowR += 2.5 * e; o.elbowL += 1.5 * e;
        // Both sleeves compress downward; the whole dress compresses slightly.
        o.dressSwayL += 0.4 * e; o.dressSwayR += 0.4 * e;
      },
    },
    // Greeting a guest: wave, then bow.
    welcome: {
      dur: 3.4,
      run(t, d, o, amp) {
        GESTURES.wave.run(t, 2.0, o, amp);
        GESTURES.bow.run(t - 1.75, 1.6, o, amp);
        o.smile += 0.3 * envelope(t, 0.3, 0.6, d);
      },
    },
    present: { dur: 1.9, run(t, d, o) { const e = envelope(t, 0.3, 0.6, d); o.elbowR -= 7 * e; o.wristR -= 4 * e; o.elbowL += 1.5 * e; o.roll += 0.8 * e; o.brow += 0.25 * e; o.dressSwayR += 1.0 * e; } },
    // ── Point to menu ──────────────────────────────────────────────────────────
    // The right hand (open palm) extends fully toward where the menu is displayed,
    // wrist angled so the fingers lead the eye to the content.
    // Phase 1 (0 → 0.6s): arm shoots out and locks onto the menu.
    // Phase 2 (0.6 → 2.4s): a gentle left-to-right sweep scans across the items.
    //   The head follows the hand slightly (roll/x), giving an attentive "see this?"
    //   look. The body leans in a little (y) to close the distance.
    // Phase 3 (2.4 → 3.0s): arm eases back, body straightens.
    pointMenu: {
      dur: 3.0,
      run(t, d, o) {
        // ── reach out ──
        const eReach = envelope(t, 0.25, 0.65, 3.0);
        o.elbowR  -= 10.5 * eReach;    // forearm fully extended toward menu
        o.wristR  -= 6.5  * eReach;    // wrist cocks so fingers point, not palm
        o.elbowL  +=  1.0 * eReach;    // left arm lifts slightly for balance
        // ── sweep: a slow sinusoidal scan across menu items ──
        // Only active while the arm is out (0.5 s → 2.4 s).
        const eSweep = envelope(t - 0.5, 0.3, 0.5, 1.9);
        const sweep  = Math.sin(Math.PI * (t - 0.5) / 1.9);   // 0 → 1 → 0
        o.elbowR  -=  2.5 * sweep * eSweep;   // sweeps the forearm a little further
        o.wristR  -=  1.8 * sweep * eSweep;   // wrist follows
        // ── head tracks the hand ──
        o.roll    +=  1.8 * eReach;            // slight head lean toward menu side
        o.x       -=  1.2 * sweep * eSweep;   // head pans with the sweep
        o.y       +=  1.4 * eReach;            // lean forward a little
        // ── expression: focused, friendly ──
        o.brow    +=  0.35 * eReach;
        o.smile   +=  0.25 * eReach;
        // ── dress: sleeve fans out as the arm reaches ──
        o.dressSwayR += 1.4 * eReach + 0.5 * sweep * eSweep;
      },
    },
    // "Please, come in / have a look": the palm offers and lifts softly twice.
    invite: {
      dur: 2.0,
      run(t, d, o) {
        const e = envelope(t, 0.3, 0.5, d);
        o.elbowR -= 5 * e;
        o.wristR -= (2 + 4 * Math.max(0, Math.sin(2 * Math.PI * 1.5 * t))) * e;
        o.roll += 1.2 * e; o.smile += 0.3 * e; o.brow += 0.2 * e;
        // The right sleeve lifts and flutters.
        o.dressSwayR += (0.6 + 0.4 * Math.sin(2 * Math.PI * 1.5 * t)) * e;
      },
    },
    // Both hands open up a little as a sentence starts.
    explain: { dur: 1.5, run(t, d, o) { const e = envelope(t, 0.3, 0.6, d); o.elbowR -= 4 * e; o.wristR -= 2 * e; o.elbowL += 2 * e; o.wristL += 2 * e; o.dressSwayL += 0.5 * e; o.dressSwayR += 0.5 * e; } },
    nod: { dur: 0.9, run(t, d, o) { o.y += 3.2 * envelope(t, 0.08, 0.2, d) * (0.5 - 0.5 * Math.cos((2 * Math.PI * t) / 0.45)); } },
    shake: { dur: 1.0, run(t, d, o) { const s = Math.sin(2 * Math.PI * 2.6 * t) * envelope(t, 0.12, 0.3, d); o.x += 2.6 * s; o.roll += 1.4 * s; } },
    tilt: { dur: 2.0, run(t, d, o) { const e = envelope(t, 0.35, 0.6, d); o.roll -= 4 * e; o.browR += 0.6 * e; } },
    emphasis: { dur: 0.5, run(t, d, o) { const b = bump(t, d); o.y += 1.8 * b; o.brow += 0.45 * b; o.elbowR -= 4 * b; o.elbowL += 1.5 * b; o.dressSwayL += 0.6 * b; o.dressSwayR += 0.6 * b; } },
    beat: { dur: 0.42, run(t, d, o, amp) { const b = bump(t, d); o.elbowR -= 6 * amp * b; o.wristR -= 3 * amp * b; o.y += 0.3 * b; o.dressSwayR += 0.5 * amp * b; } },
    beatL: { dur: 0.45, run(t, d, o, amp) { const b = bump(t, d); o.elbowL += 3.5 * amp * b; o.wristL += 3 * amp * b; o.elbowR -= 1.5 * amp * b; o.dressSwayL += 0.5 * amp * b; } },
    bob: { dur: 0.3, run(t, d, o, amp) { const b = bump(t, d); o.y += 0.7 * amp * b; o.roll += 0.25 * amp * b; } },
  };

  const defaultPose = () => ({
    blinkL: 0, blinkR: 0, browL: 0, browR: 0, browInner: 0, browFurrow: 0, open: 0, wide: 0, smile: 0,
    headRoll: 0, headX: 0, headY: 0, wave: 0, palm: 0, armL: 0, armR: 0, sway: 0, breath: 0,
    dressSway: 0, charmAng: 0, wavePose: 0,
  });

  /* ------------------------------------------------------------------ *
   * Voices
   * ------------------------------------------------------------------ */

  const synth = typeof window !== 'undefined' && window.speechSynthesis ? window.speechSynthesis : null;
  const PREFERRED_VOICES = ['Samantha', 'Ava', 'Allison', 'Susan', 'Zoe', 'Karen', 'Moira', 'Tessa', 'Serena', 'Microsoft Aria', 'Microsoft Jenny', 'Microsoft Zira', 'Google UK English Female', 'Google US English'];
  const NOVELTY_VOICES = /Albert|Bad News|Bahh|Bells|Boing|Bubbles|Cellos|Good News|Jester|Organ|Superstar|Trinoids|Whisper|Wobble|Zarvox|Deranged|Hysterical|Junior|Ralph|Fred/;

  function loadVoices() {
    if (!synth) return Promise.resolve([]);
    const list = synth.getVoices();
    if (list.length) return Promise.resolve(list);
    return new Promise((resolve) => {
      let done = false;
      const finish = () => { if (!done) { done = true; resolve(synth.getVoices()); } };
      if (synth.addEventListener) synth.addEventListener('voiceschanged', finish, { once: true });
      else synth.onvoiceschanged = finish;
      setTimeout(finish, 2000);
    });
  }

  function scoreVoice(v, lang) {
    const vl = (v.lang || '').toLowerCase();
    let s = vl.startsWith(lang || 'en') ? 100 : 0;
    const i = PREFERRED_VOICES.findIndex((n) => v.name.includes(n));
    if (i >= 0) s += 40 - i;
    if (/female|woman/i.test(v.name)) s += 15;
    if (/\bmale\b/i.test(v.name)) s -= 15;
    if (NOVELTY_VOICES.test(v.name)) s -= 60;
    if (v.localService) s += 10; // local voices report word timing, which keeps the lips in sync
    if (vl === 'en-us' || vl === 'en_us') s += 3;
    return s;
  }

  /* ------------------------------------------------------------------ *
   * Image preparation: cut out the background, build the waving-hand mask
   * ------------------------------------------------------------------ */

  function loadImage(src) {
    if (!src) return Promise.reject(new Error('VoiceProjection: no avatar image given. Load the avatar image.js or pass options.image.'));
    if (typeof src !== 'string') {
      if (src.complete === false) return new Promise((res, rej) => { src.onload = () => res(src); src.onerror = rej; });
      return Promise.resolve(src);
    }
    return new Promise((resolve, reject) => {
      const img = new Image();
      if (!/^data:/.test(src)) img.crossOrigin = 'anonymous';
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('VoiceProjection: could not load the avatar image.'));
      img.src = src;
    });
  }

  function prepareImage(img, rig) {
    const w = img.naturalWidth || img.width, h = img.naturalHeight || img.height;
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const g = canvas.getContext('2d', { willReadFrequently: true });
    g.drawImage(img, 0, 0);
    const pixels = g.getImageData(0, 0, w, h);
    if (rig.background) knockOutBackground(pixels, rig.background.color, rig.background.tolerance || 12);
    const hand = liftHand(pixels, rig);
    g.putImageData(pixels, 0, 0);
    return { canvas, hand };
  }

  function prepareRestImage(img, rig) {
    if (!img) return null;
    const w = img.naturalWidth || img.width, h = img.naturalHeight || img.height;
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const g = canvas.getContext('2d', { willReadFrequently: true });
    g.drawImage(img, 0, 0);
    const pixels = g.getImageData(0, 0, w, h);
    if (rig.background) knockOutBackground(pixels, rig.background.color, rig.background.tolerance || 12);
    g.putImageData(pixels, 0, 0);
    return { canvas };
  }

  // Flood-fills the flat background from the image border and makes it transparent.
  function knockOutBackground(imageData, color, tol) {
    const { width: w, height: h, data: d } = imageData;
    const n = w * h;
    const bg = new Uint8Array(n);
    const stack = new Int32Array(n);
    let sp = 0;
    const visit = (i) => {
      if (bg[i]) return;
      const o = i * 4;
      if (Math.abs(d[o] - color[0]) > tol || Math.abs(d[o + 1] - color[1]) > tol || Math.abs(d[o + 2] - color[2]) > tol) return;
      bg[i] = 1;
      stack[sp++] = i;
    };
    for (let x = 0; x < w; x++) { visit(x); visit(n - w + x); }
    for (let y = 0; y < h; y++) { visit(y * w); visit(y * w + w - 1); }
    while (sp > 0) {
      const i = stack[--sp], x = i % w;
      if (x > 0) visit(i - 1);
      if (x < w - 1) visit(i + 1);
      if (i >= w) visit(i - w);
      if (i < n - w) visit(i + w);
    }
    for (let i = 0; i < n; i++) {
      if (bg[i]) { d[i * 4 + 3] = 0; continue; }
      const x = i % w, y = (i / w) | 0;
      const edge = (x > 0 && bg[i - 1]) || (x < w - 1 && bg[i + 1]) || (y > 0 && bg[i - w]) || (y < h - 1 && bg[i + w]);
      if (!edge) continue;
      // Soften the cut: edge alpha = share of figure pixels around it.
      let solid = 0, total = 0;
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const xx = x + dx, yy = y + dy;
          if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
          total++;
          if (!bg[yy * w + xx]) solid++;
        }
      }
      d[i * 4 + 3] = Math.round((255 * solid) / total);
    }
  }

  // Moves the raised hand onto its own small image (so it can wave in front of the
  // kimono) and fills the hole it leaves in the body image from the pixels around it.
  function liftHand(imageData, rig) {
    const spec = rig.hands && rig.hands.wave && rig.hands.wave.mask;
    if (!spec) return null;
    const { width: iw, height: ih, data: d } = imageData;
    const sx = iw / rig.size[0], sy = ih / rig.size[1];
    const x0 = Math.max(0, Math.floor(spec.rect[0] * sx)), y0 = Math.max(0, Math.floor(spec.rect[1] * sy));
    const x1 = Math.min(iw, Math.ceil(spec.rect[2] * sx)), y1 = Math.min(ih, Math.ceil(spec.rect[3] * sy));
    const w = x1 - x0, h = y1 - y0;
    const tw = nextPow2(w), th = nextPow2(h);
    const out = new ImageData(tw, th);
    const hole = new Uint8Array(w * h);
    for (let y = 0; y < h; y++) {
      const fade = 1 - smooth01(((y0 + y) / sy - spec.fade[0]) / (spec.fade[1] - spec.fade[0]));
      for (let x = 0; x < w; x++) {
        const o = ((y0 + y) * iw + x0 + x) * 4;
        if (d[o + 3] === 0 || d[o + 2] > d[o] + 8) continue; // background or kimono blue
        // Near-white pixels on the hand's outline are leftover background: drop them so no
        // white speck shows when the hand moves over the kimono.
        if (d[o] > 232 && d[o + 1] > 222 && d[o + 2] > 218 && nearTransparent(d, iw, ih, x0 + x, y0 + y, 2)) continue;
        const q = (y * tw + x) * 4;
        out.data[q] = d[o];
        out.data[q + 1] = d[o + 1];
        out.data[q + 2] = d[o + 2];
        out.data[q + 3] = Math.round(d[o + 3] * fade);
        if (fade > 0.99) hole[y * w + x] = 1; // across the wrist the forearm stays in the body image
      }
    }
    // Grow the hole 2 px: the soft edge where skin blends into the kimono is refilled with
    // clean kimono, so no light outline is left behind when the hand moves away.
    for (let pass = 0; pass < 2; pass++) {
      const grow = [];
      for (let y = 1; y < h - 1; y++) {
        for (let x = 1; x < w - 1; x++) {
          const i = y * w + x;
          if (hole[i] || d[((y0 + y) * iw + x0 + x) * 4 + 3] === 0) continue;
          if (hole[i - 1] || hole[i + 1] || hole[i - w] || hole[i + w]) grow.push(i);
        }
      }
      for (const i of grow) hole[i] = 1;
    }
    fillHole(d, iw, ih, x0, y0, w, h, hole, 10);
    const canvas = document.createElement('canvas');
    canvas.width = tw;
    canvas.height = th;
    canvas.getContext('2d').putImageData(out, 0, 0);
    return { canvas, rect: [x0 / sx, y0 / sy, tw / sx, th / sy] };
  }

  function nearTransparent(d, iw, ih, x, y, r) {
    for (let k = 1; k <= r; k++) {
      if ((x - k >= 0 && d[(y * iw + x - k) * 4 + 3] === 0) || (x + k < iw && d[(y * iw + x + k) * 4 + 3] === 0) ||
          (y - k >= 0 && d[((y - k) * iw + x) * 4 + 3] === 0) || (y + k < ih && d[((y + k) * iw + x) * 4 + 3] === 0)) return true;
    }
    return false;
  }

  // Grows the surrounding colours into the hole one ring per pass; what is left
  // after `passes` rings becomes transparent.
  function fillHole(d, iw, ih, x0, y0, w, h, hole, passes) {
    let pending = [];
    for (let i = 0; i < w * h; i++) if (hole[i]) pending.push(i);
    for (let pass = 0; pass < passes && pending.length; pass++) {
      const next = [], done = [];
      for (const i of pending) {
        const x = i % w, y = (i / w) | 0;
        let r = 0, g = 0, b = 0, a = 0, n = 0;
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            const xx = x + dx, yy = y + dy;
            if ((!dx && !dy) || x0 + xx < 0 || y0 + yy < 0 || x0 + xx >= iw || y0 + yy >= ih) continue;
            if (xx >= 0 && yy >= 0 && xx < w && yy < h && hole[yy * w + xx]) continue;
            const o = ((y0 + yy) * iw + x0 + xx) * 4, al = d[o + 3];
            r += d[o] * al; g += d[o + 1] * al; b += d[o + 2] * al; a += al; n++;
          }
        }
        if (n) done.push(i, r, g, b, a, n);
        else next.push(i);
      }
      for (let k = 0; k < done.length; k += 6) {
        const i = done[k], a = done[k + 4];
        const o = ((y0 + ((i / w) | 0)) * iw + x0 + (i % w)) * 4;
        if (a > 0) { d[o] = done[k + 1] / a; d[o + 1] = done[k + 2] / a; d[o + 2] = done[k + 3] / a; }
        d[o + 3] = a / done[k + 5];
        hole[i] = 0;
      }
      pending = next;
    }
    for (const i of pending) d[((y0 + ((i / w) | 0)) * iw + x0 + (i % w)) * 4 + 3] = 0;
  }

  /* ------------------------------------------------------------------ *
   * Geometry and mesh
   * ------------------------------------------------------------------ */

  const toFrame = (d, cs) => [d[0] * cs[0] + d[1] * cs[1], -d[0] * cs[1] + d[1] * cs[0]];

  function eyeGeometry(e) {
    const [p, q] = e.outer[0] < e.inner[0] ? [e.outer, e.inner] : [e.inner, e.outer];
    const c = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
    const ang = Math.atan2(q[1] - p[1], q[0] - p[0]);
    const cs = [Math.cos(ang), Math.sin(ang)];
    const a = Math.hypot(q[0] - p[0], q[1] - p[1]) / 2;
    const profile = (u) => Math.sqrt(Math.max(0.25, 1 - (u / a) ** 2));
    const top = toFrame([e.top[0] - c[0], e.top[1] - c[1]], cs);
    const bottom = toFrame([e.bottom[0] - c[0], e.bottom[1] - c[1]], cs);
    return { c, cs, a, up: -top[1] / profile(top[0]), low: bottom[1] / profile(bottom[0]) };
  }

  function deriveGeometry(rig) {
    const A = (rig.face.angle || 0) * DEG;
    const faceCS = [Math.cos(A), Math.sin(A)];
    const faceO = rig.face.origin;
    const toFace = (p) => toFrame([p[0] - faceO[0], p[1] - faceO[1]], faceCS);
    const seam = rig.mouth.seam.slice().sort((a, b) => a[0] - b[0]);
    const L = seam[0], R = seam[seam.length - 1];
    const mc = [(L[0] + R[0]) / 2, (L[1] + R[1]) / 2];
    const ma = Math.atan2(R[1] - L[1], R[0] - L[0]);
    const mcs = [Math.cos(ma), Math.sin(ma)];
    let depth = 0, lo = Infinity, hi = -Infinity;
    for (const p of seam) {
      depth = Math.max(depth, toFrame([p[0] - mc[0], p[1] - mc[1]], mcs)[1]);
      lo = Math.min(lo, p[1]);
      hi = Math.max(hi, p[1]);
    }
    return {
      faceO, faceCS,
      eyes: rig.face.eyes.map(eyeGeometry),
      brows: rig.face.brows.map((b) => ({ c: toFace(b.center), inner: toFace(b.inner) })),
      cheeks: rig.face.cheeks.map(toFace),
      mouth: {
        seam, seamRef: (lo + hi) / 2, c: mc, cs: mcs, depth,
        hw: Math.hypot(R[0] - L[0], R[1] - L[1]) / 2,
        jawHalfWidth: rig.mouth.jawHalfWidth, chin: rig.mouth.chin,
      },
    };
  }

  function axisSteps(max, f0, f1, coarse, fine) {
    const out = [];
    for (let v = 0; v < f0 - 0.5; v += coarse) out.push(v);
    for (let v = f0; v < f1 - 0.25; v += fine) out.push(v);
    for (let v = f1; v < max - 0.5; v += coarse) out.push(v);
    out.push(max);
    return out;
  }

  // Vertical offset that bends the two mesh rows around the mouth seam onto the lip line.
  function seamOffset(x, seam, ref) {
    const first = seam[0], last = seam[seam.length - 1];
    let y = first[1];
    if (x >= last[0]) y = last[1];
    else if (x > first[0]) {
      for (let i = 1; i < seam.length; i++) {
        if (x <= seam[i][0]) {
          const p = seam[i - 1], q = seam[i];
          y = p[1] + ((q[1] - p[1]) * (x - p[0])) / (q[0] - p[0]);
          break;
        }
      }
    }
    const outside = x < first[0] ? first[0] - x : x > last[0] ? x - last[0] : 0;
    return (y - ref) * (1 - smooth01(outside / 22));
  }

  // Grid over the whole image. Two rows hug the lip line: triangles between them
  // stretch when the jaw opens and are painted as the inside of the mouth.
  function buildMesh(rig, geo) {
    const [W, H] = rig.size;
    const { fine: box, step = 1.5, coarse = 6 } = rig.mesh;
    const xs = axisSteps(W, box[0], box[2], coarse, step);
    const { seam, seamRef: ref } = geo.mouth;
    const yA = ref - 0.5, yB = ref + 0.5;
    const ys = axisSteps(H, box[1], box[3], coarse, step).filter((y) => y < yA - 0.45 || y > yB + 0.45);
    ys.push(yA, yB);
    ys.sort((a, b) => a - b);

    const cols = xs.length, rows = ys.length;
    const vertices = new Float32Array(cols * rows * 3);
    let k = 0;
    for (let j = 0; j < rows; j++) {
      const y = ys[j];
      const side = y <= yA ? -1 : 1;
      const bend = 1 - smooth01((Math.abs(y - ref) - 1) / 18);
      for (let i = 0; i < cols; i++) {
        vertices[k++] = xs[i];
        vertices[k++] = bend > 0 ? y + seamOffset(xs[i], seam, ref) * bend : y;
        vertices[k++] = side;
      }
    }
    const indices = new Uint32Array((cols - 1) * (rows - 1) * 6);
    k = 0;
    for (let j = 0; j < rows - 1; j++) {
      for (let i = 0; i < cols - 1; i++) {
        const a = j * cols + i, b = a + 1, c = a + cols, d = c + 1;
        indices[k++] = a; indices[k++] = c; indices[k++] = b;
        indices[k++] = b; indices[k++] = c; indices[k++] = d;
      }
    }
    // Index range for the rows that hold the waving hand (drawn as a second layer).
    let handFirst = 0, handCount = 0;
    const spec = rig.hands && rig.hands.wave && rig.hands.wave.mask;
    if (spec) {
      let j0 = 0, j1 = rows - 1;
      while (j0 < rows - 1 && ys[j0 + 1] <= spec.rect[1]) j0++;
      while (j1 > 0 && ys[j1 - 1] >= spec.rect[3]) j1--;
      handFirst = j0 * (cols - 1) * 6;
      handCount = (j1 - j0) * (cols - 1) * 6;
    }
    return { vertices, indices, handFirst, handCount };
  }

  /* ------------------------------------------------------------------ *
   * WebGL renderer
   * ------------------------------------------------------------------ */

  const VERTEX_SHADER = `
precision highp float;
attribute vec3 aPos; // rest position in image px, and which side of the lip line it is on
uniform vec2 uSize, uViewC, uViewS;
uniform mediump float uLayer; // 0 = body, 1 = waving hand (shared with the fragment shader)
uniform vec2 uFaceO, uFaceR;
uniform vec4 uEye0, uEye0b, uEye1, uEye1b;
uniform vec2 uBlink;
uniform vec4 uBrows, uBrowInner, uBrowCtl, uCheeks;
uniform vec4 uMouth, uMouthG, uMouthCtl;
uniform vec2 uHeadPivot;
uniform vec4 uHat;
uniform vec3 uHatR;
uniform vec4 uNeck;
uniform vec3 uHeadCtl;
uniform vec2 uWavePivot;
uniform float uWaveAng;
uniform vec4 uHandRect;
uniform vec3 uElbowL, uElbowR; // pivot, angle
uniform vec2 uElbowLX, uElbowRX;
uniform vec4 uElbowLY, uElbowRY;
uniform vec2 uPalmPivot, uPalmX;
uniform vec4 uPalmY;
uniform float uPalmAng;
uniform vec2 uBodyPivot, uSwayY, uBreathY;
uniform float uSway, uBreath, uDressSway;
uniform mediump float uWavePose;      // 0 = resting (hand on stomach), 1 = waving (hand raised) (shared with fragment shader)
uniform vec2 uCharmPivot;    // hat charm attachment point (rig px)
uniform vec4 uCharmBox;      // charm bounding rect [x0,y0,x1,y1] (rig px)
uniform float uCharmAng;     // pendulum swing angle (radians)
varying vec2 vUV, vHandUV;
varying float vSide, vGap, vMU, vTeeth;

vec2 toFrame(vec2 d, vec2 cs) { return vec2(d.x * cs.x + d.y * cs.y, -d.x * cs.y + d.y * cs.x); }
vec2 fromFrame(vec2 d, vec2 cs) { return vec2(d.x * cs.x - d.y * cs.y, d.x * cs.y + d.y * cs.x); }
vec2 rotateAround(vec2 p, vec2 c, float a) { return c + fromFrame(p - c, vec2(cos(a), sin(a))); }
float blob(vec2 p, vec2 c, vec2 r, float i, float o) { return 1.0 - smoothstep(i, o, length((p - c) / r)); }

// Upper lid slides down to the lower lid; skin above it stretches, the eye squeezes shut.
vec2 eyeLid(vec2 p, vec4 E, vec4 F, float k) {
  vec2 d = toFrame(p - E.xy, F.xy);
  float e = sqrt(max(0.0, 1.0 - d.x * d.x / (E.z * E.z)));
  float yu = -F.z * e;
  float yc = F.w * e;
  float top = yu - (0.9 * F.z * e + 2.5);
  float yu2 = mix(yu, yc, k);
  float v = d.y;
  float nv = v;
  if (v > top && v < yu) nv = top + (v - top) * (yu2 - top) / max(yu - top, 1e-4);
  else if (v >= yu && v < yc) nv = yu2 + (v - yu) * (yc - yu2) / max(yc - yu, 1e-4);
  return fromFrame(vec2(0.0, nv - v), F.xy);
}

vec2 faceOffset(vec2 p) {
  vec2 d = eyeLid(p, uEye0, uEye0b, uBlink.x) + eyeLid(p, uEye1, uEye1b, uBlink.y);
  vec2 l = toFrame(p - uFaceO, uFaceR);
  float bl = blob(l, uBrows.xy, vec2(24.0, 10.0), 0.6, 1.3);
  float br = blob(l, uBrows.zw, vec2(24.0, 10.0), 0.6, 1.3);
  float il = blob(l, uBrowInner.xy, vec2(13.0, 10.0), 0.4, 1.2);
  float ir = blob(l, uBrowInner.zw, vec2(13.0, 10.0), 0.4, 1.2);
  vec2 f = vec2(1.5 * uBrowCtl.w * (il - ir), 0.0);
  f.y -= 3.2 * (uBrowCtl.x * bl + uBrowCtl.y * br) + (2.6 * uBrowCtl.z - 1.8 * uBrowCtl.w) * (il + ir);
  float ch = blob(l, uCheeks.xy, vec2(20.0, 14.0), 0.3, 1.0) + blob(l, uCheeks.zw, vec2(20.0, 14.0), 0.3, 1.0);
  f.y -= 1.3 * max(uMouthCtl.z, 0.0) * ch;
  return d + fromFrame(f, uFaceR);
}

vec2 mouthOffset(vec2 p, float side) {
  vec2 m = toFrame(p - uMouth.xy, uMouth.zw);
  float hw = uMouthG.x;
  float ohw = hw * (1.0 + 0.3 * min(uMouthCtl.y, 0.0)); // rounded lips (O, U) open only in the middle
  float q = min(m.x * m.x / (hw * hw), 1.0);
  float e = pow(max(0.0, 1.0 - m.x * m.x / (ohw * ohw)), 0.8);
  float vs = m.y - uMouthG.y * (1.0 - q); // distance below the lip line
  float open = uMouthCtl.x;
  vec2 d = vec2(0.0);
  if (side > 0.0) {
    float jaw = 1.0 - smoothstep(hw * 0.9, uMouthG.z, abs(m.x));
    float prof = mix(e, jaw, smoothstep(1.0, 9.0, vs));
    d.y = open * 0.8 * prof * (1.0 - smoothstep(uMouthG.w, uMouthG.w + 24.0, vs));
  } else {
    d.y = -open * 0.2 * e * (1.0 - smoothstep(0.0, 8.0, -vs));
  }
  float cw = smoothstep(0.2 * hw, hw, abs(m.x)) * (1.0 - smoothstep(hw + 3.0, hw + 16.0, abs(m.x))) * (1.0 - smoothstep(4.0, 14.0, abs(m.y)));
  float sx = m.x < 0.0 ? -1.0 : 1.0;
  d.x += sx * cw * (uMouthCtl.y * 4.5 + max(uMouthCtl.z, 0.0) * 0.8);
  d.y -= cw * uMouthCtl.z * 2.4;
  vGap = open * e;
  vMU = m.x / ohw;
  vTeeth = smoothstep(-0.9, 0.1, uMouthCtl.y);
  return fromFrame(d, uMouth.zw);
}

void main() {
  vec2 p = aPos.xy;
  vec2 q = p + faceOffset(p) + mouthOffset(p, aPos.z);
  // Raised arm: the hand layer bends at the wrist, then hand + forearm swing from the elbow.
  q = rotateAround(q, uWavePivot, uWaveAng * uLayer);
  float wArmL = max(uLayer, (1.0 - smoothstep(uElbowLX.x, uElbowLX.y, p.x)) * smoothstep(uElbowLY.x, uElbowLY.y, p.y) * (1.0 - smoothstep(uElbowLY.z, uElbowLY.w, p.y)));
  q = rotateAround(q, uElbowL.xy, uElbowL.z * wArmL * mix(0.1, 1.0, uWavePose));
  // Open palm: wrist at the cuff, then the elbow inside the sleeve.
  float wPalm = smoothstep(uPalmX.x, uPalmX.y, p.x) * smoothstep(uPalmY.x, uPalmY.y, p.y) * (1.0 - smoothstep(uPalmY.z, uPalmY.w, p.y));
  q = rotateAround(q, uPalmPivot, uPalmAng * wPalm);
  float wArmR = smoothstep(uElbowRX.x, uElbowRX.y, p.x) * smoothstep(uElbowRY.x, uElbowRY.y, p.y) * (1.0 - smoothstep(uElbowRY.z, uElbowRY.w, p.y));
  q = rotateAround(q, uElbowR.xy, uElbowR.z * wArmR * (1.0 - uLayer));
  vec2 h = toFrame(p - uHat.xy, uHat.zw);
  float hatR = length(vec2(h.x / uHatR.x, h.y / (h.y < 0.0 ? uHatR.y : uHatR.z)));
  float wNeck = (1.0 - smoothstep(uNeck.x, uNeck.y, p.y)) * (1.0 - smoothstep(uNeck.w, uNeck.w + 30.0, abs(p.x - uNeck.z)));
  float wHead = max(1.0 - smoothstep(1.0, 1.14, hatR), wNeck) * (1.0 - uLayer);
  q = rotateAround(q, uHeadPivot, uHeadCtl.x * wHead) + uHeadCtl.yz * wHead;
  // ── Hat charm pendulum ────────────────────────────────────────────────────
  // The charm is already carried with the head above. Now add the extra swing
  // that lags behind due to inertia (driven by uCharmAng, a JS spring).
  //
  // wCharm ramps from 0 at the pivot (the charm doesn't move at its top)
  // to 1 at the tassel tip, so only the lower portion arcs outward.
  // The region is masked to the charm bounding box using the rest position p.
  float inCharmX = (1.0 - smoothstep(uCharmBox.x - 2.0, uCharmBox.x + 4.0, p.x))
                   + smoothstep(uCharmBox.z - 4.0, uCharmBox.z + 2.0, p.x);
  inCharmX = 1.0 - clamp(inCharmX, 0.0, 1.0);           // 1 inside x band, 0 outside
  float inCharmY = smoothstep(uCharmBox.y, uCharmBox.y + 6.0, p.y)
                 * (1.0 - smoothstep(uCharmBox.w - 6.0, uCharmBox.w, p.y));
  // Pendulum weight: 0 at top (pivot), 1 at bottom (tip) — linear ramp inside the box.
  float charmT    = clamp((p.y - uCharmPivot.y) / max(uCharmBox.w - uCharmPivot.y, 1.0), 0.0, 1.0);
  float wCharm    = charmT * inCharmX * inCharmY * (1.0 - uLayer);
  q = rotateAround(q, uCharmPivot, uCharmAng * wCharm);
  q.y -= uBreath * (1.0 - smoothstep(uBreathY.x, uBreathY.y, p.y));
  q = rotateAround(q, uBodyPivot, uSway * (1.0 - smoothstep(uSwayY.x, uSwayY.y, p.y)));
  // Dress sway: the lower skirt (below mid-torso) fans out gently when the arms move.
  // wDress ramps from 0 at the waist to 1 at the hem; the displacement is horizontal,
  // creating a natural pendulum-like swing of the fabric behind the arm motion.
  float wDress = smoothstep(uSwayY.x * 0.55, uBodyPivot.y, p.y) * (1.0 - uLayer);
  q.x += uDressSway * wDress * (p.y - uSwayY.x * 0.55) * 0.004;
  vUV = p / uSize;
  vHandUV = (p - uHandRect.xy) / uHandRect.zw;
  vSide = aPos.z;
  gl_Position = vec4((q - uViewC) * uViewS, 0.0, 1.0);
}`;

  const FRAGMENT_SHADER = `
precision mediump float;
uniform sampler2D uTex, uHandTex, uTexRest;
uniform mediump float uLayer;
uniform mediump float uWavePose;
uniform mediump float uHasRest;
varying vec2 vUV, vHandUV;
varying float vSide, vGap, vMU, vTeeth;
void main() {
  vec4 c;
  if (uLayer > 0.5) {
    if (uHasRest > 0.5 && uWavePose < 0.005) discard;
    c = texture2D(uHandTex, vHandUV);
    if (uHasRest > 0.5) {
      // Scales BOTH RGB and alpha for premultiplied alpha blending (gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
      c *= uWavePose;
    }
  } else {
    vec4 cWave = texture2D(uTex, vUV);
    if (uHasRest > 0.5) {
      vec4 cRest = texture2D(uTexRest, vUV);
      c = mix(cRest, cWave, uWavePose);
    } else {
      c = cWave;
    }
  }
  if (c.a < 0.003) discard;
  if (uLayer < 0.5 && abs(vSide) < 0.999 && vGap > 0.05) {
    // Inside of the open mouth: dark-red cavity, upper teeth, tongue.
    float t = vSide * 0.5 + 0.5;
    float y = t * vGap;
    float sideFade = abs(vMU);
    // Dark-red cavity: front is a rich crimson-red, sides deepen toward dark burgundy.
    vec3 col = mix(vec3(0.52, 0.06, 0.08), vec3(0.30, 0.03, 0.05), smoothstep(0.5, 1.0, sideFade));
    float teethH = min(vGap * 0.3, 2.4);
    float teeth = (1.0 - smoothstep(teethH - 0.5, teethH + 0.35, y)) * smoothstep(2.2, 4.5, vGap) * (1.0 - smoothstep(0.42, 0.75, sideFade)) * vTeeth;
    col = mix(col, vec3(0.92, 0.88, 0.86), teeth * 0.95);
    float tongue = smoothstep(0.5, 0.95, t) * smoothstep(3.5, 7.0, vGap) * (1.0 - smoothstep(0.35, 0.7, sideFade));
    // Tongue is a soft warm pink against the red cavity.
    col = mix(col, vec3(0.78, 0.32, 0.34), tongue * 0.85);
    col *= mix(0.72, 1.0, smoothstep(0.0, 0.2, min(t, 1.0 - t)));
    c.rgb = mix(c.rgb, col * c.a, smoothstep(0.0, 1.2, vGap));
  }
  gl_FragColor = c;
}`;

  function compile(gl, type, src) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error('VoiceProjection shader error: ' + gl.getShaderInfoLog(sh));
    return sh;
  }

  function createProgram(gl) {
    const prog = gl.createProgram();
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERTEX_SHADER));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error('VoiceProjection link error: ' + gl.getProgramInfoLog(prog));
    return prog;
  }

  function uploadImageTexture(gl, source, isGL2, unit) {
    const max = gl.getParameter(gl.MAX_TEXTURE_SIZE);
    let tw = source.width, th = source.height;
    if (!isGL2) { tw = Math.min(nextPow2(tw), max); th = Math.min(nextPow2(th), max); } // WebGL1 needs power-of-two sizes for mipmaps
    else if (tw > max || th > max) { const f = max / Math.max(tw, th); tw = Math.floor(tw * f); th = Math.floor(th * f); }
    let src = source;
    if (tw !== source.width || th !== source.height) {
      src = document.createElement('canvas');
      src.width = tw;
      src.height = th;
      const g = src.getContext('2d');
      g.imageSmoothingQuality = 'high';
      g.drawImage(source, 0, 0, tw, th);
    }
    const tex = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src);
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return tex;
  }

  class Renderer {
    constructor(canvas, rig, prepared, preparedRest, opts) {
      if (preparedRest && !preparedRest.canvas && !opts) {
        opts = preparedRest;
        preparedRest = null;
      }
      opts = opts || {};
      const attrs = { alpha: true, premultipliedAlpha: true, antialias: true, preserveDrawingBuffer: !!opts.preserveDrawingBuffer };
      let gl = canvas.getContext('webgl2', attrs);
      this.isGL2 = !!gl;
      if (!gl) gl = canvas.getContext('webgl', attrs) || canvas.getContext('experimental-webgl', attrs);
      if (!gl) throw new Error('VoiceProjection: WebGL is not available in this browser.');
      if (!this.isGL2 && !gl.getExtension('OES_element_index_uint')) throw new Error('VoiceProjection: this browser cannot draw large meshes.');
      this.gl = gl;
      this.canvas = canvas;
      this.prog = createProgram(gl);
      gl.useProgram(this.prog);
      this.loc = {};
      const n = gl.getProgramParameter(this.prog, gl.ACTIVE_UNIFORMS);
      for (let i = 0; i < n; i++) {
        const name = gl.getActiveUniform(this.prog, i).name;
        this.loc[name] = gl.getUniformLocation(this.prog, name);
      }

      const geo = deriveGeometry(rig);
      const mesh = buildMesh(rig, geo);
      this.count = mesh.indices.length;
      this.handFirst = mesh.handFirst;
      this.handCount = mesh.handCount;
      gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
      gl.bufferData(gl.ARRAY_BUFFER, mesh.vertices, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer());
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.indices, gl.STATIC_DRAW);
      const aPos = gl.getAttribLocation(this.prog, 'aPos');
      gl.enableVertexAttribArray(aPos);
      gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 12, 0);

      uploadImageTexture(gl, prepared.canvas, this.isGL2, 0);
      this.set('uTex', 0, 'int');
      if (prepared.hand) {
        uploadImageTexture(gl, prepared.hand.canvas, this.isGL2, 1);
        this.set('uHandTex', 1, 'int');
        const r = prepared.hand.rect;
        this.set('uHandRect', r[0], r[1], r[2], r[3]);
      } else {
        this.handCount = 0;
      }
      if (preparedRest && preparedRest.canvas) {
        uploadImageTexture(gl, preparedRest.canvas, this.isGL2, 2);
        this.set('uTexRest', 2, 'int');
        this.set('uHasRest', 1.0);
        this.hasRest = true;
      } else {
        this.set('uTexRest', 0, 'int');
        this.set('uHasRest', 0.0);
        this.hasRest = false;
      }
      this._setStatic(rig, geo);
      gl.disable(gl.DEPTH_TEST);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    }

    set(name, a, b, c, d) {
      const l = this.loc[name];
      if (!l) return;
      const gl = this.gl;
      if (b === 'int') gl.uniform1i(l, a);
      else if (d !== undefined) gl.uniform4f(l, a, b, c, d);
      else if (c !== undefined) gl.uniform3f(l, a, b, c);
      else if (b !== undefined) gl.uniform2f(l, a, b);
      else gl.uniform1f(l, a);
    }

    _setStatic(rig, g) {
      const s = this.set.bind(this);
      s('uSize', rig.size[0], rig.size[1]);
      s('uFaceO', g.faceO[0], g.faceO[1]);
      s('uFaceR', g.faceCS[0], g.faceCS[1]);
      g.eyes.slice(0, 2).forEach((e, i) => {
        s('uEye' + i, e.c[0], e.c[1], e.a, 0);
        s('uEye' + i + 'b', e.cs[0], e.cs[1], e.up, e.low);
      });
      s('uBrows', g.brows[0].c[0], g.brows[0].c[1], g.brows[1].c[0], g.brows[1].c[1]);
      s('uBrowInner', g.brows[0].inner[0], g.brows[0].inner[1], g.brows[1].inner[0], g.brows[1].inner[1]);
      s('uCheeks', g.cheeks[0][0], g.cheeks[0][1], g.cheeks[1][0], g.cheeks[1][1]);
      s('uMouth', g.mouth.c[0], g.mouth.c[1], g.mouth.cs[0], g.mouth.cs[1]);
      s('uMouthG', g.mouth.hw, g.mouth.depth, g.mouth.jawHalfWidth, g.mouth.chin);
      const head = rig.head;
      const ha = head.hat.angle * DEG;
      s('uHeadPivot', head.pivot[0], head.pivot[1]);
      s('uHat', head.hat.center[0], head.hat.center[1], Math.cos(ha), Math.sin(ha));
      s('uHatR', head.hat.radii[0], head.hat.radii[1], head.hat.radii[2]);
      s('uNeck', head.neck.top, head.neck.bottom, head.neck.x, head.neck.halfWidth);
      // Hat charm: upload pivot + bounding box (use safe fallback if rig has no charm).
      const charm = head.charm || { pivot: [0, -999], box: [0, -999, 0, -998] };
      s('uCharmPivot', charm.pivot[0], charm.pivot[1]);
      s('uCharmBox',   charm.box[0],   charm.box[1], charm.box[2], charm.box[3]);
      const wave = rig.hands.wave, palm = rig.hands.palm;
      s('uWavePivot', wave.pivot[0], wave.pivot[1]);
      s('uPalmPivot', palm.pivot[0], palm.pivot[1]);
      s('uPalmX', palm.left[0], palm.left[1]);
      s('uPalmY', palm.top[0], palm.top[1], palm.bottom[0], palm.bottom[1]);
      // Rigs without elbows get regions that weigh nothing.
      const el = wave.elbow || { pivot: [0, 0], right: [-2, -1], top: [0, 1], bottom: [2, 3] };
      const er = palm.elbow || { pivot: [0, 0], left: [1e5, 1e5 + 1], top: [0, 1], bottom: [2, 3] };
      this.elbowL = el.pivot;
      this.elbowR = er.pivot;
      s('uElbowLX', el.right[0], el.right[1]);
      s('uElbowLY', el.top[0], el.top[1], el.bottom[0], el.bottom[1]);
      s('uElbowRX', er.left[0], er.left[1]);
      s('uElbowRY', er.top[0], er.top[1], er.bottom[0], er.bottom[1]);
      const body = rig.body;
      s('uBodyPivot', body.pivot[0], body.pivot[1]);
      s('uSwayY', body.sway[0], body.sway[1]);
      s('uBreathY', body.breath[0], body.breath[1]);
    }

    draw(P, view) {
      const gl = this.gl, cw = this.canvas.width, ch = this.canvas.height;
      const s = this.set.bind(this);
      gl.viewport(0, 0, cw, ch);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      s('uViewC', view.cx, view.cy);
      s('uViewS', (2 * view.s) / cw, (-2 * view.s) / ch);
      s('uBlink', P.blinkL, P.blinkR);
      s('uBrowCtl', P.browL, P.browR, P.browInner, P.browFurrow);
      s('uMouthCtl', P.open, P.wide, P.smile, 0);
      s('uHeadCtl', P.headRoll * DEG, P.headX, P.headY);
      s('uWaveAng', P.wave * DEG);
      s('uPalmAng', P.palm * DEG);
      s('uElbowL', this.elbowL[0], this.elbowL[1], P.armL * DEG);
      s('uElbowR', this.elbowR[0], this.elbowR[1], P.armR * DEG);
      s('uSway', P.sway * DEG);
      s('uBreath', P.breath);
      s('uDressSway', P.dressSway || 0);
      s('uCharmAng',  P.charmAng  || 0);
      s('uWavePose',  P.wavePose !== undefined ? P.wavePose : 1.0);
      s('uLayer', 0);
      gl.drawElements(gl.TRIANGLES, this.count, gl.UNSIGNED_INT, 0);
      const waveAlpha = P.wavePose !== undefined ? P.wavePose : 1.0;
      if (this.handCount && (!this.hasRest || waveAlpha > 0.002)) {
        s('uLayer', 1);
        gl.drawElements(gl.TRIANGLES, this.handCount, gl.UNSIGNED_INT, this.handFirst * 4);
      }
    }
  }

  /* ------------------------------------------------------------------ *
   * Avatar
   * ------------------------------------------------------------------ */

  function resolveRig(rig) {
    if (rig && typeof rig === 'object') return rig;
    const registry = root.VoiceProjectionRigs || {};
    const name = rig || Object.keys(registry)[0];
    if (!registry[name]) throw new Error(`VoiceProjection: rig "${name}" not found. Load its rig.js first or pass the rig object.`);
    return registry[name];
  }

  class Avatar {
    constructor(container, options = {}) {
      if (!container) throw new Error('VoiceProjection: a container element is required.');
      this.opts = Object.assign({ view: 'full', voice: true, rate: 1, pitch: 1.08, maxPixelRatio: 2 }, options);
      this.rig = resolveRig(this.opts.rig);
      this.container = container;
      this.canvas = document.createElement('canvas');
      this.canvas.style.cssText = 'display:block;width:100%;height:100%;';
      container.appendChild(this.canvas);

      this.voiceEnabled = this.opts.voice !== false && !!synth;
      this.rate = this.opts.rate;
      this.pitch = this.opts.pitch;
      this.voices = [];
      this.voice = null;

      this.pose = defaultPose();
      this.wavePose = 0; // Starts with hand resting over stomach on obi
      this.expr = Object.assign({}, EMOTIONS.neutral);
      this.exprTarget = Object.assign({}, EMOTIONS.neutral);
      this.emotion = 'neutral';
      this.mouth = { open: 0, wide: 0 };
      this.armL = { e: 0, ve: 0, w: 0, vw: 0 }; // elbow and wrist angle + speed, raised hand
      this.armR = { e: 0, ve: 0, w: 0, vw: 0 }; // same for the open palm
      this.gestures = [];
      this.lip = null;
      this.talk = 0;
      this.nextBlink = nowSec() + 1.2;
      this.blinkStart = -10;
      this.relaxAt = 0;
      this.frozen = null;
      this._token = 0;

      this.viewName = this.rig.views[this.opts.view] ? this.opts.view : 'full';
      this.viewFrom = null;
      this.viewStart = 0;
      this.customView = null;

      this._tick = this._tick.bind(this);
      this.voicesReady = loadVoices().then((list) => {
        this.voices = list.slice().sort((a, b) => scoreVoice(b) - scoreVoice(a));
        this.voice = (this.opts.voiceName && this.voices.find((v) => v.name === this.opts.voiceName)) || this.voices[0] || null;
        return this.voices;
      });
      this.ready = this._init();
    }

    async _init() {
      const images = root.VoiceProjectionImages || {};
      const img = await loadImage(this.opts.image || images[this.rig.name] || this.rig.image);
      let imgRest = null;
      try {
        const restSrc = this.opts.imageRest || images[this.rig.name + '_rest'] || this.rig.imageRest;
        if (restSrc) imgRest = await loadImage(restSrc);
      } catch (e) {
        // Fallback gracefully if rest pose image is not available
      }
      const prepWave = prepareImage(img, this.rig);
      const prepRest = imgRest ? prepareRestImage(imgRest, this.rig) : null;
      this.renderer = new Renderer(this.canvas, this.rig, prepWave, prepRest, this.opts);
      this._resize();
      if (typeof ResizeObserver !== 'undefined') {
        this._observer = new ResizeObserver(() => this._resize());
        this._observer.observe(this.container);
      } else {
        this._onResize = () => this._resize();
        window.addEventListener('resize', this._onResize);
      }
      this._last = nowSec();
      this._raf = requestAnimationFrame(this._tick);
      return this;
    }

    /* ---- public API ---- */

    // Speaks the text; resolves when finished (or when stopped / replaced).
    async speak(text) {
      await this.ready;
      const interrupting = !!synth && (synth.speaking || synth.pending);
      this.stop();
      const token = ++this._token;
      // Chrome can silently drop an utterance queued right after cancel().
      if (interrupting) await new Promise((r) => setTimeout(r, 80));
      if (token !== this._token) return;
      const sentences = analyzeText(text);
      this.relaxAt = 0;
      for (let i = 0; i < sentences.length; i++) {
        if (token !== this._token) return;
        await this._speakSentence(sentences[i], i, sentences.length);
      }
      if (token !== this._token) return;
      this.relaxAt = nowSec() + 1.4;
      if (this.opts.onEnd) this.opts.onEnd();
    }

    stop() {
      this._token++;
      if (this.lip) this._endSentence(this.lip);
      if (synth && (synth.speaking || synth.pending)) synth.cancel();
    }

    setEmotion(name, intensity = 1) {
      this._setExprTarget(name, clamp(intensity, 0, 1));
      this.relaxAt = 0;
    }

    // Greets a new guest without speaking: a happy wave, then a polite bow.
    welcome() {
      this.gesture('welcome');
      this._setExprTarget('happy', 0.8);
      this.relaxAt = nowSec() + 4;
    }

    gesture(type, amp = 1) {
      const def = GESTURES[type];
      if (!def) return;
      const t = nowSec();
      if (type !== 'bob' && type !== 'beat' && type !== 'beatL' && type !== 'explain' && this.gestures.some((g) => g.type === type && t - g.start < def.dur * 0.8)) return;
      this.gestures.push({ type, start: t, amp });
    }

    setView(name) {
      if (!this.rig.views[name] || name === this.viewName) return;
      const t = nowSec();
      this.viewFrom = this._currentView(t);
      this.viewStart = t;
      this.viewName = name;
    }

    // Frame any rectangle of the artwork: [x, y, width, height]; anchor 'center' or 'top'.
    setViewRect(rect, anchor) {
      this.customView = rect ? { rect, anchor } : null;
      this.viewFrom = null;
    }

    async getVoices() { return this.voicesReady; }
    setVoice(name) { this.voice = this.voices.find((v) => v.name === name) || this.voice; }
    setVoiceEnabled(on) {
      this.voiceEnabled = !!on && !!synth;
      if (!this.voiceEnabled && synth) synth.cancel();
    }
    setRate(rate) { this.rate = clamp(+rate || 1, 0.5, 2); }

    // Hold a fixed pose (for testing and screenshots); call with null to resume animation.
    renderPose(pose) {
      this.frozen = pose ? Object.assign(defaultPose(), pose) : null;
      if (this.frozen) this._render(this.frozen, nowSec());
    }

    destroy() {
      this.stop();
      cancelAnimationFrame(this._raf);
      if (this._observer) this._observer.disconnect();
      if (this._onResize) window.removeEventListener('resize', this._onResize);
      const lose = this.renderer && this.renderer.gl.getExtension('WEBGL_lose_context');
      if (lose) lose.loseContext();
      this.canvas.remove();
    }

    /* ---- speech and lip sync ---- */

    _speakSentence(s, index, total) {
      return new Promise((resolve) => {
        const L = { s, index, wordIdx: -1, wordStart: nowSec(), pace: 1 / this.rate, synced: false, lastBoundary: false, speaking: false, silent: false, done: false, resolve };
        this.lip = L;
        this._setExprTarget(s.emotion, s.intensity);
        if (this.opts.onSentence) this.opts.onSentence(s, index, total);

        if (!this.voiceEnabled || !synth) {
          L.silent = true;
          this._startWord(L, 0, nowSec(), false);
          return;
        }
        const u = new SpeechSynthesisUtterance(s.text);
        const voice = this._voiceFor(s.lang);
        if (voice) { u.voice = voice; u.lang = voice.lang; }
        u.rate = this.rate;
        u.pitch = this.pitch;
        u.onstart = () => {
          if (L.done) return;
          L.speaking = true;
          if (L.wordIdx < 0) this._startWord(L, 0, nowSec(), false);
        };
        u.onboundary = (e) => {
          if (L.done || (e.name && e.name !== 'word')) return;
          L.speaking = true;
          L.synced = true;
          const idx = s.words.findIndex((w) => e.charIndex < w.end);
          if (idx > L.wordIdx) this._startWord(L, idx, nowSec(), true);
          else if (idx === L.wordIdx) L.lastBoundary = true;
        };
        const finish = () => this._endSentence(L);
        u.onend = finish;
        u.onerror = finish;
        L.utterance = u; // keep a reference: Chrome can drop events of garbage-collected utterances
        // Safety nets for browsers that never fire onstart / onend.
        L.startTimer = setTimeout(() => {
          if (!L.done && L.wordIdx < 0) { L.speaking = true; this._startWord(L, 0, nowSec(), false); }
        }, 1200);
        L.endTimer = setTimeout(finish, ((s.estDuration / this.rate) * 2.5 + 5) * 1000);
        synth.speak(u);
      });
    }

    _voiceFor(lang) {
      if (!lang) return this.voice;
      const best = this.voices.slice().sort((a, b) => scoreVoice(b, lang) - scoreVoice(a, lang))[0];
      return best && (best.lang || '').toLowerCase().startsWith(lang) ? best : this.voice;
    }

    _startWord(L, idx, t, fromBoundary, loop) {
      const words = L.s.words;
      if (idx < 0 || idx >= words.length) return;
      const prev = L.wordIdx;
      // Learn the real speaking pace from word-boundary events.
      if (fromBoundary && L.lastBoundary && prev >= 0 && idx > prev) {
        let est = 0;
        for (let k = prev; k < idx; k++) est += words[k].dur + words[k].pause;
        L.pace = clamp(L.pace * 0.5 + ((t - L.wordStart) / Math.max(0.08, est)) * 0.5, 0.5, 2.2);
      }
      L.lastBoundary = !!fromBoundary;
      L.wordIdx = idx;
      L.wordStart = t;
      if (!loop) {
        for (let k = prev + 1; k <= idx; k++) {
          for (const g of L.s.gestures) if (g.word === k) this.gesture(g.type, g.amp || 1);
        }
        if (this.opts.onWord) this.opts.onWord(idx, L.s, L.index);
      }
      this.gesture('bob', clamp(words[idx].dur * 2.2, 0.3, 1));
    }

    _endSentence(L) {
      if (L.done) return;
      L.done = true;
      clearTimeout(L.startTimer);
      clearTimeout(L.endTimer);
      if (this.lip === L) this.lip = null;
      L.resolve();
    }

    _lipShape(t) {
      const L = this.lip;
      if (!L || L.wordIdx < 0) return VISEME_SHAPES.rest;
      const words = L.s.words, w = words[L.wordIdx];
      const el = (t - L.wordStart) / L.pace;
      if (el < w.dur) {
        for (const v of w.visemes) if (el < v.t1) return VISEME_SHAPES[v.v];
      }
      if (!L.synced && el >= w.dur + w.pause) {
        // No word timing from the voice: advance on our own estimate.
        if (L.wordIdx + 1 < words.length) this._startWord(L, L.wordIdx + 1, t, false);
        else if (L.silent) this._endSentence(L);
        else this._startWord(L, 0, t, false, true); // voice still talking: keep the lips moving
      }
      return VISEME_SHAPES.rest;
    }

    _setExprTarget(name, intensity) {
      const base = EMOTIONS.neutral, emo = EMOTIONS[name] || base;
      for (const k in base) this.exprTarget[k] = base[k] + (emo[k] - base[k]) * intensity;
      this.emotion = EMOTIONS[name] ? name : 'neutral';
    }

    /* ---- animation ---- */

    _tick() {
      this._raf = requestAnimationFrame(this._tick);
      const t = nowSec();
      const dt = clamp(t - this._last, 0, 0.1);
      this._last = t;
      this._render(this.frozen || this._animate(t, dt), t);
    }

    _animate(t, dt) {
      if (this.relaxAt && t >= this.relaxAt) { this.relaxAt = 0; this._setExprTarget('neutral', 0); }
      const E = this.expr;
      for (const k in E) E[k] = approach(E[k], this.exprTarget[k], dt, 0.3);

      if (t >= this.nextBlink) {
        this.blinkStart = t;
        this.nextBlink = t + (Math.random() < 0.18 ? 0.32 : 2 + Math.random() * 3.8);
      }
      const bt = t - this.blinkStart;
      const blink = bt < 0.075 ? smooth01(bt / 0.075) : bt < 0.2 ? 1 - smooth01((bt - 0.075) / 0.125) : 0;

      const shape = this._lipShape(t);
      this.talk = approach(this.talk, this.lip ? 1 : 0, dt, 0.4);
      // Natural mouth: fast snap open (tau 0.022), slower relaxed close (tau 0.065).
      // A tiny jaw-tremor noise (±3 % of current opening) prevents the mouth from locking
      // into a mechanical steady state between phonemes.
      const openTarget = shape[0] + noise(t * 6.5 + 1.3) * 0.03 * this.mouth.open;
      this.mouth.open = approach(this.mouth.open, openTarget, dt, openTarget > this.mouth.open ? 0.022 : 0.065);
      // Lip-width transitions slightly faster than height so the shape arrives together.
      this.mouth.wide = approach(this.mouth.wide, shape[1], dt, 0.048);

      const g = { roll: 0, x: 0, y: 0, elbowL: 0, elbowR: 0, wristL: 0, wristR: 0, waveL: 0, swingL: 0, brow: 0, browR: 0, smile: 0, eye: 0, body: 0, dressSwayL: 0, dressSwayR: 0 };
      this.gestures = this.gestures.filter((gs) => {
        const def = GESTURES[gs.type], age = t - gs.start;
        if (age > def.dur) return false;
        def.run(age, def.dur, g, gs.amp);
        return true;
      });

      // Hand pose transition:
      // The hand rests serenely over her stomach/obi belt by default.
      // During welcome: the hand smoothly raises (0 -> 0.32s), waves (0.32s -> 1.50s),
      // smoothly returns to her stomach (1.50s -> 1.95s), and settles cleanly (0.0)
      // before her polite bow (1.75s -> 3.4s).
      // After greeting, her hand stays resting over her stomach.
      let targetWave = 0;
      if (this.renderer && !this.renderer.hasRest) {
        targetWave = 1.0; // single-image rigs without rest image stay in default raised pose
      } else {
        const activeWave = this.gestures.find((gs) => gs.type === 'welcome' || gs.type === 'wave');
        if (activeWave) {
          const age = t - activeWave.start;
          if (activeWave.type === 'welcome') {
            targetWave = envelope(age, 0.32, 0.45, 1.95);
          } else {
            targetWave = envelope(age, 0.32, 0.45, 2.05);
          }
        }
      }
      if (targetWave > 0) {
        this.wavePose = targetWave;
      } else if (this.wavePose > 0) {
        this.wavePose = approach(this.wavePose, 0, dt, 0.12);
        if (this.wavePose < 0.003) this.wavePose = 0;
      } else {
        this.wavePose = 0;
      }

      // Arms drift with her breathing, move more while she talks, and gestures ride on top.
      const breath = 0.5 - 0.5 * Math.cos((t * 2 * Math.PI) / 4.2);
      const talk = this.talk;
      // When resting on the stomach, damp the raised arm's idle drift/speech noise.
      const armLWeight = Math.max(0.08, this.wavePose);
      // A slow drift plus a quicker one while talking. Soft limits keep stacked gestures inside
      // the range that stays clean (the raised hand may only swing a little outward).
      const soft = (v, neg, pos) => (v < 0 ? neg * Math.tanh(v / neg) : pos * Math.tanh(v / pos));
      this._armStep(this.armL, dt,
        soft(g.elbowL + (noise(t * 0.31 + 3) * 1.2 + (0.6 + noise(t * 0.83 + 5)) * 2 * talk - breath * 0.5) * armLWeight, 3, 7),
        soft(g.wristL + (noise(t * 0.47 + 7) * 1.6 + (0.4 + noise(t * 1.1 + 9)) * 2.2 * talk) * armLWeight, 2.5, 10));
      this._armStep(this.armR, dt,
        soft(g.elbowR + noise(t * 0.29 + 11) * 1.4 + noise(t * 0.77 + 15) * 2.8 * talk - breath * 0.9 - talk * 2.5, 11, 4),
        soft(g.wristR + noise(t * 0.53 + 13) * 1.4 + noise(t * 1.2 + 17) * 2.2 * talk, 8, 3));

      const motion = 1 + talk * 0.9;
      const P = this.pose;
      P.wavePose = this.wavePose;
      P.blinkL = P.blinkR = clamp(blink + (E.eye + g.eye) * (1 - blink), -0.45, 1);
      P.browL = E.browL + g.brow;
      P.browR = E.browR + g.brow + g.browR;
      P.browInner = E.inner;
      P.browFurrow = E.furrow;
      P.open = this.mouth.open * this.rig.mouth.maxOpen + E.open * (1 - this.talk * 0.6);
      P.wide = this.mouth.wide;
      P.smile = clamp(E.smile + g.smile, -1.2, 1.4);
      P.headRoll = E.roll + g.roll + noise(t * 0.35) * 0.9 * motion;
      P.headX = g.x + noise(t * 0.27 + 10) * 0.8 * motion;
      P.headY = E.headY + g.y + noise(t * 0.5 + 20) * 0.5 * motion;
      P.armL = clamp(this.armL.e + g.swingL, -3.5, 8);
      P.wave = clamp(this.armL.w + g.waveL, -3, 12);
      P.armR = clamp(this.armR.e, -12, 4.5);
      P.palm = clamp(this.armR.w, -9, 3);
      P.sway = Math.sin((t * 2 * Math.PI) / 7.5) * 0.22 + noise(t * 0.2 + 5) * 0.1;
      P.breath = breath * 1.6 + g.body;
      // Dress-sway: arm gestures stir the lower kimono via a lagged spring on dressSway.
      // The spring target is built from each arm's current elbow angle (which already includes
      // gesture + noise) so the fabric follows the arms naturally and settles behind them.
      const dressTarget = ((this.armL.e * armLWeight) * 0.08 + g.dressSwayL * 0.18) - (this.armR.e * 0.06 + g.dressSwayR * 0.14);
      this._dressSway = approach(this._dressSway || 0, dressTarget, dt, 0.55);
      P.dressSway = this._dressSway;

      // ── Hat charm pendulum ────────────────────────────────────────────────
      // Physical model: simple damped spring where the rest position is 0 (vertical).
      // The driving force is proportional to the head's current roll angle — when the
      // head tilts, inertia swings the charm in the opposite direction (negative sign),
      // amplified slightly because the charm is long and light.
      // Spring constants chosen for a loose, lightly-damped pendulum feel:
      //   k = 38  (restoring stiffness — not too taut)
      //   c =  5  (damping — allows 1-2 natural oscillations before settling)
      if (!this._charm) this._charm = { ang: 0, vel: 0 };
      const ch = this._charm;
      // Target angle: counter-swing proportional to head roll (deg → rad internally).
      // The charm also picks up a tiny tremor from the head's natural noise motion.
      const charmDrive = -(P.headRoll * DEG) * 1.4;
      const steps = Math.max(1, Math.ceil(dt * 200));
      const h = dt / steps;
      for (let i = 0; i < steps; i++) {
        ch.vel += (38 * (charmDrive - ch.ang) - 5 * ch.vel) * h;
        ch.ang += ch.vel * h;
      }
      P.charmAng = ch.ang;
      return P;
    }

    // Damped springs (slight overshoot, then settle). The wrist is pulled back against the
    // elbow's speed, so the hand trails the forearm like a real one.
    _armStep(a, dt, elbowTarget, wristTarget) {
      const steps = Math.max(1, Math.ceil(dt * 120));
      const h = dt / steps;
      for (let i = 0; i < steps; i++) {
        a.ve += (55 * (elbowTarget - a.e) - 8.5 * a.ve) * h;
        a.e += a.ve * h;
        a.vw += (110 * (wristTarget - 0.07 * a.ve - a.w) - 12 * a.vw) * h;
        a.w += a.vw * h;
      }
    }

    /* ---- view and drawing ---- */

    _fit() {
      const v = this.customView || this.rig.views[this.viewName];
      const [x, y, w, h] = v.rect;
      const cw = this.canvas.width, ch = this.canvas.height;
      const s = Math.min(cw / w, ch / h);
      return { cx: x + w / 2, cy: v.anchor === 'top' ? y + ch / s / 2 : y + h / 2, s };
    }

    _currentView(t) {
      const target = this._fit();
      if (!this.viewFrom) return target;
      const p = smooth01((t - this.viewStart) / 0.7);
      if (p >= 1) { this.viewFrom = null; return target; }
      const f = this.viewFrom;
      return { cx: lerp(f.cx, target.cx, p), cy: lerp(f.cy, target.cy, p), s: f.s * Math.pow(target.s / f.s, p) };
    }

    _resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, this.opts.maxPixelRatio);
      const r = this.container.getBoundingClientRect();
      const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
      if (this.canvas.width !== w || this.canvas.height !== h) {
        this.canvas.width = w;
        this.canvas.height = h;
        this.viewFrom = null;
      }
      if (this.frozen) this._render(this.frozen, nowSec());
    }

    _render(P, t) {
      if (this.renderer) this.renderer.draw(P, this._currentView(t));
    }
  }

  async function createAvatar(container, options) {
    const avatar = new Avatar(container, options);
    await avatar.ready;
    return avatar;
  }

  return { version: VERSION, createAvatar, Avatar, analyzeText, wordToVisemes, EMOTIONS, GESTURES: Object.keys(GESTURES).filter((g) => g !== 'bob') };
});
