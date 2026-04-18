/* ============================================
   SIMPLSHOT — WEBSITE SCRIPTS
   ============================================ */

// 1. Render icons immediately — must happen before anything that could throw
lucide.createIcons();
document.querySelectorAll('svg.lucide').forEach(icon => {
  icon.setAttribute('aria-hidden', 'true');
  icon.setAttribute('focusable', 'false');
});

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

// 2. Mark JS active + immediately reveal in-viewport elements
//    Both in the same synchronous block so the browser never paints a hidden frame
document.documentElement.classList.add('js');

document.querySelectorAll('.reveal-up, .reveal-left, .reveal-right').forEach(el => {
  const rect = el.getBoundingClientRect();
  if (prefersReducedMotion.matches || (rect.top < window.innerHeight && rect.bottom > 0)) {
    el.classList.add('visible');
  }
});

// 3. Observe off-screen elements for scroll-triggered reveal
if (!prefersReducedMotion.matches) {
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        revealObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08, rootMargin: '0px 0px -20px 0px' });

  document.querySelectorAll('.reveal-up, .reveal-left, .reveal-right').forEach(el => {
    if (!el.classList.contains('visible')) revealObserver.observe(el);
  });
}

// 4. Nav scroll state + parallax
const nav = document.getElementById('nav');
const heroImageWrap = document.querySelector('.hero-image-wrap');

window.addEventListener('scroll', () => {
  if (nav) nav.classList.toggle('scrolled', window.scrollY > 20);
}, { passive: true });

// 5. Hero image toggle
const imgSimple   = document.getElementById('imgSimple');
const imgAdvanced = document.getElementById('imgAdvanced');
const btnSimple   = document.getElementById('btnSimple');
const btnAdvanced = document.getElementById('btnAdvanced');
const progress    = document.getElementById('toggleProgress');
const heroContainer = document.getElementById('heroImageContainer');
const heroPreviewStatus = document.getElementById('heroPreviewStatus');

if (imgSimple && imgAdvanced && btnSimple && btnAdvanced && progress && heroContainer && heroPreviewStatus) {
  let currentMode = 'advanced';
  
  const switchTo = (mode) => {
    if (mode === currentMode) return;
    currentMode = mode;
    const toAdvanced = mode === 'advanced';

    imgSimple.classList.toggle('active', !toAdvanced);
    imgAdvanced.classList.toggle('active', toAdvanced);
    imgSimple.hidden = toAdvanced;
    imgAdvanced.hidden = !toAdvanced;
    btnSimple.classList.toggle('active', !toAdvanced);
    btnAdvanced.classList.toggle('active', toAdvanced);
    btnSimple.setAttribute('aria-pressed', String(!toAdvanced));
    btnAdvanced.setAttribute('aria-pressed', String(toAdvanced));
    progress.classList.toggle('right', !toAdvanced);
    heroContainer.setAttribute('aria-label', `Preview of SimplShot in ${mode} mode`);
    heroPreviewStatus.textContent = `Preview showing ${mode} mode.`;
  };

  imgSimple.hidden = true;
  imgAdvanced.hidden = false;
  btnSimple.addEventListener('click', () => switchTo('simple'));
  btnAdvanced.addEventListener('click', () => switchTo('advanced'));
}

// 6. Smooth anchor scroll (offset for sticky nav height)
document.querySelectorAll('a[href^="#"]').forEach(link => {
  link.addEventListener('click', e => {
    const target = document.querySelector(link.getAttribute('href'));
    if (!target) return;
    e.preventDefault();
    window.scrollTo({
      top: target.getBoundingClientRect().top + window.scrollY - 30,
      behavior: prefersReducedMotion.matches ? 'auto' : 'smooth'
    });
  });
});
