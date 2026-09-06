const nav = document.querySelector('[data-nav]');
const menuToggle = document.querySelector('.menu-toggle');
const mainNav = document.querySelector('#main-nav');

menuToggle?.addEventListener('click', () => {
  const open = mainNav.classList.toggle('is-open');
  menuToggle.setAttribute('aria-expanded', String(open));
});

mainNav?.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => {
    mainNav.classList.remove('is-open');
    menuToggle?.setAttribute('aria-expanded', 'false');
  });
});

const preview = document.querySelector('[data-demo]');
document.querySelectorAll('[data-preview]').forEach((button) => {
  button.addEventListener('click', () => {
    const mode = button.dataset.preview;
    preview?.setAttribute('data-demo', mode);
    document.querySelectorAll('[data-preview]').forEach((item) => {
      item.classList.toggle('is-active', item === button);
    });
  });
});

const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.13 });

document.querySelectorAll('.reveal').forEach((element) => revealObserver.observe(element));

document.querySelectorAll('[data-copy]').forEach((button) => {
  button.addEventListener('click', async () => {
    const value = button.dataset.copy;
    try {
      await navigator.clipboard.writeText(value);
      button.textContent = '已复制 ✓';
    } catch {
      button.textContent = value;
    }
    window.setTimeout(() => { button.textContent = '复制命令'; }, 1800);
  });
});

window.addEventListener('scroll', () => {
  nav?.classList.toggle('is-scrolled', window.scrollY > 10);
}, { passive: true });
