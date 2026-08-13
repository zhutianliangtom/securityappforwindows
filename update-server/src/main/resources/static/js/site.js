/* ============================================================
   WinAppMigrator 官网前端逻辑
   所有内容均通过真实 API 获取（/api/site、/api/version/latest），
   失败时展示友好错误提示，绝不写入假数据。
   ============================================================ */
(function () {
  'use strict';

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  var REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var SITE = null; // GET /api/site 返回
  var VER = '';    // GET /api/version/latest 提取出的版本号

  /* ---------- 工具函数 ---------- */
  function esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function fmtInt(n) { return Number(n || 0).toLocaleString('en-US'); }
  function fmtNum(n) { return n.toLocaleString('en-US', { maximumFractionDigits: 3 }); }
  function fmtSize(bytes) {
    var b = Number(bytes || 0);
    if (!b) return '';
    var mb = b / 1024 / 1024;
    return mb >= 1024 ? (mb / 1024).toFixed(2) + ' GB' : mb.toFixed(1) + ' MB';
  }
  /* 从任意常见响应形态中提取版本号 */
  function extractVersion(data) {
    if (data == null) return '';
    if (typeof data === 'string') return data;
    if (typeof data.version === 'string') return data.version;
    if (data.latest && typeof data.latest.version === 'string') return data.latest.version;
    if (data.data && typeof data.data.version === 'string') return data.data.version;
    return '';
  }
  /* 拆出「数值 + 后缀」，用于数字滚动（如 99.9% / 10万+） */
  function splitNum(str) {
    if (str == null) return null;
    var m = String(str).match(/^([\d.,]+)\s*(.*)$/);
    if (!m) return null;
    var n = parseFloat(m[1].replace(/,/g, ''));
    if (isNaN(n)) return null;
    return { n: n, suffix: m[2] };
  }
  function currentVersion() {
    return VER || (SITE && SITE.latest && SITE.latest.version) || '';
  }

  /* ---------- 星空/星尘背景（canvas 粒子） ---------- */
  function initStars() {
    var canvas = $('#starfield');
    if (!canvas || !canvas.getContext) return;
    var ctx = canvas.getContext('2d');
    var W = 0, H = 0, stars = [], streaks = [], nextStreak = 2600;
    var mx = 0, my = 0;

    function resize() {
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W * dpr; canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      spawn();
    }
    function spawn() {
      var count = W < 768 ? 45 : 90;
      stars = [];
      for (var i = 0; i < count; i++) {
        stars.push({
          x: Math.random() * W, y: Math.random() * H,
          r: Math.random() * 1.1 + 0.3,
          p: Math.random() * Math.PI * 2,
          sp: Math.random() * 0.22 + 0.04,
          tw: 0.006 + Math.random() * 0.012
        });
      }
    }
    function frame(t) {
      ctx.clearRect(0, 0, W, H);
      var px = mx * 8, py = my * 8;
      /* 星点缓慢上浮 + 呼吸闪烁 */
      for (var i = 0; i < stars.length; i++) {
        var s = stars[i];
        s.y -= s.sp; s.p += s.tw;
        if (s.y < -6) { s.y = H + 6; s.x = Math.random() * W; }
        var a = 0.16 + Math.abs(Math.sin(s.p)) * 0.5;
        ctx.beginPath();
        ctx.arc(s.x + px * 0.25, s.y + py * 0.25, s.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(245,245,245,' + a.toFixed(3) + ')';
        ctx.fill();
      }
      /* 偶发流星 */
      if (t > nextStreak) {
        streaks.push({
          x: Math.random() * W * 0.7 + W * 0.2,
          y: Math.random() * H * 0.4,
          vx: -(3 + Math.random() * 3),
          vy: 1.6 + Math.random() * 1.6,
          life: 1
        });
        nextStreak = t + 3000 + Math.random() * 3500;
      }
      for (var k = streaks.length - 1; k >= 0; k--) {
        var st = streaks[k];
        st.x += st.vx; st.y += st.vy; st.life -= 0.012;
        if (st.life <= 0) { streaks.splice(k, 1); continue; }
        var g = ctx.createLinearGradient(st.x, st.y, st.x - st.vx * 12, st.y - st.vy * 12);
        g.addColorStop(0, 'rgba(245,245,245,' + (0.75 * st.life).toFixed(3) + ')');
        g.addColorStop(1, 'rgba(245,245,245,0)');
        ctx.strokeStyle = g;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.moveTo(st.x, st.y);
        ctx.lineTo(st.x - st.vx * 12, st.y - st.vy * 12);
        ctx.stroke();
      }
      if (!REDUCED) requestAnimationFrame(frame);
    }

    window.addEventListener('resize', resize);
    window.addEventListener('mousemove', function (e) {
      mx = e.clientX / window.innerWidth - 0.5;
      my = e.clientY / window.innerHeight - 0.5;
    });
    resize();
    if (REDUCED) { frame(0); } else { requestAnimationFrame(frame); }
  }

  /* ---------- 内容渲染（全部来自真实 API） ---------- */
  function setField(k, v) {
    if (v == null || v === '') return;
    $$('[data-field="' + k + '"]').forEach(function (el) { el.textContent = v; });
  }

  function hideSection(id) {
    var sec = document.getElementById(id);
    if (sec) sec.style.display = 'none';
    var link = $('.menu a[data-target="' + id + '"]');
    if (link) link.style.display = 'none';
  }

  /* Hero 右侧控制台面板：展示真实版本 / 体积 / 下载量 */
  function consoleHTML() {
    var v = currentVersion();
    var size = fmtSize(SITE.latest && SITE.latest.size);
    var dl = fmtInt(SITE.totalDownloads);
    var lines = [
      '<p class="c-cmd"><span class="c-prompt">$</span> winappmigrator --status</p>',
      '<p class="c-line"><span class="c-key">VERSION</span><span class="c-val">' + esc(v ? 'v' + v : '—') + '</span></p>',
      '<p class="c-line"><span class="c-key">SIZE</span><span class="c-val">' + esc(size || '—') + '</span></p>',
      '<p class="c-line"><span class="c-key">DOWNLOADS</span><span class="c-val">' + esc(dl) + '</span></p>',
      '<p class="c-line"><span class="c-key">STATE</span><span class="c-val c-ok">OK</span></p>',
      '<p class="c-cursor"><span class="caret"></span></p>'
    ];
    return [
      '<div class="console">',
      '  <div class="console-bar"><span class="c-dot"></span><span class="c-dot"></span><span class="c-dot"></span><span class="c-title">winappmigrator — status</span></div>',
      '  <div class="console-body">' + lines.join('\n') + '</div>',
      '</div>'
    ].join('\n');
  }

  function renderSite(d) {
    var c = d.content || {};
    var name = c.title || 'WinAppMigrator';
    var latest = d.latest || {};

    document.title = name + ' — Windows 应用迁移与 AI 桌面助手';
    setField('title', name);
    setField('slogan', c.slogan);
    setField('description', c.description);

    /* Hero 视觉：优先产品截图，否则渲染真实数据控制台 */
    var hv = $('#heroVisual');
    if (c.heroImage) {
      hv.innerHTML = '<figure class="hero-shot"><img src="' + esc(c.heroImage) + '" alt="' + esc(name) + ' 产品展示" loading="eager"><span class="shot-glow" aria-hidden="true"></span></figure>';
    } else {
      hv.innerHTML = consoleHTML();
    }

    /* 下载按钮：指向接口返回的 url */
    var downloadBtn = $('#downloadBtn'), navDownload = $('#navDownload'), clDownload = $('#clDownload');
    if (latest.url) {
      downloadBtn.setAttribute('href', latest.url);
      navDownload.setAttribute('href', latest.url);
      clDownload.setAttribute('href', latest.url);
      downloadBtn.textContent = '下载 ' + name;
    } else {
      /* 接口未提供下载地址时禁用按钮（不造假链接） */
      [downloadBtn, navDownload, clDownload].forEach(function (el) {
        if (el) el.classList.add('is-muted');
      });
    }

    /* 版本信息行 */
    var vStr = currentVersion();
    var sizeTxt = fmtSize(latest.size);
    var line = $('#versionLine');
    if (vStr) {
      line.innerHTML = '最新版本 <a class="v-link" href="#changelog">v' + esc(vStr) + '</a>' +
        (sizeTxt ? '<span class="v-sep">/</span>' + esc(sizeTxt) : '') +
        '<span class="v-sep">/</span>' + fmtInt(d.totalDownloads) + ' 次下载';
    } else {
      line.textContent = '版本信息暂不可用';
    }

    /* 功能特性 */
    var feats = c.features || [];
    if (feats.length) {
      $('#featuresGrid').innerHTML = feats.map(function (f, i) {
        var num = String(i + 1).padStart(2, '0');
        return '<article class="feature-card" data-light>' +
          '<span class="feature-num">/' + num + '</span>' +
          '<h3 class="feature-title">' + esc(f.title) + '</h3>' +
          '<p class="feature-desc">' + esc(f.desc) + '</p>' +
          '<span class="feature-corn" aria-hidden="true"></span>' +
          '</article>';
      }).join('');
    } else {
      hideSection('features');
    }

    /* 数据统计：总下载量 + stats 数组 */
    var dlEl = $('#dlNum');
    dlEl.dataset.target = Number(d.totalDownloads || 0);
    var statsArr = c.stats || [];
    if (statsArr.length) {
      $('#statsGrid').innerHTML = statsArr.map(function (s) {
        var num = splitNum(s.value);
        var vHtml = num
          ? '<span class="stat-value num" data-target="' + num.n + '" data-suffix="' + esc(num.suffix) + '">0</span>'
          : '<span class="stat-value">' + esc(s.value) + '</span>';
        return '<div class="stat"><span class="stat-label">' + esc(s.label) + '</span>' + vHtml + '</div>';
      }).join('');
    } else {
      hideSection('stats');
    }

    /* 更新日志 */
    $('#clVersion').textContent = vStr ? 'v' + vStr : '—';
    $('#clSize').textContent = [sizeTxt, fmtInt(d.totalDownloads) + ' 次下载'].filter(Boolean).join(' / ');
    var notes = String(latest.notes || '').split('\n').map(function (l) { return l.trim(); }).filter(Boolean);
    if (notes.length) {
      $('#clNotes').innerHTML = notes.map(function (l) {
        return '<li>' + esc(l.replace(/^[-•·\s]+/, '')) + '</li>';
      }).join('');
    } else {
      $('#clNotes').innerHTML = '<li>暂无更新说明</li>';
    }

    /* 页脚年份 */
    $('#year').textContent = new Date().getFullYear();
  }

  /* ---------- 数字滚动动画（0 → 实际值） ---------- */
  function roll(el, target, suffix, dur) {
    var t0 = null;
    function tick(ts) {
      if (t0 === null) t0 = ts;
      var p = Math.min((ts - t0) / dur, 1);
      var e = 1 - Math.pow(1 - p, 3); /* easeOutCubic */
      el.textContent = fmtNum(target * e) + suffix;
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
  function initCounters() {
    var els = $$('.num[data-target]');
    if (!els.length) return;
    if (REDUCED || !('IntersectionObserver' in window)) {
      els.forEach(function (el) {
        el.textContent = fmtNum(parseFloat(el.dataset.target)) + (el.dataset.suffix || '');
      });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var el = en.target;
        roll(el, parseFloat(el.dataset.target), el.dataset.suffix || '', 1600);
        io.unobserve(el);
      });
    }, { threshold: 0.4 });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------- 滚动触发展示 ---------- */
  function initReveal() {
    var els = $$('.sr');
    if (!els.length) return;
    if (!('IntersectionObserver' in window)) {
      els.forEach(function (el) { el.classList.add('in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add('in');
          io.unobserve(en.target);
        }
      });
    }, { threshold: 0.16, rootMargin: '0px 0px -40px 0px' });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------- Hero 滚动视差（文字慢、视觉快） ---------- */
  function initParallax() {
    if (REDUCED) return;
    var visual = $('#heroVisual'), copy = $('.hero-copy');
    var ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        var y = window.pageYOffset;
        if (y < window.innerHeight) {
          if (visual) visual.style.transform = 'translate3d(0,' + (y * 0.18) + 'px,0)';
          if (copy) copy.style.transform = 'translate3d(0,' + (y * 0.05) + 'px,0)';
        }
        ticking = false;
      });
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ---------- 特性卡片：鼠标跟随光影 ---------- */
  function initCardLight() {
    $$('.feature-card[data-light]').forEach(function (card) {
      card.addEventListener('mousemove', function (e) {
        var r = card.getBoundingClientRect();
        card.style.setProperty('--mx', ((e.clientX - r.left) / r.width * 100).toFixed(1) + '%');
        card.style.setProperty('--my', ((e.clientY - r.top) / r.height * 100).toFixed(1) + '%');
      });
    });
  }

  /* ---------- 导航滚动状态 ---------- */
  function initNav() {
    var nav = $('#nav');
    function onScroll() { nav.classList.toggle('scrolled', window.pageYOffset > 30); }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ---------- 加载完成：隐藏启动层、触发入场动画 ---------- */
  function finishBoot() {
    var boot = $('#boot');
    boot.classList.add('hidden');
    document.body.classList.add('ready');
    initReveal();
    initCounters();
    initParallax();
    initCardLight();
    initNav();
    setTimeout(function () { boot.style.display = 'none'; }, 600);
  }

  /* ---------- 失败提示：友好报错 + 重试（绝不造假数据） ---------- */
  function showError(err) {
    var boot = $('#boot');
    boot.classList.add('error');
    $('#bootInner').innerHTML =
      '<div class="boot-card">' +
      '<p class="boot-err-code">ERR / API</p>' +
      '<h2 class="boot-err-title">页面数据加载失败</h2>' +
      '<p class="boot-err-msg">无法连接后端服务' +
      (err && err.message ? '（' + esc(err.message) + '）' : '') +
      '，请确认服务已启动后重试。</p>' +
      '<button class="btn btn-primary" id="retryBtn" type="button">重新加载</button>' +
      '</div>';
    $('#retryBtn').addEventListener('click', function () { location.reload(); });
  }

  /* ---------- 启动：并行拉取真实 API ---------- */
  function load() {
    var boot = $('#boot');
    boot.classList.remove('hidden', 'error');
    $('#bootText').textContent = '正在加载产品信息…';

    var siteReq = fetch('/api/site', { headers: { Accept: 'application/json' } }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
    var verReq = fetch('/api/version/latest', { headers: { Accept: 'application/json' } }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });

    Promise.allSettled([siteReq, verReq]).then(function (res) {
      if (res[0].status !== 'fulfilled') {
        showError(res[0].reason);
        return;
      }
      SITE = res[0].value;
      if (res[1].status === 'fulfilled') VER = extractVersion(res[1].value);
      renderSite(SITE);
      finishBoot();
    });
  }

  /* 星星背景最先启动（纯装饰，与 API 无关） */
  initStars();
  load();
})();
