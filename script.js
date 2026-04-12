/* ============================================
   SIMPLSHOT — WEBSITE SCRIPTS
   ============================================ */

// 1. Render icons immediately — must happen before anything that could throw
lucide.createIcons();

// 2. Mark JS active + immediately reveal in-viewport elements
//    Both in the same synchronous block so the browser never paints a hidden frame
document.documentElement.classList.add('js');

document.querySelectorAll('.reveal-up, .reveal-left, .reveal-right').forEach(el => {
  const rect = el.getBoundingClientRect();
  if (rect.top < window.innerHeight && rect.bottom > 0) {
    el.classList.add('visible');
  }
});

// 3. Observe off-screen elements for scroll-triggered reveal
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

if (imgSimple && imgAdvanced && btnSimple && btnAdvanced && progress) {
  let currentMode = 'advanced';
  let autoTimer = null;

  const switchTo = (mode, stopAuto) => {
    if (mode === currentMode) return;
    currentMode = mode;
    const toAdvanced = mode === 'advanced';
    imgSimple.classList.toggle('active', !toAdvanced);
    imgAdvanced.classList.toggle('active', toAdvanced);
    btnSimple.classList.toggle('active', !toAdvanced);
    btnAdvanced.classList.toggle('active', toAdvanced);
    progress.classList.toggle('right', !toAdvanced);
    if (stopAuto) clearInterval(autoTimer);
  };

  const startAuto = () => {
    autoTimer = setInterval(() => {
      switchTo(currentMode === 'simple' ? 'advanced' : 'simple', false);
    }, 5000);
  };

  btnSimple.addEventListener('click', () => switchTo('simple', true));
  btnAdvanced.addEventListener('click', () => switchTo('advanced', true));
  startAuto();

  const heroContainer = document.getElementById('heroImageContainer');
  if (heroContainer) {
    heroContainer.addEventListener('mouseenter', () => clearInterval(autoTimer));
    heroContainer.addEventListener('mouseleave', startAuto);
  }
}

// 6. Smooth anchor scroll (offset for sticky nav height)
document.querySelectorAll('a[href^="#"]').forEach(link => {
  link.addEventListener('click', e => {
    const target = document.querySelector(link.getAttribute('href'));
    if (!target) return;
    e.preventDefault();
    window.scrollTo({ top: target.getBoundingClientRect().top + window.scrollY - 80, behavior: 'smooth' });
  });
});
