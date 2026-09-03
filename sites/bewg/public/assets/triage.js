/* BEWG assessment finder. Scores answers against services, renders a
   recommendation and builds a plain-text brief the visitor can send or keep. */
(function () {
  'use strict';

  var el = document.getElementById('triage-data');
  if (!el) return;
  var DATA = JSON.parse(el.textContent);
  var form = document.getElementById('triage');
  var svcBySlug = {};
  DATA.services.forEach(function (s) { svcBySlug[s.slug] = s; });

  /* ---- answers ---- */

  function answers() {
    return DATA.questions.map(function (q) {
      var picked = [].slice
        .call(form.querySelectorAll('input[name="' + q.id + '"]:checked'))
        .map(function (i) { return i.value; });
      return { q: q, picked: picked };
    });
  }

  function complete(all) {
    return all.every(function (a) { return !a.q.required || a.picked.length > 0; });
  }

  function score(all) {
    var totals = {};
    all.forEach(function (a) {
      a.picked.forEach(function (v) {
        var opt = a.q.options.find(function (o) { return o.value === v; });
        if (!opt) return;
        Object.keys(opt.weights).forEach(function (slug) {
          totals[slug] = (totals[slug] || 0) + opt.weights[slug];
        });
      });
    });
    return Object.keys(totals)
      .map(function (slug) { return { slug: slug, n: totals[slug] }; })
      .sort(function (a, b) { return b.n - a.n; });
  }

  /* An answer set with no weights at all still deserves an answer. */
  function withFallback(ranked) {
    if (ranked.length) return ranked;
    return [{ slug: 'mould-iaq-investigation', n: 0 }];
  }

  function isUrgent(all) {
    var flat = all.reduce(function (acc, a) { return acc.concat(a.picked); }, []);
    var triggers = [
      'Flood, burst pipe or storm damage',
      'Water stain or active leak',
      'Ongoing symptoms, medical advice already sought',
      'Someone with asthma, allergy or immune vulnerability lives here'
    ];
    return triggers.some(function (t) { return flat.indexOf(t) !== -1; });
  }

  /* ---- progress ---- */

  function updateProgress() {
    var all = answers();
    var done = all.filter(function (a) { return a.picked.length > 0; }).length;
    var bar = document.getElementById('bar');
    if (bar) bar.style.width = Math.round((done / all.length) * 100) + '%';
  }

  form.addEventListener('change', function (e) {
    var opt = e.target.closest('.opt');
    if (opt && e.target.type === 'radio') {
      var name = e.target.name;
      [].slice.call(form.querySelectorAll('input[name="' + name + '"]')).forEach(function (i) {
        i.closest('.opt').classList.toggle('on', i.checked);
      });
    } else if (opt) {
      opt.classList.toggle('on', e.target.checked);
    }
    updateProgress();
    document.getElementById('formErr').hidden = true;
  });

  /* ---- rendering ---- */

  function recHtml(entry, rank) {
    var s = svcBySlug[entry.slug];
    if (!s) return '';
    var primary = rank === 0;
    var body = primary ? s.intro : s.short;
    var deliv = primary
      ? '<ul class="ticks">' + s.deliverables.map(function (d) {
          return '<li>' + escapeHtml(d) + '</li>';
        }).join('') + '</ul>'
      : '';
    return '<div class="rec ' + (primary ? 'primary' : 'also') + '">' +
      '<span class="badge">' + (primary ? 'Recommended' : 'Worth considering') + '</span>' +
      '<h3>' + escapeHtml(s.title) + '</h3>' +
      '<p>' + escapeHtml(body) + '</p>' + deliv +
      '<p style="margin-bottom:0"><a href="services/' + s.slug + '.html"><strong>Read what this ' +
      'investigation involves →</strong></a></p></div>';
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function buildBrief(all, ranked, urgent) {
    var L = [];
    L.push('BEWG ASSESSMENT BRIEF');
    L.push('Generated ' + new Date().toLocaleString('en-AU'));
    L.push('');
    L.push('RECOMMENDED ASSESSMENT');
    ranked.slice(0, 3).forEach(function (r, i) {
      var s = svcBySlug[r.slug];
      if (s) L.push((i === 0 ? '  Primary:   ' : '  Secondary: ') + s.title);
    });
    if (urgent) {
      L.push('');
      L.push('PRIORITY: caller reported active water or a vulnerable occupant.');
    }
    L.push('');
    L.push('CONTACT');
    L.push('  Name:     ' + (val('c-name') || '—'));
    L.push('  Phone:    ' + (val('c-phone') || '—'));
    L.push('  Email:    ' + (val('c-email') || '—'));
    L.push('  Property: ' + (val('c-site') || '—'));
    L.push('');
    L.push('REPORTED SITUATION');
    all.forEach(function (a) {
      L.push('  ' + a.q.label);
      (a.picked.length ? a.picked : ['—']).forEach(function (p) { L.push('    - ' + p); });
    });
    var notes = val('c-notes');
    if (notes) { L.push(''); L.push('ADDITIONAL NOTES'); L.push('  ' + notes.replace(/\n/g, '\n  ')); }
    return L.join('\n');
  }

  function val(id) {
    var n = document.getElementById(id);
    return n ? n.value.trim() : '';
  }

  /* ---- submit ---- */

  var lastAll = null, lastRanked = null, lastUrgent = false;

  function refreshBrief() {
    if (!lastAll) return;
    var text = buildBrief(lastAll, lastRanked, lastUrgent);
    document.getElementById('brief').textContent = text;
    var subject = 'Assessment request — ' + (svcBySlug[lastRanked[0].slug] || {}).title;
    document.getElementById('emailBtn').href =
      'mailto:' + DATA.email + '?subject=' + encodeURIComponent(subject) +
      '&body=' + encodeURIComponent(text);
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var all = answers();
    if (!complete(all)) {
      document.getElementById('formErr').hidden = false;
      var firstGap = all.find(function (a) { return a.q.required && !a.picked.length; });
      var node = form.querySelector('fieldset[data-index="' + DATA.questions.indexOf(firstGap.q) + '"]');
      if (node) node.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    lastAll = all;
    lastRanked = withFallback(score(all));
    lastUrgent = isUrgent(all);

    document.getElementById('recs').innerHTML =
      lastRanked.slice(0, 3).map(recHtml).join('');

    var u = document.getElementById('urgent');
    u.hidden = !lastUrgent;
    if (lastUrgent) u.innerHTML = '<strong>Mention this when you contact us.</strong> ' +
      escapeHtml(DATA.urgency.high);

    refreshBrief();
    document.getElementById('form-stage').hidden = true;
    document.getElementById('result-stage').hidden = false;
    document.getElementById('result-stage').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  ['c-name', 'c-phone', 'c-email', 'c-site', 'c-notes'].forEach(function (id) {
    var n = document.getElementById(id);
    if (n) n.addEventListener('input', refreshBrief);
  });

  document.getElementById('copyBtn').addEventListener('click', function () {
    var text = document.getElementById('brief').textContent;
    var done = function () {
      var c = document.getElementById('copied');
      c.hidden = false;
      setTimeout(function () { c.hidden = true; }, 4000);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallbackCopy);
    } else { fallbackCopy(); }
    function fallbackCopy() {
      var ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (err) { /* clipboard unavailable */ }
      document.body.removeChild(ta);
    }
  });

  document.getElementById('printBtn').addEventListener('click', function () { window.print(); });

  document.getElementById('againBtn').addEventListener('click', function () {
    form.reset();
    [].slice.call(form.querySelectorAll('.opt')).forEach(function (o) { o.classList.remove('on'); });
    updateProgress();
    document.getElementById('result-stage').hidden = true;
    document.getElementById('form-stage').hidden = false;
    document.getElementById('form-stage').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  updateProgress();
})();
