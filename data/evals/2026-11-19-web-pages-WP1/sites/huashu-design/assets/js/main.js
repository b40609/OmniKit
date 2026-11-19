// OmniKeep 官網第二版：首屏演出、重點卡片列、膠囊分頁（切換實際截圖）、視窗升起、複製
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // 首屏：文字浮現 → 收件匣畫面升起
  var hero = document.querySelector('.hero');
  if (hero) requestAnimationFrame(function () { hero.classList.add('play'); });

  // 先看重點：左右按鈕
  var gallery = document.getElementById('gallery');
  if (gallery) {
    var prev = document.querySelector('.round[data-dir="-1"]');
    var next = document.querySelector('.round[data-dir="1"]');
    var step = function () {
      var t = gallery.querySelector('.tile');
      return t ? t.getBoundingClientRect().width + 24 : 400;
    };
    var sync = function () {
      var max = gallery.scrollWidth - gallery.clientWidth - 2;
      prev.disabled = gallery.scrollLeft <= 2;
      next.disabled = gallery.scrollLeft >= max;
    };
    [prev, next].forEach(function (b) {
      b.addEventListener('click', function () {
        gallery.scrollBy({ left: step() * Number(b.getAttribute('data-dir')), behavior: reduce ? 'auto' : 'smooth' });
      });
    });
    gallery.addEventListener('scroll', sync, { passive: true });
    window.addEventListener('resize', sync);
    sync();
  }

  // 分頁：點、方向鍵
  function tabs(list, onSelect) {
    var btns = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'));
    function select(i, focus) {
      btns.forEach(function (b, j) {
        var on = i === j;
        b.classList.toggle('is-on', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
        b.tabIndex = on ? 0 : -1;
      });
      if (focus) btns[i].focus();
      onSelect(i, btns[i]);
    }
    btns.forEach(function (b, i) {
      b.addEventListener('click', function () { select(i, false); });
      b.addEventListener('keydown', function (e) {
        var n = btns.length, k = e.key;
        if (k === 'ArrowRight' || k === 'ArrowDown') { e.preventDefault(); select((i + 1) % n, true); }
        if (k === 'ArrowLeft' || k === 'ArrowUp') { e.preventDefault(); select((i - 1 + n) % n, true); }
        if (k === 'Home') { e.preventDefault(); select(0, true); }
        if (k === 'End') { e.preventDefault(); select(n - 1, true); }
      });
    });
    return select;
  }

  // 怎麼運作：三個畫面
  var rig = document.getElementById('stage');
  var stepText = document.getElementById('step-text');
  var copyFor = [
    '<b>丟連結。</b>在 Telegram 把連結傳給自己的機器人，或在 OmniKeep 按頂部的「新增」貼上。',
    '<b>幫你讀完。</b>網頁、影片（YouTube、Bilibili、短影音）、社群貼文（Threads、X）都會抓下內容，交給你接上的 AI 寫出摘要與重點。',
    '<b>找得到。</b>之後用頂部的搜尋框找，或直接提問，回答會附上引用的收藏。'
  ];
  var seg = document.querySelector('.how .seg');
  if (seg && rig) {
    tabs(seg, function (i, btn) {
      rig.setAttribute('data-step', String(i + 1));
      rig.setAttribute('aria-labelledby', btn.id);
      if (stepText) stepText.innerHTML = copyFor[i];
    });
  }

  // 作業系統分頁
  var os = document.querySelector('.st-cmd .seg');
  if (os) {
    var osSelect = tabs(os, function (i, btn) {
      Array.prototype.forEach.call(os.querySelectorAll('[role="tab"]'), function (b) {
        var p = document.getElementById(b.getAttribute('aria-controls'));
        if (p) p.hidden = b !== btn;
      });
    });
    var ua = navigator.userAgent || '';
    if (/Mac|Linux|X11/.test(ua) && !/Windows|Android|iPhone|iPad/.test(ua)) osSelect(1, false);
  }

  // 裝置在捲動時從下方升起（只做 transform，內容一直都在）
  var rigIn = document.querySelector('.rig-in');
  if (rigIn && !reduce) {
    var ticking = false;
    var update = function () {
      ticking = false;
      var r = rigIn.getBoundingClientRect();
      var vh = window.innerHeight || 1;
      var p = Math.min(1, Math.max(0, (vh - r.top) / (vh * 0.75)));   // 0：還在畫面下方；1：已經升到位
      rigIn.style.setProperty('--lift', ((1 - p) * 60).toFixed(1) + 'px');
      rigIn.style.setProperty('--sc', (0.94 + p * 0.06).toFixed(3));
    };
    var onScroll = function () { if (!ticking) { ticking = true; requestAnimationFrame(update); } };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    update();
  }

  // 複製
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy') ? resolve() : reject(); } catch (err) { reject(err); }
      document.body.removeChild(ta);
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll('.copy'), function (btn) {
    var label = btn.textContent;
    btn.addEventListener('click', function () {
      var src = document.getElementById(btn.getAttribute('data-copy'));
      if (!src) return;
      copyText(src.textContent.trim()).then(function () {
        btn.textContent = '已複製'; btn.classList.add('is-done');
        setTimeout(function () { btn.textContent = label; btn.classList.remove('is-done'); }, 1800);
      }, function () {
        btn.textContent = '請手動選取';
        setTimeout(function () { btn.textContent = label; }, 1800);
      });
    });
  });

})();
