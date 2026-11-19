// OmniKeep page script: the copy buttons beside the install commands. The glyph swaps to a check in
// place, holds 1.8 s and returns (motion.md, Copy button). Nothing else on the page is scripted here.
const CHECK = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m3.5 8.4 2.8 2.8 6.2-6.4"/></svg>';

for (const btn of document.querySelectorAll('.ok-copy')) {
  const glyph = btn.innerHTML;
  const label = btn.getAttribute('aria-label');
  let timer = 0;
  btn.addEventListener('click', async () => {
    const code = btn.parentElement.querySelector('code');
    if (!code) return;
    const text = code.textContent.trim();
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
      document.body.append(area);
      area.select();
      try { document.execCommand('copy'); } catch { /* the command stays selectable by hand */ }
      area.remove();
    }
    btn.innerHTML = CHECK;
    btn.setAttribute('aria-label', '已複製');
    clearTimeout(timer);
    timer = setTimeout(() => { btn.innerHTML = glyph; btn.setAttribute('aria-label', label); }, 1800);
  });
}
