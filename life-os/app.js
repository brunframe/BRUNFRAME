/* LIFE OS · Maison — registre personnel.
   Code public, aucune donnée personnelle ici. Deux stockages possibles, même structure :
   - dans claude.ai : la base privée de l'artefact (documents systeme/plan, jours/AAAA-MM, semaines/AAAA) ;
   - sur GitHub Pages : un dépôt GitHub privé (plan.json, jours/AAAA-MM.json, semaines/AAAA.json),
     lu et écrit avec une clé gardée sur l'appareil. */
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
  var fJour = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" });
  var fCourt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
  function longDate(s) { return fJour.format(parseISO(s)); }
  function shortDate(s) { return fCourt.format(parseISO(s)); }
  var D1 = ["L", "M", "M", "J", "V", "S", "D"];
  var ROM = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"];
  function tmin(s) { if (!s || !/^\d{1,2}:\d{2}/.test(s)) return null; var p = s.split(":"); return (+p[0]) * 60 + (+p[1]); }
  function night(m) { return m < 720 ? m + 1440 : m; }
  function sleepMin(c, r) { var a = tmin(c), b = tmin(r); if (a == null || b == null) return null; var d = (b - a + 1440) % 1440; return d < 60 ? null : d; }
  function dur(m) { m = Math.round(m); return Math.floor(m / 60) + " h " + pad(m % 60); }
  function clock(m) { m = Math.round(m) % 1440; return pad(Math.floor(m / 60)) + ":" + pad(m % 60); }
  function num(v) { if (v == null || v === "") return null; var n = parseFloat(String(v).replace(",", ".").replace(/\s/g, "")); return isNaN(n) ? null : n; }
  function fr(n, d) { if (n == null) return "—"; var k = Math.pow(10, d || 0); return String(Math.round(n * k) / k).replace(".", ","); }
  function avg(a) { return a.length ? a.reduce(function (x, y) { return x + y; }, 0) / a.length : null; }
  var COCHE = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3.2 3L13 4.8"/></svg>';

  /* ================= Stockage local ================= */
  var LS = {
    get: function (k) { try { var v = localStorage.getItem("los:" + k); return v ? JSON.parse(v) : null; } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem("los:" + k, JSON.stringify(v)); return true; } catch (e) { return false; } }
  };
  var cfg = LS.get("cfg") || { token: "", repo: "brunframe/life-os-data" };
  var FKEY = "files";
  var files = LS.get(FKEY) || {};
  var saveTimer = null;
  function persist() { clearTimeout(saveTimer); saveTimer = setTimeout(function () { LS.set(FKEY, files); }, 150); }
  function file(path) { if (!files[path]) files[path] = { sha: null, data: {}, dirty: {}, pulledAt: 0 }; return files[path]; }

  /* ================= Stockages distants ================= */
  var B = { kind: null, db: null };
  function b64enc(str) { var bytes = new TextEncoder().encode(str), bin = ""; for (var i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000)); return btoa(bin); }
  function b64dec(b64) { var bin = atob(String(b64).replace(/\s/g, "")), bytes = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i); return new TextDecoder().decode(bytes); }
  function httpErr(status) { var e = new Error("http " + status); e.status = status; return e; }
  function dbId(path) { return path === "plan.json" ? "systeme/plan" : path.replace(/\.json$/, ""); }
  function gh(method, path, body) {
    return fetch("https://api.github.com/repos/" + cfg.repo + "/contents/" + path, {
      method: method, cache: "no-store",
      headers: Object.assign({ "Authorization": "Bearer " + cfg.token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" }, body ? { "Content-Type": "application/json" } : {}),
      body: body ? JSON.stringify(body) : undefined
    });
  }
  function remoteGet(path) {
    if (B.kind === "db") return B.db.doc(dbId(path)).get().then(function (s) { return s.exists ? { data: clone(s.data()), sha: "db" } : null; });
    return gh("GET", path).then(function (r) {
      if (r.status === 404) return null;
      if (!r.ok) throw httpErr(r.status);
      return r.json().then(function (j) { var d = {}; try { d = JSON.parse(b64dec(j.content)); } catch (e) { d = {}; } return { data: d, sha: j.sha }; });
    });
  }
  function remotePut(path, data, sha) {
    if (B.kind === "db") return B.db.doc(dbId(path)).set(clone(data)).then(function () { return { sha: "db" }; }, function (e) { throw httpErr(e && e.code === "invalid_argument" ? 403 : 503); });
    var body = { message: "LIFE OS · " + path, content: b64enc(JSON.stringify(data, null, 1) + "\n") };
    if (sha) body.sha = sha;
    return gh("PUT", path, body).then(function (r) {
      if (r.status === 409 || r.status === 422) throw httpErr(409);
      if (!r.ok) throw httpErr(r.status);
      return r.json().then(function (j) { return { sha: j.content && j.content.sha }; });
    });
  }

  /* ================= Synchronisation ================= */
  var SYNC = { state: "idle", error: null, timer: null, running: false, lastOk: null };
  function ready() { return B.kind === "db" || (B.kind === "gh" && !!cfg.token); }
  function pull(path) {
    return remoteGet(path).then(function (res) {
      var f = file(path);
      f.pulledAt = Date.now();
      if (!res) return false;
      var merged = res.data || {};
      Object.keys(f.dirty).forEach(function (k) { if (f.data[k] !== undefined) merged[k] = f.data[k]; });
      var changed = JSON.stringify(merged) !== JSON.stringify(f.data);
      f.data = merged; f.sha = res.sha; persist();
      return changed;
    });
  }
  function push(path, retried) {
    var f = file(path);
    if (!Object.keys(f.dirty).length) return Promise.resolve();
    var sent = clone(f.dirty);
    return remotePut(path, f.data, f.sha).then(function (res) {
      f.sha = res.sha;
      Object.keys(sent).forEach(function (k) { if (f.dirty[k] === sent[k]) delete f.dirty[k]; });
      persist();
    }, function (e) {
      if (e.status === 409 && !retried) return pull(path).then(function () { return push(path, true); });
      throw e;
    });
  }
  function dirtyPaths() { return Object.keys(files).filter(function (p) { return Object.keys(files[p].dirty).length > 0; }); }
  function paintSync() {
    var el = $("#etat"), t = $("#etat-t"), n = dirtyPaths().length;
    if (!B.kind) { el.setAttribute("data-s", "wait"); t.textContent = "Ouverture"; return; }
    if (!ready()) { el.setAttribute("data-s", "off"); t.textContent = "Non connecté"; return; }
    if (SYNC.state === "bad") { el.setAttribute("data-s", "bad"); t.textContent = SYNC.error === "auth" ? "Accès refusé" : "Erreur"; return; }
    if (navigator.onLine === false) { el.setAttribute("data-s", "off"); t.textContent = "Hors ligne"; return; }
    if (SYNC.running || n) { el.setAttribute("data-s", "wait"); t.textContent = "Enregistrement"; return; }
    el.setAttribute("data-s", "ok");
    t.textContent = SYNC.lastOk ? "Enregistré " + pad(SYNC.lastOk.getHours()) + ":" + pad(SYNC.lastOk.getMinutes()) : "Synchronisé";
  }
  function scheduleSync(ms) { clearTimeout(SYNC.timer); SYNC.timer = setTimeout(runSync, ms == null ? 2000 : ms); paintSync(); }
  function neededPaths() {
    var t = today(), list = ["plan.json"];
    [t, addDays(t.slice(0, 8) + "01", -1), UI.day, UI.week, addDays(UI.week, 6), UI.reg, addDays(UI.reg, -7), addDays(UI.reg, 6)].forEach(function (d) {
      list.push("jours/" + d.slice(0, 7) + ".json"); list.push("semaines/" + mondayOf(d).slice(0, 4) + ".json");
    });
    return list.filter(function (p, i) { return list.indexOf(p) === i; });
  }
  function runSync(force) {
    if (!ready() || SYNC.running) return Promise.resolve();
    if (navigator.onLine === false) { paintSync(); return Promise.resolve(); }
    SYNC.running = true; paintSync();
    var changed = false, chain = Promise.resolve();
    dirtyPaths().forEach(function (p) { chain = chain.then(function () { return push(p); }); });
    neededPaths().forEach(function (p) {
      chain = chain.then(function () {
        var f = files[p];
        if (!force && f && Date.now() - f.pulledAt < 45000) return;
        return pull(p).then(function (c) { if (c) changed = true; });
      });
    });
    return chain.then(function () {
      SYNC.running = false; SYNC.state = "ok"; SYNC.error = null; SYNC.lastOk = new Date(); paintSync();
      if (dirtyPaths().length) scheduleSync(1500);
      if (changed) refresh();
    }, function (e) {
      SYNC.running = false;
      if (e && (e.status === 401 || e.status === 403)) { SYNC.state = "bad"; SYNC.error = "auth"; }
      else if (e && e.status === 404) { SYNC.state = "bad"; SYNC.error = "repo"; }
      else { SYNC.state = "idle"; scheduleSync(15000); }
      paintSync();
      if (UI.view === "acces") renderAcces();
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

  /* Ce qui est suivi, et à partir de quelle semaine du plan : une à deux nouveautés par semaine. */
  var TENUE = [
    { k: "tel_loin", n: "Téléphone loin du lit", s: "La nuit dernière", from: 1 },
    { k: "salle", n: "Salle, avant le travail", s: "Lundi · jeudi · samedi", from: 2 },
    { k: "fastfood", n: "Fast-food", s: "À marquer seulement si tu en as pris", from: 2, neg: true },
    { k: "chambre", n: "Chambre remise en ordre", s: "Dix minutes, le soir", from: 6 },
    { k: "tel_matin", n: "Premières trente minutes sans téléphone", s: "Au réveil", from: 7 }
  ];
  var RELEVE = [
    { k: "ecran", n: "Temps d'écran", s: "Réglages › Temps d'écran", u: "h", step: 0.5, from: 1 },
    { k: "pas", n: "Pas", s: "App Santé, le soir", u: "pas", input: true, from: 1 },
    { k: "depenses", n: "Dépenses", s: "Tout compris", u: "€", input: true, from: 1 },
    { k: "business", n: "Business", s: "Temps réel", u: "min", step: 15, from: 1 },
    { k: "contacts", n: "Prospects contactés", s: "Message, appel, visite", u: "", step: 1, from: 4 },
    { k: "etudes", n: "Études", s: "Révisions, EVPM", u: "min", step: 15, from: 1 }
  ];
  function weekNo(d) { var w = weekOf(d); return w ? w.n : (jOf(d) < 1 ? 1 : 99); }
  function bedTarget(d) { var w = weekOrFirst(d); if (!w) return null; var t = night(tmin(w.c.coucher)); if (parseISO(d).getDay() === 3) t -= 60; return t; }
  function wakeTarget(d, w) { return parseISO(d).getDay() === 3 ? "06:30" : w.c.reveil; }
  function onTime(d, x) { var b = tmin(x.coucher), t = bedTarget(d); if (b == null || t == null) return null; return night(b) <= t + 15; }
  function tenueDuJour(d) {
    var x = day(d), n = weekNo(d), ok = 0, tot = 0;
    function add(v) { tot++; if (v) ok++; }
    add(onTime(d, x) === true);
    TENUE.forEach(function (h) { if (h.from > n || h.k === "salle") return; add(h.neg ? (noted(x) && x[h.k] !== true) : x[h.k] === true); });
    ["1", "2", "3"].forEach(function (i) { if (x["p" + i]) add(x["p" + i + "_ok"] === true); });
    return { ok: ok, tot: tot };
  }

  /* ================= État de l'interface ================= */
  var UI = { view: "jour", day: today(), week: mondayOf(today()), reg: mondayOf(today()), navigated: false };

  /* ================= Jour ================= */
  function renderJour() {
    var d = UI.day, x = day(d), w = weekOrFirst(d), n = weekNo(d), j = jOf(d), t = today(), ph = phaseOf(d);
    var html = '<header class="mast apparait"><span class="date">' + esc(longDate(d)) + (d === t ? "" : (d < t ? " · passé" : " · à venir")) + "</span>" +
      '<div class="jour"><b class="num">' + (j < 1 ? "0" : j) + "</b><span>" + (j >= 1 && j <= 90 ? "sur quatre-vingt-dix" : (j < 1 ? "départ lundi 23 novembre" : "au-delà du plan")) + "</span></div>" +
      (w ? '<p class="phase">' + (ph ? "<b>" + esc(ph.nom) + "</b>" : "") + "semaine " + ROM[w.n] + " · " + tx(w.titre) + "</p>" : "") +
      '<div class="pas-jour"><button type="button" class="lien" data-day="-1">← Veille</button>' + (d === t ? "" : '<button type="button" class="lien" data-day="0">Aujourd\'hui</button>') + '<button type="button" class="lien" data-day="1">Lendemain →</button></div></header>';
    if (!plan()) html += '<p class="avis">Le plan n\'est pas encore déposé. Il apparaîtra ici dès qu\'il le sera.</p>';
    if (w) {
      html += '<section class="sec"><div class="sec-h"><span class="cap or">L\'intention de la semaine</span></div><ol class="intent">' + w.priorites.map(function (p) { return "<li>" + tx(p) + "</li>"; }).join("") + "</ol>" +
        '<div class="cibles">' + cible("Coucher", parseISO(d).getDay() === 2 ? clock(night(tmin(w.c.coucher)) - 60) : w.c.coucher) + cible("Réveil", wakeTarget(d, w)) + (w.c.salle ? cible("Salle", w.c.salle + " ×") : "") + (w.c.ecran ? cible("Écran", "≤ " + fr(w.c.ecran, 1) + " h") : "") + (w.c.depenses ? cible("Dépenses", "≤ " + w.c.depenses + " €") : "") + "</div></section>";
    }
    var sm = sleepMin(x.coucher, x.reveil);
    html += '<section class="sec"><div class="sec-h"><span class="cap">Le matin</span><h2 class="titre-s">La nuit</h2></div>' +
      '<div class="nuit"><label class="heure"><span class="cap">Lumière éteinte</span><input type="time" data-d="coucher" value="' + esc(x.coucher || "") + '"' + (x.coucher ? "" : ' class="vide"') + '><span class="c">cible ' + (w ? clock(bedTarget(d)) : "—") + "</span></label>" +
      '<label class="heure"><span class="cap">Réveil</span><input type="time" data-d="reveil" value="' + esc(x.reveil || "") + '"' + (x.reveil ? "" : ' class="vide"') + '><span class="c">cible ' + (w ? wakeTarget(d, w) : "—") + "</span></label></div>" +
      '<div class="duree" id="duree">' + dureeHTML(sm) + "</div>" +
      '<div class="champ"><span class="lb" id="en-l">Énergie au réveil</span><div class="energie" role="group" aria-labelledby="en-l">' + [1, 2, 3, 4, 5].map(function (v) { return '<button type="button" data-en="' + v + '" aria-pressed="' + (x.energie === v) + '" aria-label="' + v + ' sur 5">' + v + "</button>"; }).join("") + "</div></div></section>";
    html += '<section class="sec"><div class="sec-h"><span class="cap">Le matin</span><h2 class="titre-s">Trois priorités</h2></div><div>' +
      ["1", "2", "3"].map(function (i) {
        var ok = x["p" + i + "_ok"] === true;
        return '<div class="prio' + (ok ? " faite" : "") + '"><span class="r">' + ROM[+i] + '</span><input type="text" data-d="p' + i + '" value="' + esc(x["p" + i] || "") + '" placeholder="À écrire" autocomplete="off" enterkeyhint="done" aria-label="Priorité ' + i + '"><button type="button" data-pok="' + i + '" aria-pressed="' + ok + '" aria-label="Priorité ' + i + ' faite"><span>' + COCHE + "</span></button></div>";
      }).join("") + "</div></section>";
    var hs = TENUE.filter(function (h) { return h.from <= n; });
    html += '<section class="sec"><div class="sec-h"><span class="cap">La tenue</span><h2 class="titre-s">Ce qui a été tenu</h2></div><div class="lignes">' +
      hs.map(function (h) {
        return '<button type="button" class="ligne' + (h.neg ? " neg" : "") + '" data-h="' + h.k + '" aria-pressed="' + (x[h.k] === true) + '"><span><span class="n">' + tx(h.n) + '</span><span class="s">' + tx(h.from === n && n > 1 ? "Depuis cette semaine · " + h.s : h.s) + '</span></span><span class="o">' + COCHE + "</span></button>";
      }).join("") + "</div></section>";
    var rs = RELEVE.filter(function (c) { return c.from <= n; });
    html += '<section class="sec"><div class="sec-h"><span class="cap">Le soir</span><h2 class="titre-s">Le relevé</h2></div><div class="releve">' +
      rs.map(function (c) {
        var v = x[c.k];
        var lab = '<div><span class="n">' + tx(c.n) + '</span><span class="s">' + tx(c.s) + "</span></div>";
        if (c.input) return '<div class="cpt">' + lab + '<div class="pas"><input class="v num" type="text" inputmode="decimal" data-d="' + c.k + '" value="' + esc(v == null ? "" : String(v).replace(".", ",")) + '" placeholder="—" aria-label="' + esc(c.n) + '"><span class="u">' + esc(c.u) + "</span></div></div>";
        return '<div class="cpt">' + lab + '<div class="pas"><button type="button" data-c="' + c.k + '" data-dir="-1" aria-label="Moins">−</button><span class="v num" id="cv-' + c.k + '">' + (v == null ? "0" : fr(v, 1)) + (c.u ? "<small>" + c.u + "</small>" : "") + '</span><button type="button" data-c="' + c.k + '" data-dir="1" aria-label="Plus">+</button></div></div>';
      }).join("") + "</div></section>";
    html += '<section class="sec"><div class="sec-h"><span class="cap">Le soir</span><h2 class="titre-s">Le bilan</h2></div>' +
      '<div class="champ"><label for="f-diff">Ce qui a coincé</label><textarea class="saisie" id="f-diff" data-d="difficultes" rows="2" placeholder="En une phrase">' + esc(x.difficultes || "") + "</textarea></div>" +
      '<div class="champ"><label for="f-amel">Ce que tu changes demain</label><input class="saisie" id="f-amel" type="text" data-d="amelioration" value="' + esc(x.amelioration || "") + '" placeholder="Un geste concret" autocomplete="off"></div>' +
      '<p class="bilan-jour" id="tenue">' + tenueHTML(d) + "</p></section>";
    $("#v-jour").innerHTML = html;
    $$("#v-jour textarea").forEach(grow);
  }
  function cible(k, v) { return '<div class="cible"><span class="cap">' + esc(k) + '</span><span class="v">' + esc(v) + "</span></div>"; }
  function dureeHTML(sm) {
    var lo = 240, hi = 600, pos = function (m) { return Math.max(0, Math.min(100, (m - lo) / (hi - lo) * 100)); };
    var cls = sm == null ? "" : (sm >= 420 ? "ok" : "ko");
    return '<div class="l"><span class="cap">Sommeil</span><span class="v num">' + (sm == null ? "—" : dur(sm)) + (sm == null ? "" : "<small>" + (sm >= 420 ? "dans la norme" : "sous les 7 h") + "</small>") + "</span></div>" +
      '<div class="regle" aria-hidden="true"><span class="zone" style="left:' + pos(420) + "%;width:" + (pos(540) - pos(420)) + '%"></span>' + (sm == null ? "" : '<span class="pt ' + cls + '" style="left:' + pos(sm) + '%"></span>') +
      '<span class="gr" style="left:0">4 H</span><span class="gr" style="left:' + pos(420) + '%">7 H</span><span class="gr" style="left:' + pos(540) + '%">9 H</span><span class="gr" style="left:100%">10 H</span></div>';
  }
  function tenueHTML(d) { var s = tenueDuJour(d); return "Tenu aujourd'hui : <b>" + s.ok + "</b> sur " + s.tot + "."; }
  function refreshTenue() { var el = $("#tenue"); if (el) el.innerHTML = tenueHTML(UI.day); }

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
    r.sleepAvg = avg(r.sleep); r.bedAvg = avg(r.beds); r.ecranAvg = avg(r.ecran); r.pasAvg = avg(r.pas); r.enAvg = avg(r.energie);
    r.w = weekOf(m) || weekOf(addDays(m, 6));
    r.rev = review(m);
    return r;
  }
  function semTitre(m) { var w = weekOf(m) || weekOf(addDays(m, 6)); return (w ? "Semaine " + ROM[w.n] : "Semaine") ; }
  function semDates(m) { return shortDate(m) + " — " + shortDate(addDays(m, 6)); }
  function navSem(attr) { return '<div class="pas-jour"><button type="button" class="lien" data-' + attr + '="-7">← Précédente</button><button type="button" class="lien" data-' + attr + '="7">Suivante →</button></div>'; }

  /* ================= Semaine ================= */
  function renderSemaine() {
    var m = UI.week, a = agg(m), c = a.w ? a.w.c : null, r = a.rev;
    function row(k, v, tg) { return '<tr><td class="k">' + tx(k) + '</td><td class="d">' + esc(v) + "</td><td>" + tx(tg || "") + "</td></tr>"; }
    var html = '<header class="mast apparait"><span class="date">' + esc(semDates(m)) + '</span><h1 class="titre">' + esc(semTitre(m)) + ', <em>le bilan.</em></h1><p class="lead">Le dimanche, quinze minutes. Les chiffres sont tirés de ton journal ; les jours non notés ne comptent pas.</p>' + navSem("week") + "</header>" +
      '<section class="sec"><span class="cap or">Les chiffres</span><div class="defile"><table class="livre"><thead><tr><th>Indicateur</th><th>Réel</th><th>Cible</th></tr></thead><tbody>' +
      row("Jours notés", a.noted + " / 7", "6 / 7") +
      row("Sommeil moyen", a.sleepAvg != null ? dur(a.sleepAvg) : "—", "7 h et plus") +
      row("Nuits à l'heure", a.bedN ? a.onTime + " / " + a.bedN : "—", c ? "coucher " + c.coucher : "") +
      row("Salle", String(a.salle), c && c.salle ? c.salle + " séances" : "") +
      row("Écran par jour", a.ecranAvg != null ? fr(a.ecranAvg, 1) + " h" : "—", c && c.ecran ? "≤ " + fr(c.ecran, 1) + " h" : "mesure") +
      row("Pas par jour", a.pasAvg != null ? fr(a.pasAvg, 0) : "—", "départ 5 844") +
      row("Dépenses", fr(a.dep, 0) + " €", c && c.depenses ? "≤ " + c.depenses + " €" : "mesure") +
      row("Fast-food", String(a.fast), "1 au plus") +
      row("Business", dur(a.biz), "environ 13 h") +
      row("Prospects contactés", String(a.contacts), c && c.contacts ? String(c.contacts) : "") +
      row("Études", dur(a.etudes), c && c.etudes ? dur(c.etudes) : "") +
      row("Priorités tenues", a.pp ? a.pd + " / " + a.pp : "—", "") +
      "</tbody></table></div></section>";
    function area(k, l, ph) { return '<div class="champ"><label for="w-' + k + '">' + tx(l) + '</label><textarea class="saisie" id="w-' + k + '" data-w="' + k + '" rows="2" placeholder="' + esc(ph || "") + '">' + esc(r[k] || "") + "</textarea></div>"; }
    function nb(k, l) { return '<div class="champ"><label for="w-' + k + '">' + tx(l) + '</label><input class="saisie num" id="w-' + k + '" type="text" inputmode="decimal" data-w="' + k + '" value="' + esc(r[k] || "") + '" placeholder="—" autocomplete="off"></div>'; }
    html += '<section class="sec"><span class="cap or">Le bilan</span>' + area("atteints", "Ce qui est atteint") + area("non_atteints", "Ce qui ne l'est pas, et pourquoi") + area("progres", "Progrès par domaine", "Sommeil, salle, argent, business, études") +
      '<div class="deux">' + nb("revenus", "Revenus (€)") + nb("epargne", "Mis de côté (€)") + nb("clients", "Clients signés") + nb("encaisse", "Encaissé business (€)") + "</div>" +
      area("organisation", "Ton organisation") + area("problemes", "Ce qui revient") +
      '<div class="champ"><span class="lb">Les trois priorités de la semaine suivante</span>' + ["s1", "s2", "s3"].map(function (k, i) { return '<input class="saisie" type="text" data-w="' + k + '" value="' + esc(r[k] || "") + '" placeholder="' + ROM[i + 1] + '" aria-label="Priorité ' + (i + 1) + '" autocomplete="off">'; }).join("") + "</div></section>";
    $("#v-semaine").innerHTML = html;
    $$("#v-semaine textarea").forEach(grow);
  }

  /* ================= Registre ================= */
  function ecart(cur, prev, better, f) {
    if (cur == null) return '<span class="ecart">Pas encore de mesure</span>';
    if (prev == null) return '<span class="ecart">Première mesure</span>';
    var dd = cur - prev; if (Math.abs(dd) < 1e-9) return '<span class="ecart">Stable</span>';
    var good = better === "up" ? dd > 0 : dd < 0;
    return '<span class="ecart ' + (good ? "mieux" : "moins") + '">' + (dd > 0 ? "+ " : "− ") + esc(f(Math.abs(dd))) + " sur la semaine</span>";
  }
  function courbe(m) {
    var days = weekDays(addDays(m, -7)).concat(weekDays(m));
    var W = 420, H = 170, L = 26, R = 2, T = 8, Bm = 22, cw = (W - L - R) / 14, mx = 660;
    function y(v) { return T + (H - T - Bm) * (1 - v / mx); }
    var g = "";
    [0, 7, 9].forEach(function (h) { g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(h * 60) + '" y2="' + y(h * 60) + '" stroke="rgba(236,231,221,' + (h ? 0.16 : 0.22) + ')" stroke-dasharray="' + (h ? "2 4" : "0") + '"/><text class="ax" x="' + (L - 6) + '" y="' + (y(h * 60) + 3) + '" text-anchor="end">' + h + "H</text>"; });
    days.forEach(function (d, i) {
      var x = day(d), s = sleepMin(x.coucher, x.reveil), cx = L + i * cw + cw / 2;
      if (s != null) {
        var col = i < 7 ? "rgba(236,231,221,0.30)" : (s >= 420 ? "#C8A96B" : "#C0675A");
        g += '<line x1="' + cx + '" x2="' + cx + '" y1="' + y(0) + '" y2="' + y(Math.min(s, mx)) + '" stroke="' + col + '" stroke-width="2"/><circle cx="' + cx + '" cy="' + y(Math.min(s, mx)) + '" r="4" fill="' + col + '"><title>' + esc(longDate(d)) + " · " + dur(s) + "</title></circle>";
      }
      g += '<text class="ax" x="' + cx + '" y="' + (H - 6) + '" text-anchor="middle">' + D1[i % 7] + "</text>";
    });
    g += '<line x1="' + (L + 7 * cw) + '" x2="' + (L + 7 * cw) + '" y1="' + T + '" y2="' + y(0) + '" stroke="rgba(236,231,221,0.14)"/>';
    return '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Sommeil sur quatorze nuits">' + g + "</svg>";
  }
  function grille(m) {
    var ds = weekDays(m), rows = [
      ["Nuit à l'heure", function (x, d) { return onTime(d, x); }],
      ["Téléphone loin", function (x) { return noted(x) ? x.tel_loin === true : null; }],
      ["Salle", function (x) { return noted(x) ? x.salle === true : null; }],
      ["Sans fast-food", function (x) { return noted(x) ? x.fastfood !== true : null; }],
      ["Chambre", function (x) { return noted(x) ? x.chambre === true : null; }],
      ["Priorités", function (x) { if (!noted(x)) return null; var k = 0; ["1", "2", "3"].forEach(function (i) { if (x["p" + i + "_ok"] === true) k++; }); return k; }]
    ];
    var h = '<div class="grille"><span></span>' + ds.map(function (d, i) { return '<span class="h">' + D1[i] + "<br>" + parseISO(d).getDate() + "</span>"; }).join("");
    rows.forEach(function (r) {
      h += '<span class="r">' + tx(r[0]) + "</span>";
      ds.forEach(function (d) {
        var v = r[1](day(d), d), t = esc(longDate(d) + " · " + r[0]);
        if (v === null) h += '<span class="pt na" title="' + t + ' : non noté"></span>';
        else if (typeof v === "number") h += '<span class="pt n' + (v === 3 ? " on" : "") + '" title="' + t + " : " + v + ' sur 3">' + v + "</span>";
        else h += '<span class="pt' + (v ? " on" : "") + '" title="' + t + (v ? " : oui" : " : non") + '"></span>';
      });
    });
    return h + "</div>";
  }
  function renderRegistre() {
    var m = UI.reg, a = agg(m), b = agg(addDays(m, -7)), c = a.w ? a.w.c : null, t = today();
    var total = 0, st = startDate();
    for (var i = 0; i < 90; i++) { var dd = addDays(st, i); if (dd > t) break; if (noted(day(dd))) total++; }
    var jt = Math.max(0, Math.min(90, jOf(t)));
    function ch(k, v, sub, e) { return '<div class="chiffre"><span class="cap">' + esc(k) + '</span><span class="v">' + v + '</span><span class="t">' + tx(sub) + "</span>" + e + "</div>"; }
    var html = '<header class="mast apparait"><span class="date">' + esc(semDates(m)) + '</span><h1 class="titre">Le <em>registre.</em></h1>' + navSem("reg") + "</header>";
    if (!a.noted && !b.noted) html += '<p class="avis">Rien n\'est encore inscrit sur ces deux semaines. Chaque matin, note ta nuit : le registre se remplit de lui-même.</p>';
    html += '<div class="chiffres">' +
      ch("Sommeil moyen", a.sleepAvg != null ? Math.floor(a.sleepAvg / 60) + "<small>h</small>" + pad(Math.round(a.sleepAvg % 60)) : "—", "Norme : 7 à 9 h", ecart(a.sleepAvg, b.sleepAvg, "up", dur)) +
      ch("Salle", a.salle + (c && c.salle ? "<small>/ " + c.salle + "</small>" : ""), "Séances", ecart(a.noted ? a.salle : null, b.noted ? b.salle : null, "up", String)) +
      ch("Écran", a.ecranAvg != null ? fr(a.ecranAvg, 1) + "<small>h</small>" : "—", c && c.ecran ? "Cible : " + fr(c.ecran, 1) + " h au plus" : "Départ : 6 h par jour", ecart(a.ecranAvg, b.ecranAvg, "down", function (n) { return fr(n, 1) + " h"; })) +
      ch("Dépenses", a.depN ? fr(a.dep, 0) + "<small>€</small>" : "—", c && c.depenses ? "Cible : " + c.depenses + " € au plus" : "Semaine de mesure", ecart(a.depN ? a.dep : null, b.depN ? b.dep : null, "down", function (n) { return fr(n, 0) + " €"; })) +
      "</div>";
    html += '<section class="sec"><div class="prog"><div class="l"><span class="cap">Programme</span><span class="petit">' + total + " jours inscrits · jour " + jt + ' sur 90</span></div><div class="bar"><span style="width:' + (jt / 90 * 100) + '%"></span></div></div></section>';
    html += '<section class="sec graph"><div class="sec-h"><span class="cap">Quatorze nuits</span><h2 class="titre-s">Le sommeil</h2></div>' + courbe(m) + '<p class="petit">À gauche, la semaine précédente. Or : sept heures ou plus. Rouge : moins.</p></section>';
    html += '<section class="sec"><div class="sec-h"><span class="cap">Sept jours</span><h2 class="titre-s">La régularité</h2></div><div class="defile">' + grille(m) + "</div></section>";
    function tr(dom, ind, cv, pv, tg) { return '<tr><td>' + tx(dom) + '</td><td class="k">' + tx(ind) + '</td><td class="d">' + esc(cv) + '</td><td class="d" style="color:rgba(236,231,221,.5)">' + esc(pv) + "</td><td>" + tx(tg) + "</td></tr>"; }
    html += '<section class="sec"><div class="sec-h"><span class="cap">Semaine contre semaine</span><h2 class="titre-s">Tous les domaines</h2></div><div class="defile"><table class="livre" style="min-width:520px"><thead><tr><th>Domaine</th><th>Indicateur</th><th>Celle-ci</th><th>Avant</th><th>Cible</th></tr></thead><tbody>' +
      tr("Organisation", "Priorités tenues", a.pp ? a.pd + "/" + a.pp : "—", b.pp ? b.pd + "/" + b.pp : "—", "3 par jour") +
      tr("Organisation", "Jours notés", a.noted + "/7", b.noted + "/7", "6 sur 7") +
      tr("Hygiène", "Téléphone loin du lit", a.tel + "/7", b.tel + "/7", "7 sur 7") +
      tr("Chambre", "Remise en ordre", a.chambre + "/7", b.chambre + "/7", "5 sur 7 dès la semaine VI") +
      tr("Discipline", "Écran par jour", a.ecranAvg != null ? fr(a.ecranAvg, 1) + " h" : "—", b.ecranAvg != null ? fr(b.ecranAvg, 1) + " h" : "—", c && c.ecran ? fr(c.ecran, 1) + " h au plus" : "mesure") +
      tr("Études", "Temps d'études", dur(a.etudes), dur(b.etudes), c && c.etudes ? dur(c.etudes) : "—") +
      tr("Business", "Temps business", dur(a.biz), dur(b.biz), "environ 13 h") +
      tr("Business", "Prospects contactés", String(a.contacts), String(b.contacts), c ? String(c.contacts) : "—") +
      tr("Business", "Clients signés", a.rev.clients || "—", b.rev.clients || "—", "4 au jour 90") +
      tr("Finances", "Dépenses", fr(a.dep, 0) + " €", fr(b.dep, 0) + " €", c && c.depenses ? c.depenses + " € au plus" : "mesure") +
      tr("Finances", "Mis de côté", a.rev.epargne ? a.rev.epargne + " €" : "—", b.rev.epargne ? b.rev.epargne + " €" : "—", "250 € par mois") +
      tr("Corps", "Sommeil moyen", a.sleepAvg != null ? dur(a.sleepAvg) : "—", b.sleepAvg != null ? dur(b.sleepAvg) : "—", "7 h et plus") +
      tr("Corps", "Coucher moyen", a.bedAvg != null ? clock(a.bedAvg) : "—", b.bedAvg != null ? clock(b.bedAvg) : "—", c ? c.coucher : "—") +
      tr("Corps", "Pas par jour", a.pasAvg != null ? fr(a.pasAvg, 0) : "—", b.pasAvg != null ? fr(b.pasAvg, 0) : "—", "départ 5 844") +
      tr("Corps", "Fast-food", String(a.fast), String(b.fast), "1 au plus") +
      tr("Corps", "Énergie au réveil", a.enAvg != null ? fr(a.enAvg, 1) + "/5" : "—", b.enAvg != null ? fr(b.enAvg, 1) + "/5" : "—", "en hausse") +
      tr("Vision", "Bilan du dimanche", noted(a.rev) ? "fait" : "non", noted(b.rev) ? "fait" : "non", "chaque semaine") +
      "</tbody></table></div></section>";
    $("#v-registre").innerHTML = html;
  }

  /* ================= Cap ================= */
  function renderCap() {
    var p = plan();
    if (!p) { $("#v-cap").innerHTML = '<p class="avis">Le plan n\'est pas encore déposé.</p>'; return; }
    var t = today(), cw = weekOf(t), cp = phaseOf(t), v = p.vision;
    function wd(w) { var s = addDays(p.debut, (w.n - 1) * 7), e = w.n === p.semaines.length ? addDays(p.debut, 89) : addDays(s, 6); return shortDate(s) + " — " + shortDate(e); }
    var html = "";
    if (v) {
      html += '<header class="vision apparait"><span class="cap or">Dans cinq ans</span><span class="lieu">' + esc(v.lieu) + '.</span><p class="phrase">' + tx(v.cinq_ans) + '</p><p class="pourquoi">' + tx(v.pourquoi) + "</p></header>" +
        '<section class="sec"><div class="sec-h"><span class="cap">D\'ici là</span><h2 class="titre-s">La distance</h2></div><div class="defile"><table class="livre distance"><thead><tr><th></th><th>Aujourd\'hui</th><th>Jour 90</th><th>Dans un an</th><th>Dans cinq ans</th></tr></thead><tbody>' +
        v.distance.map(function (r) { return "<tr>" + r.map(function (c) { return "<td>" + tx(c) + "</td>"; }).join("") + "</tr>"; }).join("") + "</tbody></table></div>" +
        '<p class="petit ital" style="font-family:var(--f-d);font-size:16px">' + tx(v.risque) + "</p></section>";
    }
    html += '<section class="sec"><div class="sec-h"><span class="cap">Quatre-vingt-dix jours · ' + esc(shortDate(p.debut)) + " — " + esc(shortDate(addDays(p.debut, 89))) + '</span><h2 class="titre-s">Une chose à la fois.</h2><p class="lead">Une à deux nouvelles habitudes par semaine. Le sommeil d\'abord : la salle du matin, la concentration et le business en dépendent.</p></div>' +
      '<div class="phases">' + p.phases.map(function (ph) { return '<div class="phase' + (cp === ph ? " now" : "") + '"><span class="j">' + esc(ph.jours) + '</span><div><div class="n">' + tx(ph.nom) + '</div><div class="b">' + tx(ph.but) + "</div></div></div>"; }).join("") + "</div></section>" +
      '<section class="sec"><div class="sec-h"><span class="cap">Mesurables</span><h2 class="titre-s">Les objectifs</h2></div><dl class="obj">' + p.objectifs.map(function (o) { return "<div><dt>" + tx(o.nom) + "</dt><dd>" + tx(o.mesure) + "</dd></div>"; }).join("") + "</dl></section>" +
      '<section class="sec"><div class="sec-h"><span class="cap">Treize semaines</span><h2 class="titre-s">Le programme</h2></div><div>' +
      p.semaines.map(function (w) {
        var now = cw === w || (!cw && jOf(t) < 1 && w.n === 1);
        return '<details class="sem' + (now ? " now" : "") + '"' + (now ? " open" : "") + '><summary><span class="r">' + ROM[w.n] + '</span><span class="t">' + tx(w.titre) + '</span><span class="d">' + esc(wd(w)) + "</span></summary>" +
          '<div class="corps"><ol class="intent">' + w.priorites.map(function (x) { return "<li>" + tx(x) + "</li>"; }).join("") + "</ol>" +
          '<dl class="kv"><div><dt>Actions</dt><dd><ul class="puces">' + w.actions.map(function (x) { return "<li>" + tx(x) + "</li>"; }).join("") + "</ul></dd></div>" +
          "<div><dt>Temps</dt><dd>" + tx(w.temps) + "</dd></div><div><dt>Ressources</dt><dd>" + tx(w.ressources) + "</dd></div><div><dt>Résultat attendu</dt><dd>" + tx(w.resultats) + "</dd></div><div><dt>Indicateurs</dt><dd>" + tx(w.indicateurs.join(" · ")) + "</dd></div></dl></div></details>";
      }).join("") + "</div></section>" +
      '<section class="sec"><div class="sec-h"><span class="cap">Tranché</span><h2 class="titre-s">Les décisions</h2></div><ul class="puces">' + p.decisions.map(function (x) { return "<li>" + tx(x) + "</li>"; }).join("") + "</ul></section>" +
      '<section class="sec"><div class="sec-h"><span class="cap">À partir de la semaine VII</span><h2 class="titre-s">La semaine type</h2></div><div class="defile"><table class="livre" style="min-width:560px"><thead><tr><th>Heure</th><th>Lun · Mar · Jeu · Ven</th><th>Mercredi</th><th>Samedi</th><th>Dimanche</th></tr></thead><tbody>' +
      p.semaineType.map(function (r) { return "<tr>" + r.map(function (c, i) { return "<td" + (i === 0 ? ' class="d"' : "") + ">" + tx(c) + "</td>"; }).join("") + "</tr>"; }).join("") + "</tbody></table></div></section>";
    $("#v-cap").innerHTML = html;
  }

  /* ================= État des lieux ================= */
  function graduation(n) { var s = ""; for (var i = 1; i <= 10; i++) s += "<i" + (i <= n ? ' class="on"' : "") + "></i>"; return '<div class="graduation" aria-hidden="true">' + s + "</div>"; }
  function renderEtat() {
    var p = plan();
    if (!p) { $("#v-etat").innerHTML = '<p class="avis">L\'état des lieux n\'est pas encore déposé.</p>'; return; }
    function bloc(t, a) { return a && a.length ? '<div class="champ"><span class="lb">' + tx(t) + '</span><ul class="puces">' + a.map(function (x) { return "<li>" + tx(x) + "</li>"; }).join("") + "</ul></div>" : ""; }
    var html = '<header class="mast apparait"><span class="date">Établi le ' + esc(p.maj || "") + '</span><h1 class="titre">L\'état <em>des lieux.</em></h1><p class="lead">Classé par impact sur ta vie. Chaque note repose sur tes propres réponses et sur tes données Santé.</p></header>' +
      '<section class="dom"><div class="dom-h"><div><span class="cap or">Cohérence d\'ensemble</span></div><span class="note">' + p.synthese.note + "<small>/10</small></span></div>" + graduation(p.synthese.note) + '<p style="font:400 18px/1.5 var(--f-d)">' + tx(p.synthese.texte) + "</p></section>" +
      p.audit.map(function (d, i) {
        return '<section class="dom"><div class="dom-h"><div style="display:grid;gap:8px"><span class="urg ' + esc(d.urg) + '">' + ROM[i + 1] + " · " + esc(d.urg) + '</span><h2 class="titre-s">' + tx(d.nom) + '</h2></div><span class="note">' + d.note + "<small>/10</small></span></div>" + graduation(d.note) +
          '<p class="lead">' + tx(d.justif) + "</p>" +
          '<details class="pli"><summary>Forces, faiblesses, habitudes</summary><div class="in">' + bloc("Forces", d.forces) + bloc("Faiblesses", d.faiblesses) + bloc("Habitudes à défaire", d.contre) + bloc("Possibilités", d.possib) + "</div></details>" +
          '<div class="champ"><span class="lb">Recommandations</span><ol class="recos">' + d.recos.map(function (x) { return "<li>" + tx(x) + "</li>"; }).join("") + "</ol></div></section>";
      }).join("");
    $("#v-etat").innerHTML = html;
  }

  /* ================= Accès (version GitHub) ================= */
  function renderAcces() {
    if (B.kind === "db" || (B.kind === "gh" && cfg.token)) {
      var n = dirtyPaths().length;
      var err = SYNC.state === "bad" ? (SYNC.error === "auth" ? "L'accès est refusé. Crée une nouvelle clé et reconnecte-toi." : (SYNC.error === "repo" ? "Dépôt introuvable." : "Erreur d'enregistrement.")) : "";
      $("#v-acces").innerHTML = '<header class="mast"><span class="date">Réglages</span><h1 class="titre">L\'<em>enregistrement.</em></h1></header>' +
        (err ? '<p class="avis ko">' + tx(err) + "</p>" : "") +
        '<section class="sec"><table class="livre"><tbody><tr><td class="k">Stockage</td><td>' + (B.kind === "db" ? "Espace privé claude.ai" : esc(cfg.repo)) + '</td></tr><tr><td class="k">En attente</td><td class="d">' + n + '</td></tr><tr><td class="k">Dernier enregistrement</td><td class="d">' + (SYNC.lastOk ? pad(SYNC.lastOk.getHours()) + ":" + pad(SYNC.lastOk.getMinutes()) : "—") + "</td></tr></tbody></table>" +
        '<button type="button" class="bouton plein" id="sync-now">Enregistrer maintenant</button>' + (B.kind === "gh" ? '<button type="button" class="bouton" id="logout">Se déconnecter de cet appareil</button>' : "") + "</section>";
      return;
    }
    var standalone = window.navigator.standalone === true || (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
    $("#v-acces").innerHTML = '<div class="acces apparait"><div class="mono">Life<br><i>OS.</i></div><p class="lead">Ton registre privé. Les données vivent dans ton dépôt GitHub privé, et nulle part ailleurs.</p>' +
      (standalone ? "" : '<p class="avis">Installe-la d\'abord : dans Safari, Partager, puis « Sur l\'écran d\'accueil ». Ouvre ensuite LIFE OS depuis l\'icône pour te connecter : une connexion faite dans Safari ne passe pas dans l\'app installée.</p>') +
      '<ol class="etapes"><li><span>Ouvre <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">github.com · Fine-grained token</a>.</span></li>' +
      "<li><span>Nom : LIFE OS. Expiration : un an. Accès : <b>Only select repositories</b>, <b>life-os-data</b>.</span></li>" +
      "<li><span>Permissions du dépôt : <b>Contents · Read and write</b>. Rien d'autre.</span></li>" +
      "<li><span>Copie la clé et colle-la ci-dessous. Ne l'envoie jamais dans une conversation.</span></li></ol>" +
      '<div class="champ"><label for="tok">Clé d\'accès</label><input class="saisie" id="tok" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="github_pat_…"></div>' +
      '<div class="champ"><label for="repo">Dépôt</label><input class="saisie" id="repo" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" value="' + esc(cfg.repo) + '"></div>' +
      '<p class="petit" id="msg" role="status"></p><button type="button" class="bouton plein" id="connect">Entrer</button></div>';
  }
  function connect() {
    var tok = ($("#tok").value || "").trim(), repo = ($("#repo").value || "").trim(), msg = $("#msg");
    if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) { msg.textContent = "Nom de dépôt invalide (compte/dépôt)."; return; }
    if (tok.length < 20) { msg.textContent = "Colle la clé complète."; return; }
    msg.textContent = "Vérification…";
    fetch("https://api.github.com/repos/" + repo, { cache: "no-store", headers: { "Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json" } }).then(function (r) {
      if (r.status === 401) { msg.textContent = "Clé refusée : vérifie qu'elle est complète."; return; }
      if (r.status === 404 || r.status === 403) { msg.textContent = "Cette clé n'a pas accès à " + repo + "."; return; }
      if (!r.ok) { msg.textContent = "GitHub ne répond pas (" + r.status + ")."; return; }
      cfg = { token: tok, repo: repo }; LS.set("cfg", cfg); toast("Bienvenue");
      location.hash = "#jour"; runSync(true).then(route);
    }, function () { msg.textContent = "Pas de connexion."; });
  }

  /* ================= Navigation ================= */
  var VIEWS = { jour: renderJour, semaine: renderSemaine, registre: renderRegistre, cap: renderCap, etat: renderEtat, acces: renderAcces };
  function show(v) {
    if (B.kind && !ready()) v = "acces";
    if (!VIEWS[v]) v = "jour";
    UI.view = v;
    Object.keys(VIEWS).forEach(function (k) { $("#v-" + k).hidden = k !== v; });
    $$("#nav a").forEach(function (a) { if (a.getAttribute("data-v") === v) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    $("#nav").hidden = !ready();
    VIEWS[v](); paintSync();
  }
  function route() { var h = location.hash.replace("#", ""); show(h || "jour"); }
  function refresh() {
    var a = document.activeElement, root = $("#v-" + UI.view);
    if (a && root && root.contains(a) && /INPUT|TEXTAREA/.test(a.tagName)) return;
    show(UI.view);
  }
  window.addEventListener("hashchange", function () { route(); window.scrollTo(0, 0); });
  function toast(t) { var el = document.createElement("div"); el.className = "toast apparait"; el.textContent = t; document.body.appendChild(el); setTimeout(function () { el.remove(); }, 1600); }
  function grow(el) { el.style.height = "auto"; el.style.height = (el.scrollHeight + 2) + "px"; }

  /* ================= Événements ================= */
  document.addEventListener("input", function (e) {
    var el = e.target;
    if (el.tagName === "TEXTAREA") grow(el);
    var k = el.getAttribute && el.getAttribute("data-d");
    if (k) {
      var v = el.value;
      if (k === "depenses" || k === "pas") { var n = num(v); v = n == null ? null : n; }
      setDay(UI.day, k, v);
      if (k === "coucher" || k === "reveil") { el.classList.toggle("vide", !el.value); var x = day(UI.day); $("#duree").innerHTML = dureeHTML(sleepMin(x.coucher, x.reveil)); }
      refreshTenue(); return;
    }
    var w = el.getAttribute && el.getAttribute("data-w");
    if (w) setReview(UI.week, w, el.value);
  });
  document.addEventListener("change", function (e) {
    var el = e.target, k = el.getAttribute && el.getAttribute("data-d");
    if (k === "coucher" || k === "reveil") { setDay(UI.day, k, el.value); var x = day(UI.day); $("#duree").innerHTML = dureeHTML(sleepMin(x.coucher, x.reveil)); refreshTenue(); }
  });
  document.addEventListener("click", function (e) {
    var t = e.target;
    var h = t.closest("[data-h]");
    if (h) { var k = h.getAttribute("data-h"), v = day(UI.day)[k] !== true; setDay(UI.day, k, v ? true : null); h.setAttribute("aria-pressed", String(v)); refreshTenue(); return; }
    var pk = t.closest("[data-pok]");
    if (pk) { var i = pk.getAttribute("data-pok"), pv = day(UI.day)["p" + i + "_ok"] !== true; setDay(UI.day, "p" + i + "_ok", pv ? true : null); pk.setAttribute("aria-pressed", String(pv)); pk.parentNode.classList.toggle("faite", pv); refreshTenue(); return; }
    var en = t.closest("[data-en]");
    if (en) { var ev = +en.getAttribute("data-en"), cur = day(UI.day).energie === ev ? null : ev; setDay(UI.day, "energie", cur); $$("[data-en]").forEach(function (b) { b.setAttribute("aria-pressed", String(+b.getAttribute("data-en") === cur)); }); return; }
    var c = t.closest("[data-c]");
    if (c) {
      var ck = c.getAttribute("data-c"), def = RELEVE.filter(function (x) { return x.k === ck; })[0], val = num(day(UI.day)[ck]) || 0;
      val = Math.max(0, Math.round((val + def.step * +c.getAttribute("data-dir")) * 10) / 10);
      setDay(UI.day, ck, val === 0 ? null : val);
      $("#cv-" + ck).innerHTML = fr(val, 1) + (def.u ? "<small>" + def.u + "</small>" : ""); return;
    }
    var dd = t.closest("[data-day]");
    if (dd) { var n = +dd.getAttribute("data-day"); UI.day = n === 0 ? today() : addDays(UI.day, n); UI.navigated = n !== 0; renderJour(); scheduleSync(0); window.scrollTo(0, 0); return; }
    var dw = t.closest("[data-week]");
    if (dw) { UI.week = addDays(UI.week, +dw.getAttribute("data-week")); renderSemaine(); scheduleSync(0); return; }
    var dr = t.closest("[data-reg]");
    if (dr) { UI.reg = addDays(UI.reg, +dr.getAttribute("data-reg")); renderRegistre(); scheduleSync(0); return; }
    if (t.closest("#etat")) { if (B.kind) location.hash = "#acces"; return; }
    if (t.closest("#connect")) { connect(); return; }
    if (t.closest("#sync-now")) { runSync(true).then(function () { if (UI.view === "acces") renderAcces(); toast("Enregistré"); }); return; }
    if (t.closest("#logout")) { cfg = { token: "", repo: cfg.repo }; LS.set("cfg", cfg); route(); return; }
  });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") { LS.set(FKEY, files); runSync(); return; }
    var t = today(); if (UI.day !== t && UI.view === "jour" && !UI.navigated) UI.day = t;
    runSync().then(refresh);
  });
  window.addEventListener("online", function () { runSync(true); });
  window.addEventListener("offline", paintSync);
  window.addEventListener("pagehide", function () { LS.set(FKEY, files); });

  /* ================= Démarrage ================= */
  function start(kind, db) {
    B.kind = kind; B.db = db || null;
    if (kind === "db") { FKEY = "files-db"; files = LS.get(FKEY) || {}; }
    route();
    if (ready()) runSync(true);
  }
  route();
  var c = window.claude;
  if (c && typeof c.use === "function") {
    Promise.resolve().then(function () { return c.use("db"); }).catch(function () { return null; }).then(function (db) { start(db ? "db" : "gh", db); });
  } else {
    start("gh");
    if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("sw.js").catch(function () { /* l'app marche sans */ });
  }
})();
