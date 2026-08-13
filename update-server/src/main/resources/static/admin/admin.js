/* ============================================================
   WinAppMigrator · 管理后台
   纯原生 JS，无框架无外部依赖；所有数据真实调用后端 API
   ============================================================ */

(function () {
  "use strict";

  /* ---------- 常量与状态 ---------- */

  var API = {
    login: "/admin/api/login",
    site: "/admin/api/site",
    siteImage: "/admin/api/site/image",
    version: "/admin/api/version",
    stats: "/admin/api/stats"
  };

  var TOKEN_KEY = "wm_admin_token";
  var token = localStorage.getItem(TOKEN_KEY) || null;

  var state = {
    versions: [],       // 版本列表缓存（统计页版本表复用）
    trend: []           // 趋势数据缓存
  };

  var chart = {           // canvas 图表绘制上下文
    canvas: null,
    ctx: null,
    data: [],
    hover: null,
    raf: 0
  };

  /* ---------- DOM 快捷引用 ---------- */

  var $ = function (id) { return document.getElementById(id); };

  var els = {
    loginView: $("loginView"),
    mainView: $("mainView"),
    loginForm: $("loginForm"),
    password: $("password"),
    loginError: $("loginError"),
    loginBtn: $("loginBtn"),
    togglePwd: $("togglePwd"),
    logoutBtn: $("logoutBtn"),
    // 内容管理
    siteTitle: $("siteTitle"),
    siteSlogan: $("siteSlogan"),
    siteDescription: $("siteDescription"),
    siteHeroImage: $("siteHeroImage"),
    uploadHeroBtn: $("uploadHeroBtn"),
    heroFileInput: $("heroFileInput"),
    heroUploadHint: $("heroUploadHint"),
    featureList: $("featureList"),
    statList: $("statList"),
    addFeatureBtn: $("addFeatureBtn"),
    addStatBtn: $("addStatBtn"),
    saveSiteBtn: $("saveSiteBtn"),
    // 版本发布
    releaseForm: $("releaseForm"),
    releaseVersion: $("releaseVersion"),
    releaseFile: $("releaseFile"),
    releaseFileName: $("releaseFileName"),
    releaseNotes: $("releaseNotes"),
    releaseForce: $("releaseForce"),
    releaseMsg: $("releaseMsg"),
    releaseBtn: $("releaseBtn"),
    versionTbody: $("versionTbody"),
    versionCount: $("versionCount"),
    // 统计
    totalDownloads: $("totalDownloads"),
    trendCanvas: $("trendCanvas"),
    chartBox: $("chartBox"),
    chartTip: $("chartTip"),
    chartEmpty: $("chartEmpty"),
    statsVersionTbody: $("statsVersionTbody"),
    toast: $("toast")
  };

  /* ============================================================
     fetch 统一封装：携带 Authorization、统一错误处理、401 登出
     ============================================================ */

  function apiFetch(url, options) {
    options = options || {};
    var headers = Object.assign({}, options.headers || {});
    if (token) {
      headers["Authorization"] = "Bearer " + token;
    }
    if (options.body instanceof FormData) {
      // multipart：浏览器自动设置 Content-Type，不能手动覆盖
      delete headers["Content-Type"];
    } else if (options.body && typeof options.body !== "string") {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.body);
    }
    return fetch(url, Object.assign({}, options, { headers: headers })).then(
      function (res) {
        if (res.status === 401) {
          logout();
          throw new Error("登录状态已失效，请重新登录");
        }
        return res.text().then(function (text) {
          var data = null;
          if (text) {
            try { data = JSON.parse(text); } catch (e) { data = text; }
          }
          if (!res.ok) {
            var msg = "请求失败（" + res.status + "）";
            if (data && typeof data === "object" && data.error) {
              msg = data.error;
            } else if (typeof data === "string") {
              msg = data;
            }
            var err = new Error(msg);
            err.status = res.status;
            throw err;
          }
          return data;
        });
      }
    );
  }

  /* ============================================================
     登录 / 登出
     ============================================================ */

  function showLogin() {
    els.mainView.classList.add("hidden");
    els.loginView.classList.remove("hidden");
    els.password.value = "";
    els.loginError.classList.add("hidden");
  }

  function showMain() {
    els.loginView.classList.add("hidden");
    els.mainView.classList.remove("hidden");
    loadAll();
  }

  function logout() {
    token = null;
    localStorage.removeItem(TOKEN_KEY);
    showLogin();
    toast("已退出登录", "err");
  }

  function doLogin() {
    var password = els.password.value;
    if (!password) {
      showLoginError("请输入访问密码");
      return;
    }
    setBtnBusy(els.loginBtn, true, "登录中…");
    apiFetch(API.login, {
      method: "POST",
      body: { password: password }
    })
      .then(function (data) {
        token = data && data.token ? data.token : null;
        if (!token) throw new Error("服务端未返回有效令牌");
        localStorage.setItem(TOKEN_KEY, token);
        showMain();
        toast("登录成功", "ok");
      })
      .catch(function (err) {
        showLoginError(err.message || "登录失败");
      })
      .finally(function () {
        setBtnBusy(els.loginBtn, false, "登 录");
      });
  }

  function showLoginError(msg) {
    els.loginError.textContent = msg;
    els.loginError.classList.remove("hidden");
  }

  function setBtnBusy(btn, busy, text) {
    if (busy) {
      btn.dataset.origin = btn.textContent;
      btn.disabled = true;
      btn.textContent = text;
    } else {
      btn.disabled = false;
      btn.textContent = text || btn.dataset.origin || btn.textContent;
    }
  }

  /* ============================================================
     页面总加载
     ============================================================ */

  function loadAll() {
    loadSite();
    loadVersions();
  }

  /* ============================================================
     内容管理
     ============================================================ */

  function loadSite() {
    return apiFetch(API.site)
      .then(function (data) {
        var content = (data && data.content) || {};
        els.siteTitle.value = content.title || "";
        els.siteSlogan.value = content.slogan || "";
        els.siteDescription.value = content.description || "";
        els.siteHeroImage.value = content.heroImage || "";
        renderFeatureRows(content.features || []);
        renderStatRows(content.stats || []);
      })
      .catch(function (err) {
        toast("加载官网内容失败：" + err.message, "err");
      });
  }

  function collectSiteContent() {
    return {
      title: els.siteTitle.value.trim(),
      slogan: els.siteSlogan.value.trim(),
      description: els.siteDescription.value.trim(),
      heroImage: els.siteHeroImage.value.trim(),
      features: collectRows(els.featureList, ["title", "desc"]),
      stats: collectRows(els.statList, ["label", "value"])
    };
  }

  // 从行容器收集数据，跳过全空行
  function collectRows(container, keys) {
    var rows = [];
    container.querySelectorAll(".list-row").forEach(function (rowEl) {
      var item = {};
      keys.forEach(function (key) {
        item[key] = rowEl.querySelector('[data-key="' + key + '"]').value.trim();
      });
      var isEmpty = keys.every(function (key) { return item[key] === ""; });
      if (!isEmpty) rows.push(item);
    });
    return rows;
  }

  function renderFeatureRows(features) {
    els.featureList.innerHTML = "";
    (features || []).forEach(function (f, i) {
      els.featureList.appendChild(
        buildRow(["title", "desc"], f, i, "feature")
      );
    });
  }

  function renderStatRows(stats) {
    els.statList.innerHTML = "";
    (stats || []).forEach(function (s, i) {
      els.statList.appendChild(buildRow(["label", "value"], s, i, "stat"));
    });
  }

  // 构建 features / stats 行编辑器（输入框 + 删除按钮）
  function buildRow(keys, values, index, kind) {
    var rowEl = document.createElement("div");
    rowEl.className = "list-row";

    var label = document.createElement("span");
    label.className = "list-row-label";
    label.textContent = "#" + String(index + 1).padStart(2, "0");
    rowEl.appendChild(label);

    var placeholder = kind === "feature" ? "特性标题" : "标签";
    var input = document.createElement("input");
    input.className = "input";
    input.dataset.key = keys[0];
    input.placeholder = placeholder;
    input.value = (values && values[keys[0]]) || "";
    rowEl.appendChild(input);

    var input2 = document.createElement("input");
    input2.className = "input";
    input2.dataset.key = keys[1];
    input2.placeholder = kind === "feature" ? "特性描述" : "数值";
    input2.value = (values && values[keys[1]]) || "";
    rowEl.appendChild(input2);

    var delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "list-del";
    delBtn.title = "删除该行";
    delBtn.innerHTML =
      '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    delBtn.addEventListener("click", function () {
      rowEl.remove();
      refreshRowIndexes(rowEl.parentElement);
    });
    rowEl.appendChild(delBtn);
    return rowEl;
  }

  function refreshRowIndexes(container) {
    if (!container) return;
    container.querySelectorAll(".list-row").forEach(function (rowEl, i) {
      var label = rowEl.querySelector(".list-row-label");
      if (label) label.textContent = "#" + String(i + 1).padStart(2, "0");
    });
  }

  function saveSite() {
    var content = collectSiteContent();
    setBtnBusy(els.saveSiteBtn, true, "保存中…");
    apiFetch(API.site, {
      method: "PUT",
      body: { content: content }
    })
      .then(function () {
        toast("官网内容已保存", "ok");
      })
      .catch(function (err) {
        toast("保存失败：" + err.message, "err");
      })
      .finally(function () {
        setBtnBusy(els.saveSiteBtn, false, "保存修改");
      });
  }

  function uploadHeroImage(file) {
    var fd = new FormData();
    fd.append("image", file);
    els.heroUploadHint.classList.remove("hidden", "ok", "err");
    els.heroUploadHint.textContent = "上传中…";
    apiFetch(API.siteImage, { method: "POST", body: fd })
      .then(function (data) {
        var url = (data && data.url) || "";
        if (!url) throw new Error("服务端未返回图片地址");
        els.siteHeroImage.value = url;
        els.heroUploadHint.classList.add("ok");
        els.heroUploadHint.textContent = "上传成功：" + url;
        toast("图片上传成功", "ok");
      })
      .catch(function (err) {
        els.heroUploadHint.classList.add("err");
        els.heroUploadHint.textContent = "上传失败：" + err.message;
        toast("图片上传失败：" + err.message, "err");
      });
  }

  /* ============================================================
     版本发布
     ============================================================ */

  function loadVersions() {
    return apiFetch(API.version)
      .then(function (data) {
        state.versions = Array.isArray(data) ? data : [];
        renderVersionTable();
        renderStatsVersionTable();
      })
      .catch(function (err) {
        toast("加载版本列表失败：" + err.message, "err");
      });
  }

  function renderVersionTable() {
    els.versionCount.textContent = String(state.versions.length);
    if (!state.versions.length) {
      els.versionTbody.innerHTML =
        '<tr class="empty-row"><td colspan="7">暂无已发布版本</td></tr>';
      return;
    }
    var html = "";
    state.versions.forEach(function (v) {
      html +=
        "<tr>" +
        '<td class="mono">' + esc(v.version) + "</td>" +
        '<td class="mono">' + esc(v.fileName) + "</td>" +
        '<td class="mono">' + formatSize(v.fileSize) + "</td>" +
        "<td>" + esc(v.notes || "") + "</td>" +
        '<td class="mono">' + formatDate(v.createdAt) + "</td>" +
        '<td><span class="tag-force' + (v.forceUpdate ? "" : " no") + '">' +
          (v.forceUpdate ? "强制" : "可选") + "</span></td>" +
        '<td class="td-right"><button class="btn btn-danger btn-sm" data-del-id="' +
          v.id + '">删除</button></td>' +
        "</tr>";
    });
    els.versionTbody.innerHTML = html;
    els.versionTbody.querySelectorAll("[data-del-id]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        deleteVersion(Number(btn.dataset.delId));
      });
    });
  }

  function renderStatsVersionTable() {
    if (!state.versions.length) {
      els.statsVersionTbody.innerHTML =
        '<tr class="empty-row"><td colspan="4">暂无版本数据</td></tr>';
      return;
    }
    var html = "";
    state.versions.forEach(function (v) {
      html +=
        "<tr>" +
        '<td class="mono">' + esc(v.version) + "</td>" +
        '<td class="mono">' + esc(v.fileName) + "</td>" +
        '<td class="mono">' + formatDate(v.createdAt) + "</td>" +
        '<td class="mono">' + formatSize(v.fileSize) + "</td>" +
        "</tr>";
    });
    els.statsVersionTbody.innerHTML = html;
  }

  function publishVersion() {
    var file = els.releaseFile.files && els.releaseFile.files[0];
    var version = els.releaseVersion.value.trim();
    if (!file) { toast("请选择安装包文件", "err"); return; }
    if (!version) { toast("请填写版本号", "err"); return; }

    var fd = new FormData();
    fd.append("file", file);
    fd.append("version", version);
    fd.append("notes", els.releaseNotes.value.trim());
    fd.append("force", els.releaseForce.checked ? "true" : "false");

    setBtnBusy(els.releaseBtn, true, "发布中…");
    els.releaseMsg.classList.remove("hidden", "ok", "err");
    els.releaseMsg.textContent = "正在上传并发布：" + file.name;

    apiFetch(API.version, { method: "POST", body: fd })
      .then(function () {
        els.releaseMsg.classList.add("ok");
        els.releaseMsg.textContent = "发布成功";
        els.releaseForm.reset();
        els.releaseFileName.textContent = "选择安装包文件";
        toast("版本 " + version + " 发布成功", "ok");
        loadVersions();
      })
      .catch(function (err) {
        els.releaseMsg.classList.add("err");
        els.releaseMsg.textContent = "发布失败：" + err.message;
        toast("发布失败：" + err.message, "err");
      })
      .finally(function () {
        setBtnBusy(els.releaseBtn, false, "发布版本");
      });
  }

  function deleteVersion(id) {
    var target = state.versions.find(function (v) { return v.id === id; });
    var label = target ? target.version : String(id);
    confirmDialog("删除版本", "确定删除版本 " + label + " 吗？该操作不可恢复。")
      .then(function (ok) {
        if (!ok) return;
        apiFetch(API.version + "/" + id, { method: "DELETE" })
          .then(function () {
            toast("版本 " + label + " 已删除", "ok");
            loadVersions();
          })
          .catch(function (err) {
            toast("删除失败：" + err.message, "err");
          });
      });
  }

  /* ============================================================
     统计图表
     ============================================================ */

  function loadStats() {
    return apiFetch(API.stats)
      .then(function (data) {
        data = data || {};
        state.trend = Array.isArray(data.trend) ? data.trend : [];
        state.versions = Array.isArray(data.versions)
          ? data.versions
          : state.versions;
        els.totalDownloads.textContent = formatNumber(data.totalDownloads || 0);
        renderStatsVersionTable();
        drawTrendChart();
      })
      .catch(function (err) {
        toast("加载统计数据失败：" + err.message, "err");
      });
  }

  // ---------- canvas 折线图（自研，无外部库） ----------

  function drawTrendChart() {
    var canvas = els.trendCanvas;
    var box = els.chartBox;
    if (!canvas || !box) return;
    var data = state.trend || [];

    els.chartEmpty.classList.toggle("hidden", data.length > 0);
    canvas.style.display = data.length ? "block" : "none";
    hideTip();

    if (!data.length) return;

    var dpr = window.devicePixelRatio || 1;
    var rect = box.getBoundingClientRect();
    if (rect.width <= 0) return;

    var pad = { top: 24, right: 18, bottom: 38, left: 46 };
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    canvas.style.width = rect.width + "px";
    canvas.style.height = rect.height + "px";
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    var w = rect.width;
    var h = rect.height;
    var plotW = w - pad.left - pad.right;
    var plotH = h - pad.top - pad.bottom;

    var values = data.map(function (d) { return d.downloads || 0; });
    var maxV = Math.max.apply(null, values);
    var minV = Math.min.apply(null, values);
    if (maxV === minV) { maxV = minV + 1; }   // 全零/全相等时保证有绘制区间
    var yMax = niceCeil(maxV);
    var yMin = 0;

    var xStep = data.length > 1 ? plotW / (data.length - 1) : 0;
    var px = function (i) {
      return pad.left + (data.length > 1 ? i * xStep : plotW / 2);
    };
    var py = function (v) {
      return pad.top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
    };

    // ---- 网格 + Y 轴刻度（4 档） ----
    ctx.font = '10px "Cascadia Mono", Consolas, monospace';
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    var ticks = 4;
    for (var t = 0; t <= ticks; t++) {
      var val = yMin + ((yMax - yMin) * t) / ticks;
      var y = py(val);
      ctx.strokeStyle = "rgba(255,255,255,0.06)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();
      ctx.fillStyle = "#5c5c5c";
      ctx.fillText(formatNumber(Math.round(val)), pad.left - 8, y);
    }

    // ---- X 轴日期刻度（稀疏显示） ----
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    var labelEvery = Math.max(1, Math.ceil(data.length / 7));
    data.forEach(function (d, i) {
      if (i % labelEvery !== 0 && i !== data.length - 1) return;
      ctx.fillStyle = "#5c5c5c";
      ctx.fillText(shortDate(d.date), px(i), pad.top + plotH + 10);
    });

    // ---- 渐变填充（深蓝透明渐变） ----
    var grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
    grad.addColorStop(0, "rgba(37,99,235,0.30)");
    grad.addColorStop(0.6, "rgba(37,99,235,0.08)");
    grad.addColorStop(1, "rgba(37,99,235,0)");

    ctx.beginPath();
    data.forEach(function (d, i) {
      var x = px(i);
      var y = py(d.downloads || 0);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(px(data.length - 1), pad.top + plotH);
    ctx.lineTo(px(0), pad.top + plotH);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // ---- 折线 ----
    ctx.beginPath();
    data.forEach(function (d, i) {
      var x = px(i);
      var y = py(d.downloads || 0);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = "#2563eb";
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();

    // ---- 数据点（最后一个高亮） ----
    data.forEach(function (d, i) {
      var x = px(i);
      var y = py(d.downloads || 0);
      ctx.beginPath();
      ctx.arc(x, y, i === data.length - 1 ? 3.5 : 2.2, 0, Math.PI * 2);
      ctx.fillStyle = i === data.length - 1 ? "#ffffff" : "#2563eb";
      ctx.fill();
    });

    // ---- 悬停命中区域 ----
    chart.ctx = ctx;
    chart.data = data;
    chart.hover = { pad: pad, px: px, py: py };
  }

  function onChartMove(ev) {
    if (!chart.hover || !chart.data.length) return;
    var rect = els.chartBox.getBoundingClientRect();
    var mx = ev.clientX - rect.left;
    var my = ev.clientY - rect.top;
    var pad = chart.hover.pad;

    var idx = -1;
    var best = 18; // 命中半径（px）
    chart.data.forEach(function (d, i) {
      var x = chart.hover.px(i);
      var y = chart.hover.py(d.downloads || 0);
      var dist = Math.hypot(x - mx, y - my);
      if (dist < best) {
        best = dist;
        idx = i;
      }
    });

    if (idx < 0) { hideTip(); return; }
    var d = chart.data[idx];
    var x = chart.hover.px(idx);
    var y = chart.hover.py(d.downloads || 0);

    els.chartTip.innerHTML =
      '<span class="tip-date">' + esc(d.date) + "</span>" +
      '<span class="tip-value">下载 ' + formatNumber(d.downloads || 0) + " 次</span>";
    els.chartTip.classList.remove("hidden");

    var tipW = els.chartTip.offsetWidth;
    var tipX = x;
    if (tipX < tipW / 2 + 8) tipX = tipW / 2 + 8;
    if (tipX > rect.width - tipW / 2 - 8) tipX = rect.width - tipW / 2 - 8;
    els.chartTip.style.left = tipX + "px";
    els.chartTip.style.top = y + "px";
  }

  function hideTip() {
    els.chartTip.classList.add("hidden");
  }

  /* ============================================================
     工具函数
     ============================================================ */

  function esc(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // 文件大小格式化：B / KB / MB / GB
  function formatSize(bytes) {
    var n = Number(bytes) || 0;
    if (n <= 0) return "-";
    var units = ["B", "KB", "MB", "GB"];
    var i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (i === 0 ? String(Math.round(n)) : n.toFixed(1)) + " " + units[i];
  }

  // 日期格式化：2026-08-01T10:00:00 -> 2026-08-01 10:00
  function formatDate(iso) {
    if (!iso) return "-";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso).slice(0, 16).replace("T", " ");
    return (
      d.getFullYear() + "-" +
      pad2(d.getMonth() + 1) + "-" +
      pad2(d.getDate()) + " " +
      pad2(d.getHours()) + ":" +
      pad2(d.getMinutes())
    );
  }

  // 趋势图 x 轴短日期：2026-08-01 -> 08-01
  function shortDate(dateStr) {
    var s = String(dateStr || "");
    return s.length >= 10 ? s.slice(5) : s;
  }

  // 千分位格式化
  function formatNumber(n) {
    return String(Number(n) || 0).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  // Y 轴取整：向上取到 1/2/5 的整数倍
  function niceCeil(v) {
    if (v <= 0) return 1;
    var pow = Math.pow(10, Math.floor(Math.log10(v)));
    var m = v / pow;
    var nice = m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10;
    return nice * pow;
  }

  function pad2(n) { return n < 10 ? "0" + n : String(n); }

  var toastTimer = 0;
  function toast(msg, type) {
    els.toast.textContent = msg;
    els.toast.className = "toast" + (type ? " " + type : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      els.toast.classList.add("hidden");
    }, 3000);
  }

  /* ---------- 自定义确认对话框 ---------- */

  var confirmResolve = null;

  function confirmDialog(title, text) {
    $("confirmTitle").textContent = title;
    $("confirmText").textContent = text;
    $("confirmMask").classList.remove("hidden");
    return new Promise(function (resolve) {
      confirmResolve = resolve;
    });
  }

  function closeConfirm(result) {
    $("confirmMask").classList.add("hidden");
    if (confirmResolve) {
      var resolve = confirmResolve;
      confirmResolve = null;
      resolve(result);
    }
  }

  $("confirmOk").addEventListener("click", function () { closeConfirm(true); });
  $("confirmCancel").addEventListener("click", function () { closeConfirm(false); });
  $("confirmMask").addEventListener("click", function (e) {
    if (e.target === $("confirmMask")) closeConfirm(false);
  });
  document.addEventListener("keydown", function (e) {
    if (!$("confirmMask").classList.contains("hidden")) {
      if (e.key === "Escape") closeConfirm(false);
      if (e.key === "Enter") closeConfirm(true);
    }
  });

  /* ============================================================
     事件绑定
     ============================================================ */

  // 登录
  els.loginForm.addEventListener("submit", function (e) {
    e.preventDefault();
    doLogin();
  });

  els.togglePwd.addEventListener("click", function () {
    var input = els.password;
    input.type = input.type === "password" ? "text" : "password";
  });

  els.logoutBtn.addEventListener("click", logout);

  // 标签页切换
  document.querySelectorAll(".tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".tab").forEach(function (t) {
        t.classList.remove("active");
      });
      tab.classList.add("active");
      var name = tab.dataset.tab;
      document.querySelectorAll(".panel").forEach(function (p) {
        p.classList.remove("active");
      });
      $("panel-" + name).classList.add("active");
      // 切页时刷新对应数据
      if (name === "content") loadSite();
      else if (name === "release") loadVersions();
      else if (name === "stats") loadStats();
    });
  });

  // 内容管理
  els.addFeatureBtn.addEventListener("click", function () {
    els.featureList.appendChild(buildRow(["title", "desc"], null, els.featureList.children.length, "feature"));
    refreshRowIndexes(els.featureList);
  });

  els.addStatBtn.addEventListener("click", function () {
    els.statList.appendChild(buildRow(["label", "value"], null, els.statList.children.length, "stat"));
    refreshRowIndexes(els.statList);
  });

  els.saveSiteBtn.addEventListener("click", saveSite);

  els.uploadHeroBtn.addEventListener("click", function () {
    els.heroFileInput.click();
  });

  els.heroFileInput.addEventListener("change", function () {
    if (els.heroFileInput.files && els.heroFileInput.files[0]) {
      uploadHeroImage(els.heroFileInput.files[0]);
    }
    els.heroFileInput.value = "";
  });

  // 版本发布
  els.releaseFile.addEventListener("change", function () {
    var f = els.releaseFile.files && els.releaseFile.files[0];
    els.releaseFileName.textContent = f ? f.name : "选择安装包文件";
  });

  // 拖拽上传支持
  var dropLabel = els.releaseFile.parentElement;
  ["dragover", "dragenter"].forEach(function (evName) {
    dropLabel.addEventListener(evName, function (e) {
      e.preventDefault();
      dropLabel.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach(function (evName) {
    dropLabel.addEventListener(evName, function (e) {
      e.preventDefault();
      dropLabel.classList.remove("dragover");
    });
  });
  dropLabel.addEventListener("drop", function (e) {
    var files = e.dataTransfer && e.dataTransfer.files;
    if (files && files.length) {
      // FileList 只读，需经 DataTransfer 写入 input
      var dt = new DataTransfer();
      dt.items.add(files[0]);
      els.releaseFile.files = dt.files;
      els.releaseFileName.textContent = files[0].name;
    }
  });

  els.releaseForm.addEventListener("submit", function (e) {
    e.preventDefault();
    publishVersion();
  });

  // 统计图表：canvas 悬停提示 + 窗口缩放重绘
  els.chartBox.addEventListener("mousemove", onChartMove);
  els.chartBox.addEventListener("mouseleave", hideTip);

  var resizeTimer = 0;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (!$("panel-stats").classList.contains("active")) return;
      if (state.trend.length) drawTrendChart();
    }, 180);
  });

  /* ============================================================
     启动
     ============================================================ */

  function init() {
    if (token) {
      showMain();
    } else {
      showLogin();
    }
    els.password.focus();
  }

  init();
})();
