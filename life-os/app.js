/* LIFE OS — application personnelle de suivi.
   Code public. Aucune donnée personnelle ici : le plan, l'audit et le journal vivent dans
   un dépôt GitHub privé, lus et écrits avec une clé d'accès gardée sur l'appareil.
   Fichiers du dépôt de données :
     plan.json                 plan sur 90 jours, audit, cibles (écrit par Claude)
     jours/AAAA-MM.json        { "AAAA-MM-JJ": { coucher, reveil, energie, p1..p3, p1_ok.., salle, ... } }
     semaines/AAAA.json        { "<lundi AAAA-MM-JJ>": { atteints, non_atteints, ... } } */
(function () {
  "use strict";

  /* ================= Outils ================= */
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return ESC[c]; }); }
  function ty(s) { return String(s).replace(/ ([:;?!»])/g, " $1").replace(/« /g, "« "); }
  function tx(s) { return ty(esc(s)); }
  function clone(o) { return JSON.parse(JSON.stringify(o == null ? {} : o)); }
  function pad(n) { return String(n).padStart(2, "0"); }
  function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function parseISO(s) { var p = s.split("-"); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function addDays(s, n) { var d = parseISO(s); d.setDate(d.getDate() + n); return iso(d); }
  function diffDays(a, b) { return Math.round((parseISO(b) - parseISO(a)) / 86400000); }
  function mondayOf(s) { var d = parseISO(s); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return iso(d); }
  /* La journée bascule à 05:00 : un bilan écrit à 01:30 compte pour la veille. */
  function today() { var d = new Date(); if (d.getHours() < 5) d.setDate(d.getDate() - 1); return iso(d); }
  var fLong = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" });
  var fShort = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function longDate(s) { return cap(fLong.format(parseISO(s))); }
  function shortDate(s) { return fShort.format(parseISO(s)); }
  var D1 = ["L", "M", "M", "J", "V", "S", "D"];
  function tmin(s) { if (!s || !/^\d{1,2}:\d{2}/.test(s)) return null; var p = s.split(":"); return (+p[0]) * 60 + (+p[1]); }
  function night(m) { return m < 720 ? m + 1440 : m; }
  function sleepMin(c, r) { var a = tmin(c), b = tmin(r); if (a == null || b == null) return null; var d = (b - a + 1440) % 1440; return d < 60 ? null : d; }
  function dur(m) { m = Math.round(m); return Math.floor(m / 60) + " h " + pad(m % 60); }
  function clock(m) { m = Math.round(m) % 1440; return pad(Math.floor(m / 60)) + ":" + pad(m % 60); }
  function num(v) { if (v == null || v === "") return null; var n = parseFloat(String(v).replace(",", ".")); return isNaN(n) ? null : n; }
  function fr(n, d) { if (n == null) return "—"; var k = Math.pow(10, d || 0); return String(Math.round(n * k) / k).replace(".", ","); }
  function avg(a) { return a.length ? a.reduce(function (x, y) { return x + y; }, 0) / a.length : null; }
  var CHECK = '<svg viewBox="0 0 16 16"><path d="M3 8.5l3.2 3L13 4.8"/></svg>';

  /* ================= Stockage local ================= */
  var LS = {
    get: function (k) { try { var v = localStorage.getItem("los:" + k); return v ? JSON.parse(v) : null; } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem("los:" + k, JSON.stringify(v)); return true; } catch (e) { return false; } },
    del: function (k) { try { localStorage.removeItem("los:" + k); } catch (e) { /* rien */ } }
  };
  var cfg = LS.get("cfg") || { token: "", repo: "brunframe/life-os-data" };
  /* files[path] = { sha, data, dirty: { clé: rev }, pulledAt } */
  var files = LS.get("files") || {};
  var saveTimer = null;
  function persist() { clearTimeout(saveTimer); saveTimer = setTimeout(function () { LS.set("files", files); }, 150); }
  function file(path) { if (!files[path]) files[path] = { sha: null, data: {}, dirty: {}, pulledAt: 0 }; return files[path]; }

  /* ================= Synchronisation GitHub ================= */
  var SYNC = { state: "idle", error: null, timer: null, running: false, lastOk: null };
  function b64enc(str) { var bytes = new TextEncoder().encode(str), bin = ""; for (var i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000)); return btoa(bin); }
  function b64dec(b64) { var bin = atob(String(b64).replace(/\s/g, "")), bytes = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i); return new TextDecoder().decode(bytes); }
  function api(method, path, body) {
    return fetch("https://api.github.com/repos/" + cfg.repo + "/contents/" + path, {
      method: method, cache: "no-store",
      headers: Object.assign({ "Authorization": "Bearer " + cfg.token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" }, body ? { "Content-Type": "application/json" } : {}),
      body: body ? JSON.stringify(body) : undefined
    });
  }
  function httpError(r) { var e = new Error("http " + r.status); e.status = r.status; return e; }
  function pull(path) {
    return api("GET", path).then(function (r) {
      var f = file(path);
      if (r.status === 404) { f.pulledAt = Date.now(); return false; }
      if (!r.ok) throw httpError(r);
      return r.json().then(function (j) {
        var remote = {};
        try { remote = JSON.parse(b64dec(j.content)); } catch (e) { remote = {}; }
        var merged = remote;
        Object.keys(f.dirty).forEach(function (k) { if (f.data[k] !== undefined) merged[k] = f.data[k]; });
        var changed = JSON.stringify(merged) !== JSON.stringify(f.data);
        f.data = merged; f.sha = j.sha; f.pulledAt = Date.now();
        persist();
        return changed;
      });
    });
  }
  function push(path, retried) {
    var f = file(path), keys = Object.keys(f.dirty);
    if (!keys.length) return Promise.resolve();
    var sent = clone(f.dirty);
    var body = { message: "LIFE OS · " + path, content: b64enc(JSON.stringify(f.data, null, 1) + "\n") };
    if (f.sha) body.sha = f.sha;
    return api("PUT", path, body).then(function (r) {
      if ((r.status === 409 || r.status === 422) && !retried) return pull(path).then(function () { return push(path, true); });
      if (!r.ok) throw httpError(r);
      return r.json().then(function (j) {
        f.sha = j.content && j.content.sha;
        Object.keys(sent).forEach(function (k) { if (f.dirty[k] === sent[k]) delete f.dirty[k]; });
        persist();
      });
    });
  }
  function dirtyPaths() { return Object.keys(files).filter(function (p) { return Object.keys(files[p].dirty).length > 0; }); }
  function setSync(s, err) { SYNC.state = s; SYNC.error = err || null; paintSync(); }
  function paintSync() {
    var el = $("#sync"), t = $("#sync-t"), s = SYNC.state, n = dirtyPaths().length;
    if (!cfg.token) { el.setAttribute("data-s", "off"); t.textContent = "Non connecté"; return; }
    if (s === "bad") { el.setAttribute("data-s", "bad"); t.textContent = SYNC.error === "auth" ? "Clé refusée" : "Erreur"; return; }
    if (s === "running" || n) { el.setAttribute("data-s", "wait"); t.textContent = navigator.onLine === false ? "Hors ligne" : "Envoi…"; if (navigator.onLine === false) el.setAttribute("data-s", "off"); return; }
    el.setAttribute("data-s", "ok");
    t.textContent = SYNC.lastOk ? "Synchro " + pad(SYNC.lastOk.getHours()) + ":" + pad(SYNC.lastOk.getMinutes()) : "Synchro";
  }
  function scheduleSync(ms) { clearTimeout(SYNC.timer); SYNC.timer = setTimeout(runSync, ms == null ? 2500 : ms); paintSync(); }
  function neededPaths() {
    var t = today(), m = t.slice(0, 7), prev = addDays(t.slice(0, 8) + "01", -1).slice(0, 7);
    var list = ["plan.json", "jours/" + m + ".json", "jours/" + prev + ".json", "semaines/" + t.slice(0, 4) + ".json"];
    var extra = [UI.day, UI.week, UI.stats, addDays(UI.stats, -7), addDays(UI.week, 6)];
    extra.forEach(function (d) { if (d) { list.push("jours/" + d.slice(0, 7) + ".json"); list.push("semaines/" + mondayOf(d).slice(0, 4) + ".json"); } });
    return list.filter(function (p, i) { return list.indexOf(p) === i; });
  }
  function runSync(force) {
    if (!cfg.token || SYNC.running) return Promise.resolve();
    if (navigator.onLine === false) { paintSync(); return Promise.resolve(); }
    SYNC.running = true; setSync("running");
    var changed = false;
    var chain = Promise.resolve();
    dirtyPaths().forEach(function (p) { chain = chain.then(function () { return push(p); }); });
    neededPaths().forEach(function (p) {
      chain = chain.then(function () {
        var f = files[p];
        if (!force && f && Date.now() - f.pulledAt < 45000) return;
        return pull(p).then(function (c) { if (c) changed = true; });
      });
    });
    return chain.then(function () {
      SYNC.running = false; SYNC.lastOk = new Date(); setSync("ok");
      if (dirtyPaths().length) scheduleSync(1500);
      if (changed) refresh();
    }, function (e) {
      SYNC.running = false;
      if (e && (e.status === 401 || e.status === 403)) setSync("bad", "auth");
      else if (e && e.status === 404) setSync("bad", "repo");
      else { setSync("idle"); scheduleSync(15000); }
      if (UI.view === "reglages") renderReglages();
    });
  }

  /* ================= Modèle ================= */
  function plan() { var f = files["plan.json"]; return f && f.data && f.data.semaines ? f.data : null; }
  function startDate() { var p = plan(); return p ? p.debut : "2026-11-23"; }
  function jOf(d) { return diffDays(startDate(), d) + 1; }
  function weekOf(d) { var p = plan(), j = jOf(d); if (!p || j < 1 || j > 90) return null; return p.semaines[Math.min(p.semaines.length - 1, Math.floor((j - 1) / 7))]; }
  function weekOrFirst(d) { var p = plan(); if (!p) return null; return weekOf(d) || (jOf(d) < 1 ? p.semaines[0] : null); }
  function phaseOf(d) { var p = plan(), j = jOf(d); if (!p || j < 1 || j > 90) return null; return p.phases[j <= 30 ? 0 : (j <= 60 ? 1 : 2)]; }
  function dayPath(d) { return "jours/" + d.slice(0, 7) + ".json"; }
  function weekPath(m) { return "semaines/" + m.slice(0, 4) + ".json"; }
  function day(d) { var f = files[dayPath(d)]; return (f && f.data[d]) || {}; }
  function review(m) { var f = files[weekPath(m)]; return (f && f.data[m]) || {}; }
  var rev = 0;
  function setDay(d, k, v) {
    var f = file(dayPath(d)), cur = Object.assign({}, f.data[d] || {});
    if (v === null || v === "" || v === false) delete cur[k]; else cur[k] = v;
    cur.maj = new Date().toISOString();
    f.data[d] = cur; f.dirty[d] = ++rev; persist(); scheduleSync();
  }
  function setReview(m, k, v) {
    var f = file(weekPath(m)), cur = Object.assign({}, f.data[m] || {});
    if (v === null || v === "") delete cur[k]; else cur[k] = v;
    cur.maj = new Date().toISOString();
    f.data[m] = cur; f.dirty[m] = ++rev; persist(); scheduleSync();
  }
  function noted(x) { return Object.keys(x).some(function (k) { return k !== "maj"; }); }

  /* Ce qui est suivi chaque jour, et à partir de quelle semaine (1 à 2 nouveautés par semaine). */
  var HABITS = [
    { k: "tel_loin", n: "Téléphone loin du lit", s: "la nuit dernière", from: 1 },
    { k: "salle", n: "Séance de salle", s: "le matin, avant le travail", from: 2 },
    { k: "fastfood", n: "Fast-food", s: "à cocher si tu en as mangé", from: 2, neg: true },
    { k: "chambre", n: "Chambre en ordre", s: "10 min le soir", from: 6 },
    { k: "tel_matin", n: "Pas de téléphone au réveil", s: "les 30 premières minutes", from: 7 }
  ];
  var COUNTERS = [
    { k: "ecran", n: "Écran", u: "h", step: 0.5, from: 1, s: "Réglages › Temps d'écran" },
    { k: "depenses", n: "Dépenses", u: "€", input: true, from: 1, s: "tout compris" },
    { k: "pas", n: "Pas", u: "pas", input: true, from: 1, s: "app Santé, le soir" },
    { k: "business", n: "Business", u: "min", step: 15, from: 1, s: "temps réel" },
    { k: "contacts", n: "Prospects contactés", u: "", step: 1, from: 4, s: "message, appel ou visite" },
    { k: "etudes", n: "Études", u: "min", step: 15, from: 1, s: "révisions, EVPM" }
  ];
  function weekNo(d) { var w = weekOf(d); return w ? w.n : (jOf(d) < 1 ? 1 : 99); }
  function bedTarget(d) { var w = weekOrFirst(d); if (!w) return null; var t = night(tmin(w.c.coucher)); if (parseISO(d).getDay() === 3) t -= 60; return t; }
  function onTime(d, x) { var b = tmin(x.coucher), t = bedTarget(d); if (b == null || t == null) return null; return night(b) <= t + 15; }
  function dayScore(d) {
    var x = day(d), n = weekNo(d), got = 0, tot = 0;
    function add(ok) { tot++; if (ok) got++; }
    add(x.coucher && x.reveil);
    var ot = onTime(d, x); add(ot === true);
    HABITS.forEach(function (h) { if (h.from > n || h.k === "salle") return; if (h.neg) { if (noted(x)) add(x[h.k] !== true); else add(false); } else add(x[h.k] === true); });
    ["1", "2", "3"].forEach(function (i) { if (x["p" + i]) add(x["p" + i + "_ok"] === true); });
    return tot ? Math.round(got / tot * 100) : 0;
  }
  function streak(test) { var d = today(), n = 0; if (!test(d)) d = addDays(d, -1); while (test(d) && n < 400) { n++; d = addDays(d, -1); } return n; }

  /* ================= État de l'interface ================= */
  var UI = { view: "jour", day: today(), week: mondayOf(today()), stats: mondayOf(today()) };

  /* ================= Vue : Jour ================= */
  function ringSVG(p) {
    var r = 50, c = 2 * Math.PI * r;
    return '<svg viewBox="0 0 120 120" aria-hidden="true"><circle class="trk" cx="60" cy="60" r="' + r + '" fill="none" stroke-width="9"/>' +
      '<circle class="val" id="ring-val" cx="60" cy="60" r="' + r + '" fill="none" stroke-width="9" stroke-linecap="round" stroke-dasharray="' + c.toFixed(1) + '" stroke-dashoffset="' + (c * (1 - p / 100)).toFixed(1) + '"/></svg>';
  }
  function targetsChips(w, d) {
    if (!w) return "";
    var c = w.c, out = [];
    out.push('<span class="chip">Coucher <b>' + (d && parseISO(d).getDay() === 2 ? clock(night(tmin(c.coucher)) - 60) + " (mardi)" : c.coucher) + "</b></span>");
    out.push('<span class="chip">Réveil <b>' + (d && parseISO(d).getDay() === 3 ? "06:30" : c.reveil) + "</b></span>");
    if (c.salle) out.push('<span class="chip">Salle <b>' + c.salle + "×</b></span>");
    if (c.ecran) out.push('<span class="chip">Écran <b>≤ ' + fr(c.ecran, 1) + " h</b></span>");
    if (c.depenses) out.push('<span class="chip">Dépenses <b>≤ ' + c.depenses + " €</b></span>");
    if (c.contacts) out.push('<span class="chip">Contacts <b>' + c.contacts + "</b></span>");
    return '<div class="chips">' + out.join("") + "</div>";
  }
  function renderJour() {
    var d = UI.day, x = day(d), w = weekOrFirst(d), n = weekNo(d), j = jOf(d), t = today();
    var score = dayScore(d);
    var notedStreak = streak(function (dd) { return noted(day(dd)); });
    var nightStreak = streak(function (dd) { return onTime(dd, day(dd)) === true; });
    var head = j < 1 ? '<span class="daynum">J0<small>/90</small></span>' : (j > 90 ? '<span class="daynum">J' + j + "</span>" : '<span class="daynum">J' + j + "<small>/90</small></span>");
    var ph = phaseOf(d);
    var html =
      '<div class="hero fade"><div>' + head +
        '<div class="daymeta"><span class="daydate">' + esc(longDate(d)) + (d === t ? "" : (d < t ? " · passé" : " · à venir")) + "</span>" +
        '<div class="chips">' + (ph ? '<span class="chip gold">' + esc(ph.nom) + " · S" + w.n + "</span>" : (j < 1 ? '<span class="chip gold">Départ lundi</span>' : "")) +
        '<span class="chip">Série <b>' + notedStreak + " j</b></span><span class=\"chip\">À l'heure <b>" + nightStreak + " nuits</b></span></div></div></div>" +
        '<div class="ring">' + ringSVG(score) + '<div class="lab"><span class="pct" id="score">' + score + '<small>%</small></span><span class="cap">du jour</span></div></div></div>' +
      '<div class="daynav"><button type="button" class="btn sm" data-day="-1" aria-label="Jour précédent">←</button>' + (d === t ? "" : '<button type="button" class="btn sm" data-day="0">Aujourd\'hui</button>') + '<button type="button" class="btn sm" data-day="1" aria-label="Jour suivant">→</button></div>';
    if (w) {
      html += '<details class="card focus fold"' + (LS.get("focusClosed") === w.n ? "" : " open") + ' id="focus"><summary><div><p class="eyebrow">Semaine ' + w.n + (j < 1 ? " · commence lundi" : "") + '</p><h2 class="h2">' + tx(w.titre) + '</h2></div></summary><div class="fb">' +
        '<ol class="prio">' + w.priorites.map(function (p) { return "<li>" + tx(p) + "</li>"; }).join("") + "</ol>" + targetsChips(w, d) + "</div></details>";
    } else if (!plan()) {
      html += '<div class="note warn">Le plan n\'est pas encore chargé. Il apparaîtra dès que Claude l\'aura déposé dans ton dépôt de données.</div>';
    }
    var sm = sleepMin(x.coucher, x.reveil);
    html += '<section class="card"><div class="row"><div><p class="eyebrow">Matin</p><h2 class="h2">Ta nuit</h2></div></div>' +
      '<div class="night"><label class="tbox"><span class="k">Lumière éteinte</span><input type="time" data-d="coucher" value="' + esc(x.coucher || "") + '"' + (x.coucher ? "" : ' class="empty"') + '><span class="t">cible ' + (w ? (parseISO(d).getDay() === 3 ? clock(night(tmin(w.c.coucher)) - 60) : w.c.coucher) : "—") + "</span></label>" +
      '<label class="tbox"><span class="k">Réveil</span><input type="time" data-d="reveil" value="' + esc(x.reveil || "") + '"' + (x.reveil ? "" : ' class="empty"') + '><span class="t">cible ' + (w ? (parseISO(d).getDay() === 3 ? "06:30" : w.c.reveil) : "—") + "</span></label></div>" +
      '<div class="sleepbar" id="sleepbar">' + sleepBar(sm) + "</div>" +
      '<div class="fld"><span class="lb" id="en-l">Énergie au réveil</span><div class="seg" role="group" aria-labelledby="en-l">' + [1, 2, 3, 4, 5].map(function (v) { return '<button type="button" data-en="' + v + '" aria-pressed="' + (x.energie === v) + '">' + v + "</button>"; }).join("") + "</div></div></section>";
    html += '<section class="card"><div><p class="eyebrow">Matin · 3 priorités</p><h2 class="h2">Ce qui compte aujourd\'hui</h2></div><div class="prios">' +
      ["1", "2", "3"].map(function (i) {
        var ok = x["p" + i + "_ok"] === true;
        return '<div class="pr' + (ok ? " done" : "") + '"><button type="button" data-pok="' + i + '" aria-pressed="' + ok + '" aria-label="Priorité ' + i + ' faite"><span>' + CHECK + '</span></button><input type="text" data-d="p' + i + '" value="' + esc(x["p" + i] || "") + '" placeholder="Priorité ' + i + '" autocomplete="off" enterkeyhint="done"></div>';
      }).join("") + "</div></section>";
    var hs = HABITS.filter(function (h) { return h.from <= n; });
    html += '<section class="card"><div><p class="eyebrow">Habitudes · un tap</p><h2 class="h2">Tenu aujourd\'hui</h2></div><div class="habits">' +
      hs.map(function (h) {
        return '<button type="button" class="habit' + (h.neg ? " neg" : "") + '" data-h="' + h.k + '" aria-pressed="' + (x[h.k] === true) + '">' + (h.from === n && n > 1 ? '<span class="chip new badge">nouveau</span>' : "") +
          '<span class="dot">' + CHECK + '</span><span><span class="hn">' + tx(h.n) + '</span><br><span class="hs">' + tx(h.s) + "</span></span></button>";
      }).join("") + "</div></section>";
    var cs = COUNTERS.filter(function (c) { return c.from <= n; });
    html += '<section class="card"><div><p class="eyebrow">Soir · chiffres</p><h2 class="h2">Le relevé</h2></div><div class="counters">' +
      cs.map(function (c) {
        var v = x[c.k];
        if (c.input) return '<div class="ctr"><div><div class="cn">' + tx(c.n) + '</div><div class="ct">' + tx(c.s) + '</div></div><div class="step"><input class="v" type="text" inputmode="decimal" data-d="' + c.k + '" value="' + esc(v == null ? "" : String(v).replace(".", ",")) + '" placeholder="0" aria-label="' + esc(c.n) + '"><span class="mono muted">' + esc(c.u) + '</span></div></div>';
        return '<div class="ctr"><div><div class="cn">' + tx(c.n) + '</div><div class="ct">' + tx(c.s) + '</div></div><div class="step"><button type="button" data-c="' + c.k + '" data-dir="-1" aria-label="Moins">−</button><span class="v" id="cv-' + c.k + '">' + (v == null ? "0" : fr(v, 1)) + (c.u ? "<small>" + c.u + "</small>" : "") + '</span><button type="button" data-c="' + c.k + '" data-dir="1" aria-label="Plus">+</button></div></div>';
      }).join("") + "</div></section>";
    html += '<details class="card fold"' + (x.difficultes || x.amelioration ? " open" : "") + '><summary><div><p class="eyebrow">Soir · 1 min</p><h2 class="h2">Le bilan</h2></div></summary><div class="fb">' +
      '<div class="fld"><label for="f-diff">Ce qui a coincé</label><textarea class="in" id="f-diff" data-d="difficultes" rows="2">' + esc(x.difficultes || "") + "</textarea></div>" +
      '<div class="fld"><label for="f-amel">Une amélioration concrète pour demain</label><input class="in" id="f-amel" type="text" data-d="amelioration" value="' + esc(x.amelioration || "") + '" autocomplete="off"></div></div></details>';
    $("#v-jour").innerHTML = html;
    $$("#v-jour textarea").forEach(grow);
  }
  function sleepBar(sm) {
    var max = 600, pct = sm == null ? 0 : Math.min(100, sm / max * 100);
    var cls = sm == null ? "" : (sm >= 420 ? "ok" : "bad");
    return '<div class="track"><span class="band" style="left:' + (420 / max * 100) + "%;width:" + (120 / max * 100) + '%"></span><span class="fill ' + cls + '" style="width:' + pct + '%"></span></div>' +
      '<div class="txt"><span>' + (sm == null ? "Durée de sommeil : —" : "Dormi <b>" + dur(sm) + "</b>") + "</span><span>7–9 h recommandées</span></div>";
  }
  function refreshScore() {
    var s = dayScore(UI.day), el = $("#score"), ring = $("#ring-val");
    if (el) el.innerHTML = s + "<small>%</small>";
    if (ring) { var c = 2 * Math.PI * 50; ring.setAttribute("stroke-dashoffset", (c * (1 - s / 100)).toFixed(1)); }
  }

  /* ================= Agrégats ================= */
  function weekDays(m) { var o = []; for (var i = 0; i < 7; i++) o.push(addDays(m, i)); return o; }
  function agg(m) {
    var r = { noted: 0, sleep: [], beds: [], onTime: 0, bedN: 0, salle: 0, fast: 0, chambre: 0, tel: 0, ecran: [], pas: [], dep: 0, depN: 0, biz: 0, contacts: 0, etudes: 0, energie: [], pd: 0, pp: 0 };
    weekDays(m).forEach(function (d) {
      var x = day(d); if (!noted(x)) return;
      r.noted++;
      var s = sleepMin(x.coucher, x.reveil); if (s != null) r.sleep.push(s);
      var b = tmin(x.coucher); if (b != null) { r.beds.push(night(b)); r.bedN++; if (onTime(d, x)) r.onTime++; }
      if (x.salle === true) r.salle++;
      if (x.fastfood === true) r.fast++;
      if (x.chambre === true) r.chambre++;
      if (x.tel_loin === true) r.tel++;
      var e = num(x.ecran); if (e != null) r.ecran.push(e);
      var ps = num(x.pas); if (ps != null) r.pas.push(ps);
      var dp = num(x.depenses); if (dp != null) { r.dep += dp; r.depN++; }
      r.biz += num(x.business) || 0; r.contacts += num(x.contacts) || 0; r.etudes += num(x.etudes) || 0;
      if (x.energie) r.energie.push(x.energie);
      ["1", "2", "3"].forEach(function (i) { if (x["p" + i]) { r.pp++; if (x["p" + i + "_ok"] === true) r.pd++; } });
    });
    r.pasAvg = avg(r.pas); r.sleepAvg = avg(r.sleep); r.bedAvg = avg(r.beds); r.ecranAvg = avg(r.ecran); r.enAvg = avg(r.energie);
    r.w = weekOf(m) || weekOf(addDays(m, 6));
    r.rev = review(m);
    return r;
  }
  function weekTitle(m) { var w = weekOf(m) || weekOf(addDays(m, 6)); return (w ? "Semaine " + w.n + " · " : "") + shortDate(m) + " → " + shortDate(addDays(m, 6)); }

  /* ================= Vue : Semaine ================= */
  function renderSemaine() {
    var m = UI.week, a = agg(m), c = a.w ? a.w.c : null, r = a.rev;
    function line(k, v, tg) { return "<tr><td>" + tx(k) + '</td><td class="n">' + esc(v) + '</td><td class="n muted">' + tx(tg || "") + "</td></tr>"; }
    var html = '<div class="row"><div><p class="eyebrow">Bilan du dimanche · 15 min</p><h2 class="h2">' + esc(weekTitle(m)) + '</h2></div><div class="daynav"><button type="button" class="btn sm" data-week="-7" aria-label="Semaine précédente">←</button><button type="button" class="btn sm" data-week="7" aria-label="Semaine suivante">→</button></div></div>' +
      '<section class="card"><p class="eyebrow">Calculé depuis ton journal</p><div class="scrollx"><table class="tbl"><thead><tr><th>Indicateur</th><th>Réel</th><th>Cible</th></tr></thead><tbody>' +
      line("Jours notés", a.noted + "/7", "≥ 6/7") +
      line("Sommeil moyen", a.sleepAvg != null ? dur(a.sleepAvg) : "—", "≥ 7 h") +
      line("Nuits à l'heure", a.bedN ? a.onTime + "/" + a.bedN : "—", c ? "coucher " + c.coucher : "") +
      line("Salle", String(a.salle), c && c.salle ? c.salle + " séances" : "") +
      line("Écran moyen", a.ecranAvg != null ? fr(a.ecranAvg, 1) + " h/j" : "—", c && c.ecran ? "≤ " + fr(c.ecran, 1) + " h" : "mesure") +
      line("Dépenses", fr(a.dep, 0) + " €", c && c.depenses ? "≤ " + c.depenses + " €" : "mesure") +
      line("Fast-food", String(a.fast), "≤ 1") +
      line("Pas par jour", a.pasAvg != null ? fr(a.pasAvg, 0) : "—", "départ : 5 844") +
      line("Business", dur(a.biz), "≈ 13 h") +
      line("Prospects contactés", String(a.contacts), c && c.contacts ? String(c.contacts) : "") +
      line("Études", dur(a.etudes), c && c.etudes ? dur(c.etudes) : "") +
      line("Priorités faites", a.pp ? a.pd + "/" + a.pp : "—", "") +
      "</tbody></table></div></section>";
    function area(k, l, ph) { return '<div class="fld"><label for="w-' + k + '">' + tx(l) + '</label><textarea class="in" id="w-' + k + '" data-w="' + k + '" rows="2"' + (ph ? ' placeholder="' + esc(ph) + '"' : "") + ">" + esc(r[k] || "") + "</textarea></div>"; }
    function numf(k, l) { return '<div class="fld"><label for="w-' + k + '">' + tx(l) + '</label><input class="in mono" id="w-' + k + '" type="text" inputmode="decimal" data-w="' + k + '" value="' + esc(r[k] || "") + '" autocomplete="off"></div>'; }
    html += '<section class="card"><div><p class="eyebrow">Ton bilan</p><h2 class="h2">Ce que la semaine a donné</h2></div>' +
      area("atteints", "Objectifs atteints") + area("non_atteints", "Objectifs non atteints, et pourquoi") + area("progres", "Progrès par domaine", "Sommeil, salle, argent, business, études, chambre…") +
      '<div class="grid2">' + numf("revenus", "Revenus de la semaine (€)") + numf("epargne", "Mis de côté (€)") + numf("clients", "Clients signés au total") + numf("encaisse", "Encaissé business au total (€)") + "</div>" +
      area("organisation", "Évolution de ton organisation") + area("problemes", "Problèmes qui reviennent") +
      '<div class="fld"><span class="lb">Les 3 priorités de la semaine prochaine</span>' + ["s1", "s2", "s3"].map(function (k, i) { return '<input class="in" type="text" data-w="' + k + '" value="' + esc(r[k] || "") + '" placeholder="Priorité ' + (i + 1) + '" aria-label="Priorité ' + (i + 1) + ' de la semaine prochaine" autocomplete="off">'; }).join("") + "</div></section>";
    $("#v-semaine").innerHTML = html;
    $$("#v-semaine textarea").forEach(grow);
  }

  /* ================= Vue : Stats ================= */
  function delta(cur, prev, better, f) {
    if (cur == null || prev == null) return '<span class="delta">' + (cur == null ? "pas de donnée" : "1re mesure") + "</span>";
    var dd = cur - prev; if (Math.abs(dd) < 1e-9) return '<span class="delta">stable</span>';
    var good = better === "up" ? dd > 0 : dd < 0;
    return '<span class="delta ' + (good ? "up" : "down") + '">' + (dd > 0 ? "▲ +" : "▼ −") + esc(f(Math.abs(dd))) + "</span>";
  }
  function sleepChart(m) {
    var days = weekDays(addDays(m, -7)).concat(weekDays(m));
    var W = 420, H = 190, L = 30, R = 4, T = 10, B = 24, cw = (W - L - R) / 14, mx = 720;
    function y(v) { return T + (H - T - B) * (1 - v / mx); }
    var g = "";
    [0, 4, 8, 12].forEach(function (h) { g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(h * 60) + '" y2="' + y(h * 60) + '" stroke="#2C2C31"/><text class="ax" x="' + (L - 6) + '" y="' + (y(h * 60) + 4) + '" text-anchor="end">' + h + "h</text>"; });
    g += '<rect x="' + L + '" y="' + y(540) + '" width="' + (W - L - R) + '" height="' + (y(420) - y(540)) + '" fill="rgba(226,190,114,0.08)"/><text class="lb" x="' + (W - R - 4) + '" y="' + (y(540) + 13) + '" text-anchor="end">7–9 h</text>';
    days.forEach(function (d, i) {
      var x = day(d), s = sleepMin(x.coucher, x.reveil), bx = L + i * cw + 2, bw = cw - 4;
      if (s != null) {
        var top = y(Math.min(s, mx)), r = Math.min(4, bw / 2);
        g += '<path d="M' + bx + "," + y(0) + "V" + (top + r) + "Q" + bx + "," + top + " " + (bx + r) + "," + top + "H" + (bx + bw - r) + "Q" + (bx + bw) + "," + top + " " + (bx + bw) + "," + (top + r) + "V" + y(0) + 'Z" fill="' + (i < 7 ? "#4A4A50" : (s >= 420 ? "#E2BE72" : "#FF6B5E")) + '"><title>' + esc(longDate(d)) + " · " + dur(s) + "</title></path>";
      } else g += '<rect x="' + bx + '" y="' + (y(0) - 2) + '" width="' + bw + '" height="2" fill="#2C2C31"/>';
      g += '<text class="ax" x="' + (bx + bw / 2) + '" y="' + (H - 7) + '" text-anchor="middle">' + D1[i % 7] + "</text>";
    });
    g += '<line x1="' + (L + 7 * cw) + '" x2="' + (L + 7 * cw) + '" y1="' + T + '" y2="' + y(0) + '" stroke="#75746F" stroke-dasharray="3 3"/>';
    return '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Sommeil sur 14 jours">' + g + "</svg>";
  }
  function grid(m) {
    var ds = weekDays(m), rows = [
      ["Nuit à l'heure", function (x, d) { return onTime(d, x); }],
      ["Téléphone loin", function (x) { return noted(x) ? x.tel_loin === true : null; }],
      ["Salle", function (x) { return noted(x) ? x.salle === true : null; }],
      ["Sans fast-food", function (x) { return noted(x) ? x.fastfood !== true : null; }],
      ["Chambre", function (x) { return noted(x) ? x.chambre === true : null; }],
      ["Priorités /3", function (x) { if (!noted(x)) return null; var k = 0; ["1", "2", "3"].forEach(function (i) { if (x["p" + i + "_ok"] === true) k++; }); return k; }]
    ];
    var h = '<div class="hg"><span></span>' + ds.map(function (d, i) { return '<span class="h">' + D1[i] + "<br>" + parseISO(d).getDate() + "</span>"; }).join("");
    rows.forEach(function (r) {
      h += '<span class="r">' + tx(r[0]) + "</span>";
      ds.forEach(function (d) {
        var v = r[1](day(d), d), t = esc(longDate(d) + " · " + r[0]);
        if (v === null) h += '<span class="cell na" title="' + t + ' : non noté"></span>';
        else if (typeof v === "number") h += '<span class="cell' + (v === 3 ? " on" : "") + '" title="' + t + " : " + v + '/3">' + v + "</span>";
        else h += '<span class="cell ' + (v ? "on" : "no") + '" title="' + t + (v ? " : oui" : " : non") + '">' + (v ? "✓" : "") + "</span>";
      });
    });
    return h + "</div>";
  }
  function renderStats() {
    var m = UI.stats, a = agg(m), b = agg(addDays(m, -7)), c = a.w ? a.w.c : null, t = today();
    var total = 0, start = startDate();
    for (var i = 0; i < 90; i++) { var dd = addDays(start, i); if (dd > t) break; if (noted(day(dd))) total++; }
    var jt = Math.max(0, Math.min(90, jOf(t)));
    var html = '<div class="row"><div><p class="eyebrow">Statistiques</p><h2 class="h2">' + esc(weekTitle(m)) + '</h2></div><div class="daynav"><button type="button" class="btn sm" data-stats="-7" aria-label="Semaine précédente">←</button><button type="button" class="btn sm" data-stats="7" aria-label="Semaine suivante">→</button></div></div>';
    if (!a.noted && !b.noted) html += '<div class="note">Pas encore de données sur ces deux semaines. Chaque matin, note ta nuit : les stats se remplissent toutes seules.</div>';
    html += '<div class="tiles">' +
      '<div class="tile"><span class="k">Sommeil moyen</span><span class="v">' + (a.sleepAvg != null ? dur(a.sleepAvg).replace(" h ", "<small>h</small>") : "—") + '</span><span class="t">recommandé 7–9 h</span>' + delta(a.sleepAvg, b.sleepAvg, "up", dur) + "</div>" +
      '<div class="tile"><span class="k">Salle</span><span class="v">' + a.salle + (c && c.salle ? "<small>/" + c.salle + "</small>" : "") + '</span><span class="t">séances</span>' + delta(a.noted ? a.salle : null, b.noted ? b.salle : null, "up", String) + "</div>" +
      '<div class="tile"><span class="k">Écran / jour</span><span class="v">' + (a.ecranAvg != null ? fr(a.ecranAvg, 1) + "<small>h</small>" : "—") + '</span><span class="t">' + (c && c.ecran ? "cible ≤ " + fr(c.ecran, 1) + " h" : "départ : 6 h") + "</span>" + delta(a.ecranAvg, b.ecranAvg, "down", function (n) { return fr(n, 1) + " h"; }) + "</div>" +
      '<div class="tile"><span class="k">Dépenses</span><span class="v">' + (a.depN ? fr(a.dep, 0) + "<small>€</small>" : "—") + '</span><span class="t">' + (c && c.depenses ? "cible ≤ " + c.depenses + " €" : "semaine de mesure") + "</span>" + delta(a.depN ? a.dep : null, b.depN ? b.dep : null, "down", function (n) { return fr(n, 0) + " €"; }) + "</div>" +
      "</div>";
    html += '<section class="card"><div class="prog"><div class="row"><span class="eyebrow">Programme 90 jours</span><span class="mono small">' + total + " jours notés · J" + jt + '/90</span></div><div class="bar"><span style="width:' + (jt / 90 * 100) + '%"></span></div></div></section>';
    html += '<section class="card chart"><div><p class="eyebrow">14 nuits</p><h2 class="h2">Sommeil</h2></div>' + sleepChart(m) + '<p class="small muted">Gris : semaine précédente. Or : nuit de 7 h ou plus. Rouge : moins de 7 h.</p></section>';
    html += '<section class="card"><div><p class="eyebrow">7 jours</p><h2 class="h2">Régularité</h2></div><div class="scrollx">' + grid(m) + "</div></section>";
    function tr(dom, ind, cv, pv, tg) { return "<tr><td>" + tx(dom) + "</td><td>" + tx(ind) + '</td><td class="n">' + esc(cv) + '</td><td class="n muted">' + esc(pv) + '</td><td class="n muted">' + tx(tg) + "</td></tr>"; }
    html += '<section class="card"><div><p class="eyebrow">Semaine contre semaine</p><h2 class="h2">Tous les domaines</h2></div><div class="scrollx"><table class="tbl"><thead><tr><th>Domaine</th><th>Indicateur</th><th>Cette sem.</th><th>Préc.</th><th>Cible</th></tr></thead><tbody>' +
      tr("Organisation", "Priorités faites", a.pp ? a.pd + "/" + a.pp : "—", b.pp ? b.pd + "/" + b.pp : "—", "3/jour") +
      tr("Organisation", "Jours notés", a.noted + "/7", b.noted + "/7", "≥ 6/7") +
      tr("Hygiène", "Téléphone loin du lit", a.tel + "/7", b.tel + "/7", "7/7") +
      tr("Chambre", "Remise en ordre", a.chambre + "/7", b.chambre + "/7", "5/7 dès S6") +
      tr("Discipline", "Écran moyen", a.ecranAvg != null ? fr(a.ecranAvg, 1) + " h" : "—", b.ecranAvg != null ? fr(b.ecranAvg, 1) + " h" : "—", c && c.ecran ? "≤ " + fr(c.ecran, 1) + " h" : "mesure") +
      tr("Études", "Temps d'études", dur(a.etudes), dur(b.etudes), c && c.etudes ? dur(c.etudes) : "—") +
      tr("Business", "Temps business", dur(a.biz), dur(b.biz), "≈ 13 h") +
      tr("Business", "Prospects contactés", String(a.contacts), String(b.contacts), c ? String(c.contacts) : "—") +
      tr("Business", "Clients signés", a.rev.clients || "—", b.rev.clients || "—", "4 à J90") +
      tr("Finances", "Dépenses", fr(a.dep, 0) + " €", fr(b.dep, 0) + " €", c && c.depenses ? "≤ " + c.depenses + " €" : "mesure") +
      tr("Finances", "Mis de côté", a.rev.epargne ? a.rev.epargne + " €" : "—", b.rev.epargne ? b.rev.epargne + " €" : "—", "250 €/mois") +
      tr("Bien-être", "Sommeil moyen", a.sleepAvg != null ? dur(a.sleepAvg) : "—", b.sleepAvg != null ? dur(b.sleepAvg) : "—", "≥ 7 h") +
      tr("Bien-être", "Coucher moyen", a.bedAvg != null ? clock(a.bedAvg) : "—", b.bedAvg != null ? clock(b.bedAvg) : "—", c ? c.coucher : "—") +
      tr("Bien-être", "Pas par jour", a.pasAvg != null ? fr(a.pasAvg, 0) : "—", b.pasAvg != null ? fr(b.pasAvg, 0) : "—", "départ : 5 844") +
      tr("Bien-être", "Fast-food", String(a.fast), String(b.fast), "≤ 1") +
      tr("Bien-être", "Énergie au réveil", a.enAvg != null ? fr(a.enAvg, 1) + "/5" : "—", b.enAvg != null ? fr(b.enAvg, 1) + "/5" : "—", "en hausse") +
      tr("Vision", "Bilan du dimanche", noted(a.rev) ? "fait" : "non", noted(b.rev) ? "fait" : "non", "chaque semaine") +
      "</tbody></table></div></section>";
    $("#v-stats").innerHTML = html;
  }

  /* ================= Vue : Plan ================= */
  function renderPlan() {
    var p = plan();
    if (!p) { $("#v-plan").innerHTML = '<div class="note warn">Le plan n\'est pas encore chargé.</div>'; return; }
    var t = today(), cw = weekOf(t), cp = phaseOf(t);
    function wdates(w) { var s = addDays(p.debut, (w.n - 1) * 7), e = w.n === p.semaines.length ? addDays(p.debut, 89) : addDays(s, 6); return shortDate(s) + " → " + shortDate(e); }
    var html = '<div><p class="eyebrow">90 jours · ' + esc(shortDate(p.debut)) + " → " + esc(shortDate(addDays(p.debut, 89))) + '</p><h2 class="h2" style="font-size:34px">Une chose à la fois.</h2><p class="muted small" style="margin-top:6px">1 à 2 nouvelles habitudes par semaine. Le sommeil d\'abord : la salle, la concentration et le business en dépendent.</p></div>' +
      '<div class="phases">' + p.phases.map(function (ph) { return '<div class="phase' + (cp === ph ? " now" : "") + '"><span class="pn">' + esc(ph.jours) + " · " + esc(ph.dates) + '</span><span class="pt">' + tx(ph.nom) + '</span><span class="small muted">' + tx(ph.but) + "</span></div>"; }).join("") + "</div>" +
      '<section class="card"><div><p class="eyebrow">Objectifs à 90 jours</p><h2 class="h2">En chiffres</h2></div><dl class="kv">' + p.objectifs.map(function (o) { return "<div><dt>" + tx(o.nom) + "</dt><dd>" + tx(o.mesure) + "</dd></div>"; }).join("") + "</dl></section>" +
      '<h2 class="h2" style="margin-top:6px">Les ' + p.semaines.length + " semaines</h2>" +
      p.semaines.map(function (w) {
        var now = cw === w || (!cw && jOf(t) < 1 && w.n === 1);
        return '<details class="wk' + (now ? " now" : "") + '"' + (now ? " open" : "") + '><summary><span class="wn">S' + w.n + '</span><span class="wt">' + tx(w.titre) + (cw === w ? " · en cours" : "") + '</span><span class="wd">' + esc(wdates(w)) + "</span></summary>" +
          '<div class="wb"><ol class="prio">' + w.priorites.map(function (x) { return "<li>" + tx(x) + "</li>"; }).join("") + "</ol>" +
          '<dl class="kv"><div><dt>Actions</dt><dd><ul class="ls">' + w.actions.map(function (x) { return "<li>" + tx(x) + "</li>"; }).join("") + "</ul></dd></div>" +
          "<div><dt>Temps</dt><dd>" + tx(w.temps) + "</dd></div><div><dt>Ressources</dt><dd>" + tx(w.ressources) + "</dd></div><div><dt>Résultat attendu</dt><dd>" + tx(w.resultats) + "</dd></div><div><dt>Indicateurs</dt><dd>" + tx(w.indicateurs.join(" · ")) + "</dd></div></dl>" + targetsChips(w) + "</div></details>";
      }).join("") +
      '<section class="card"><div><p class="eyebrow">Décisions</p><h2 class="h2">Ce qui est tranché</h2></div><ul class="ls">' + p.decisions.map(function (x) { return "<li>" + tx(x) + "</li>"; }).join("") + "</ul></section>" +
      '<section class="card"><div><p class="eyebrow">À partir de la semaine 7</p><h2 class="h2">Semaine type</h2></div><div class="scrollx"><table class="tbl" style="min-width:560px"><thead><tr><th>Heure</th><th>Lun Mar Jeu Ven</th><th>Mercredi</th><th>Samedi</th><th>Dimanche</th></tr></thead><tbody>' +
      p.semaineType.map(function (r) { return "<tr>" + r.map(function (c, i) { return "<td" + (i === 0 ? ' class="n"' : "") + ">" + tx(c) + "</td>"; }).join("") + "</tr>"; }).join("") + "</tbody></table></div></section>";
    $("#v-plan").innerHTML = html;
  }

  /* ================= Vue : Audit ================= */
  function meter(n) { var s = ""; for (var i = 1; i <= 10; i++) s += "<i" + (i <= n ? ' class="on"' : "") + "></i>"; return '<div class="meter" aria-hidden="true">' + s + "</div>"; }
  function renderAudit() {
    var p = plan();
    if (!p) { $("#v-audit").innerHTML = '<div class="note warn">L\'audit n\'est pas encore chargé.</div>'; return; }
    function ul(t, a) { return a && a.length ? '<div><div class="sub">' + tx(t) + '</div><ul class="ls">' + a.map(function (x) { return "<li>" + tx(x) + "</li>"; }).join("") + "</ul></div>" : ""; }
    var html = '<div><p class="eyebrow">Audit · ' + esc(p.maj || "") + '</p><h2 class="h2" style="font-size:34px">Sans filtre.</h2><p class="muted small" style="margin-top:6px">Classé par impact. Chaque note est justifiée par tes réponses.</p></div>' +
      '<section class="dom"><div class="dom-h"><div><p class="eyebrow">Cohérence globale</p></div><span class="score">' + p.synthese.note + "<small>/10</small></span></div>" + meter(p.synthese.note) + "<p>" + tx(p.synthese.texte) + "</p></section>" +
      p.audit.map(function (d, i) {
        return '<section class="dom"><div class="dom-h"><div><p class="eyebrow">' + (i + 1) + ' · <span class="tag ' + d.urg + '">' + esc(d.urg) + '</span></p><h3 class="h3">' + tx(d.nom) + '</h3></div><span class="score">' + d.note + "<small>/10</small></span></div>" + meter(d.note) +
          "<p>" + tx(d.justif) + "</p>" +
          '<details class="fold"><summary><span class="small muted">Forces, faiblesses, habitudes</span></summary><div class="fb">' + ul("Forces", d.forces) + ul("Faiblesses", d.faiblesses) + ul("Habitudes contre-productives", d.contre) + ul("Possibilités", d.possib) + "</div></details>" +
          '<div><div class="sub">Recommandations</div><ol>' + d.recos.map(function (x) { return "<li>" + tx(x) + "</li>"; }).join("") + "</ol></div></section>";
      }).join("");
    $("#v-audit").innerHTML = html;
  }

  /* ================= Connexion et réglages ================= */
  function renderSetup() {
    var standalone = window.navigator.standalone === true || (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
    $("#v-reglages").innerHTML =
      '<div class="setup"><div class="big">LIFE<br><b>OS</b></div><p class="muted">Ton système personnel. Données privées, synchronisées sur ton compte GitHub.</p>' +
      (standalone ? "" : '<div class="note warn">Installe-la d\'abord : dans Safari, bouton Partager, puis « Sur l\'écran d\'accueil ». Ensuite, ouvre LIFE OS depuis l\'icône et connecte-toi. La connexion faite dans Safari ne passe pas dans l\'app installée.</div>') +
      '<section class="card"><h2 class="h2">Connexion</h2><ol class="steps">' +
      '<li><span>Ouvre <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">github.com › Fine-grained token</a>.</span></li>' +
      "<li><span>Nom : LIFE OS. Expiration : 1 an. Repository access : <b>Only select repositories</b> › <b>life-os-data</b>.</span></li>" +
      "<li><span>Permissions › Repository › <b>Contents : Read and write</b>. Rien d'autre.</span></li>" +
      "<li><span>Génère la clé, copie-la et colle-la ici. Ne l'envoie jamais dans une conversation.</span></li></ol>" +
      '<div class="fld"><label for="tok">Clé d\'accès GitHub</label><input class="in mono" id="tok" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="github_pat_…" value=""></div>' +
      '<div class="fld"><label for="repo">Dépôt de données</label><input class="in mono" id="repo" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" value="' + esc(cfg.repo) + '"></div>' +
      '<p class="small" id="setup-msg" role="status"></p><button type="button" class="btn gold" id="connect">Se connecter</button></section></div>';
  }
  function renderReglages() {
    if (!cfg.token) { renderSetup(); return; }
    var n = dirtyPaths().length;
    var err = SYNC.state === "bad" ? (SYNC.error === "auth" ? "La clé est refusée (expirée ou sans accès au dépôt). Crée une nouvelle clé et reconnecte-toi." : (SYNC.error === "repo" ? "Dépôt introuvable. Vérifie son nom." : "Erreur de synchronisation.")) : "";
    $("#v-reglages").innerHTML = '<div><p class="eyebrow">Réglages</p><h2 class="h2">Synchronisation</h2></div>' +
      (err ? '<div class="note bad">' + tx(err) + "</div>" : "") +
      '<section class="card"><div class="row"><span>Dépôt</span><span class="mono small">' + esc(cfg.repo) + '</span></div><div class="row"><span>En attente d\'envoi</span><span class="mono small">' + n + " fichier" + (n > 1 ? "s" : "") + '</span></div><div class="row"><span>Dernière synchro</span><span class="mono small">' + (SYNC.lastOk ? pad(SYNC.lastOk.getHours()) + ":" + pad(SYNC.lastOk.getMinutes()) : "—") + "</span></div>" +
      '<button type="button" class="btn gold" id="sync-now">Synchroniser maintenant</button></section>' +
      '<section class="card"><p class="small muted">Se déconnecter efface la clé de cet appareil. Les données déjà envoyées restent dans ton dépôt.</p><button type="button" class="btn ghost" id="logout">Se déconnecter</button></section>';
  }
  function connect() {
    var tok = ($("#tok").value || "").trim(), repo = ($("#repo").value || "").trim(), msg = $("#setup-msg");
    if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) { msg.textContent = "Nom de dépôt invalide (format : compte/depot)."; return; }
    if (tok.length < 20) { msg.textContent = "Colle la clé complète."; return; }
    msg.textContent = "Vérification…";
    fetch("https://api.github.com/repos/" + repo, { cache: "no-store", headers: { "Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json" } }).then(function (r) {
      if (r.status === 401) { msg.textContent = "Clé refusée. Vérifie que tu l'as copiée en entier."; return; }
      if (r.status === 404 || r.status === 403) { msg.textContent = "Cette clé n'a pas accès au dépôt " + repo + ". Vérifie l'étape 2."; return; }
      if (!r.ok) { msg.textContent = "GitHub ne répond pas (" + r.status + "). Réessaie."; return; }
      cfg = { token: tok, repo: repo }; LS.set("cfg", cfg);
      toast("Connecté");
      location.hash = "#jour";
      runSync(true).then(route);
    }, function () { msg.textContent = "Pas de connexion internet."; });
  }

  /* ================= Navigation ================= */
  var VIEWS = { jour: renderJour, semaine: renderSemaine, stats: renderStats, plan: renderPlan, audit: renderAudit, reglages: renderReglages };
  function crumb() {
    var t = today(), j = jOf(t), w = weekOf(t);
    $("#crumb").textContent = !plan() ? "" : (j < 1 ? "départ lundi" : (w ? "J" + j + " · S" + w.n : "après J90"));
  }
  function show(v) {
    if (!cfg.token) v = "reglages";
    if (!VIEWS[v]) v = "jour";
    UI.view = v;
    Object.keys(VIEWS).forEach(function (k) { $("#v-" + k).hidden = k !== v; });
    $$("#tabs a").forEach(function (a) { if (a.getAttribute("data-v") === v) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    $("#tabs").hidden = !cfg.token;
    VIEWS[v]();
    crumb(); paintSync();
  }
  function route() { var h = location.hash.replace("#", ""); show(h || "jour"); }
  function refresh() {
    var a = document.activeElement, inView = a && $("#v-" + UI.view) && $("#v-" + UI.view).contains(a) && /INPUT|TEXTAREA/.test(a.tagName);
    if (inView) return; /* ne jamais casser une saisie en cours */
    show(UI.view);
  }
  function scrollTop() { window.scrollTo({ top: 0, behavior: "auto" }); }
  window.addEventListener("hashchange", function () { route(); scrollTop(); });

  function toast(t) {
    var el = document.createElement("div"); el.className = "toast fade"; el.textContent = t; document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 1600);
  }
  function grow(el) { el.style.height = "auto"; el.style.height = (el.scrollHeight + 2) + "px"; }
  function haptic() { if (navigator.vibrate) { try { navigator.vibrate(8); } catch (e) { /* rien */ } } }

  /* ================= Événements ================= */
  document.addEventListener("input", function (e) {
    var el = e.target;
    if (el.tagName === "TEXTAREA") grow(el);
    var k = el.getAttribute && el.getAttribute("data-d");
    if (k) {
      var v = el.value;
      if (k === "depenses" || k === "pas") { var n = num(v); v = n == null ? null : n; }
      setDay(UI.day, k, v);
      if (k === "coucher" || k === "reveil") { el.classList.toggle("empty", !el.value); var x = day(UI.day); $("#sleepbar").innerHTML = sleepBar(sleepMin(x.coucher, x.reveil)); }
      refreshScore();
      return;
    }
    var w = el.getAttribute && el.getAttribute("data-w");
    if (w) setReview(UI.week, w, el.value);
  });
  document.addEventListener("change", function (e) {
    var el = e.target, k = el.getAttribute && el.getAttribute("data-d");
    if (k === "coucher" || k === "reveil") { setDay(UI.day, k, el.value); var x = day(UI.day); $("#sleepbar").innerHTML = sleepBar(sleepMin(x.coucher, x.reveil)); refreshScore(); }
  });
  document.addEventListener("click", function (e) {
    var t = e.target;
    var h = t.closest("[data-h]");
    if (h) { var k = h.getAttribute("data-h"), v = day(UI.day)[k] !== true; setDay(UI.day, k, v ? true : null); h.setAttribute("aria-pressed", String(v)); haptic(); refreshScore(); return; }
    var pk = t.closest("[data-pok]");
    if (pk) { var i = pk.getAttribute("data-pok"), pv = day(UI.day)["p" + i + "_ok"] !== true; setDay(UI.day, "p" + i + "_ok", pv ? true : null); pk.setAttribute("aria-pressed", String(pv)); pk.parentNode.classList.toggle("done", pv); haptic(); refreshScore(); return; }
    var en = t.closest("[data-en]");
    if (en) { var ev = +en.getAttribute("data-en"), cur = day(UI.day).energie === ev ? null : ev; setDay(UI.day, "energie", cur); $$("[data-en]").forEach(function (b) { b.setAttribute("aria-pressed", String(+b.getAttribute("data-en") === cur)); }); haptic(); return; }
    var c = t.closest("[data-c]");
    if (c) {
      var ck = c.getAttribute("data-c"), def = COUNTERS.filter(function (x) { return x.k === ck; })[0], val = num(day(UI.day)[ck]) || 0;
      val = Math.max(0, Math.round((val + def.step * +c.getAttribute("data-dir")) * 10) / 10);
      setDay(UI.day, ck, val === 0 ? null : val);
      $("#cv-" + ck).innerHTML = fr(val, 1) + (def.u ? "<small>" + def.u + "</small>" : "");
      haptic(); return;
    }
    var dd = t.closest("[data-day]");
    if (dd) { var n = +dd.getAttribute("data-day"); UI.day = n === 0 ? today() : addDays(UI.day, n); UI.navigated = n !== 0; renderJour(); scheduleSync(0); return; }
    var dw = t.closest("[data-week]");
    if (dw) { UI.week = addDays(UI.week, +dw.getAttribute("data-week")); renderSemaine(); scheduleSync(0); return; }
    var ds = t.closest("[data-stats]");
    if (ds) { UI.stats = addDays(UI.stats, +ds.getAttribute("data-stats")); renderStats(); scheduleSync(0); return; }
    if (t.closest("#sync")) { if (cfg.token) location.hash = "#reglages"; return; }
    if (t.closest("#connect")) { connect(); return; }
    if (t.closest("#sync-now")) { runSync(true).then(function () { if (UI.view === "reglages") renderReglages(); toast("Synchronisé"); }); return; }
    if (t.closest("#logout")) { cfg = { token: "", repo: cfg.repo }; LS.set("cfg", cfg); location.hash = "#reglages"; route(); return; }
  });
  document.addEventListener("toggle", function (e) {
    if (e.target.id === "focus") { var w = weekOrFirst(UI.day); if (w) LS.set("focusClosed", e.target.open ? null : w.n); }
  }, true);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") { LS.set("files", files); runSync(); return; }
    var t = today(); if (UI.day !== t && UI.view === "jour" && !UI.navigated) UI.day = t;
    runSync().then(refresh);
  });
  window.addEventListener("online", function () { runSync(true); });
  window.addEventListener("offline", paintSync);
  window.addEventListener("pagehide", function () { LS.set("files", files); });

  /* ================= Démarrage ================= */
  if (!location.hash && cfg.token) location.replace("#jour");
  route();
  if (cfg.token) runSync(true);
  if ("serviceWorker" in navigator && location.protocol === "https:") {
    navigator.serviceWorker.register("sw.js").catch(function () { /* hors ligne indisponible, l'app marche quand même */ });
  }
})();
