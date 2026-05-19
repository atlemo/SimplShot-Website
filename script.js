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
const heroImages = {
  annotate: document.getElementById('imgAnnotate'),
  edit:     document.getElementById('imgEdit'),
  view:     document.getElementById('imgView'),
};
const heroButtons = {
  annotate: document.getElementById('btnAnnotate'),
  edit:     document.getElementById('btnEdit'),
  view:     document.getElementById('btnView'),
};
const progress          = document.getElementById('toggleProgress');
const heroContainer     = document.getElementById('heroImageContainer');
const heroPreviewStatus = document.getElementById('heroPreviewStatus');

const heroImgSrc = {
  annotate: { dark: 'assets/annotate_dark.webp', light: 'assets/annotate_light.webp' },
  edit:     { dark: 'assets/edit_dark.webp',     light: 'assets/edit_light.webp'     },
  view:     { dark: 'assets/view_dark.webp',     light: 'assets/view_light.webp'     },
};

const allImgs = Object.values(heroImages);
const allBtns = Object.values(heroButtons);
const heroToggle = document.getElementById('toggleProgress')?.parentElement;

const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');

function updateImgSources() {
  const scheme = darkModeQuery.matches ? 'dark' : 'light';
  Object.entries(heroImages).forEach(([mode, img]) => {
    if (img) img.src = heroImgSrc[mode][scheme];
  });
}

function snapProgress(btn) {
  if (!progress || !heroToggle) return;
  const containerLeft = heroToggle.getBoundingClientRect().left;
  const btnRect = btn.getBoundingClientRect();
  progress.style.left  = (btnRect.left - containerLeft) + 'px';
  progress.style.width = btnRect.width + 'px';
}

if (allImgs.every(Boolean) && allBtns.every(Boolean) && progress && heroContainer && heroPreviewStatus) {
  let currentMode = 'annotate';

  const switchTo = (mode, animate = true) => {
    if (mode === currentMode && animate) return;
    currentMode = mode;

    allImgs.forEach((img, i) => {
      const active = Object.keys(heroImages)[i] === mode;
      img.classList.toggle('active', active);
      img.hidden = !active;
    });
    allBtns.forEach((btn, i) => {
      const active = Object.keys(heroButtons)[i] === mode;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', String(active));
    });

    snapProgress(heroButtons[mode]);
    heroContainer.setAttribute('aria-label', `Preview of SimplShot in ${mode} mode`);
    heroPreviewStatus.textContent = `Preview showing ${mode} mode.`;
  };

  // Set initial state
  heroImages.annotate.hidden = false;
  heroImages.edit.hidden = true;
  heroImages.view.hidden = true;

  // Apply correct sources on load and whenever system theme changes
  updateImgSources();
  darkModeQuery.addEventListener('change', updateImgSources);

  // Position indicator without animation on first paint, then enable transitions
  progress.style.transition = 'none';
  requestAnimationFrame(() => {
    switchTo('annotate', false);
    requestAnimationFrame(() => {
      progress.style.transition = '';
    });
  });

  Object.entries(heroButtons).forEach(([mode, btn]) => {
    btn.addEventListener('click', () => switchTo(mode));
  });

  // Reposition on resize in case layout shifts
  window.addEventListener('resize', () => snapProgress(heroButtons[currentMode]), { passive: true });
}

// 6. Auto-update download links from the latest GitHub release
fetch('https://api.github.com/repos/atlemo/SimplShot-App/releases/latest', {
  headers: { Accept: 'application/vnd.github+json' }
})
  .then(r => r.ok ? r.json() : Promise.reject())
  .then(data => {
    const tag = data.tag_name;
    if (!tag) return;
    const url = `https://github.com/atlemo/SimplShot-App/releases/download/${tag}/SimplShot.dmg`;
    document.querySelectorAll('[data-download]').forEach(el => { el.href = url; });
  })
  .catch(() => {});

// 7. Smooth anchor scroll (offset for sticky nav height)
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
