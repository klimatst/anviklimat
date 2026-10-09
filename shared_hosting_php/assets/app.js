document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('input[type="file"]').forEach(function (input) {
    input.addEventListener('change', function () {
      if (input.files && input.files[0]) {
        input.setAttribute('title', input.files[0].name);
      }
    });
  });
  document.querySelectorAll('textarea.content-editor').forEach(function (area) {
    var bar = document.createElement('div');
    bar.className = 'editor-tools';
    var actions = [
      ['Абзац', '<p>', '</p>'],
      ['Заголовок', '<h2>', '</h2>'],
      ['Жирный', '<strong>', '</strong>'],
      ['Курсив', '<em>', '</em>'],
      ['Список', '<ul>\n<li>', '</li>\n</ul>'],
      ['Ссылка', '<a href="https://">', '</a>']
    ];
    actions.forEach(function (action) {
      var button = document.createElement('button');
      button.type = 'button';
      button.textContent = action[0];
      button.addEventListener('click', function () {
        var start = area.selectionStart;
        var end = area.selectionEnd;
        var selected = area.value.slice(start, end) || 'Текст';
        var insertion = action[1] + selected + action[2];
        area.setRangeText(insertion, start, end, 'select');
        area.focus();
      });
      bar.appendChild(button);
    });
    area.parentNode.insertBefore(bar, area);
  });
});



/* Motion is opt-in at runtime; content remains visible if observers are unavailable. */
(function () {
  'use strict';
  var header = document.querySelector('.eco-header');
  if (header) {
    var updateHeader = function () {
      header.classList.toggle('is-scrolled', window.scrollY > 24);
    };
    updateHeader();
    window.addEventListener('scroll', updateHeader, { passive: true });
  }

  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var revealTargets = document.querySelectorAll(
    '.hero-content, .section-heading, .category-card, .product-card, .feature-card, .admin-panel, .metric-card, .stat-card, .engineering-workstream, .formula-item'
  );
  if (!reduceMotion && 'IntersectionObserver' in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-revealed');
          observer.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -36px 0px', threshold: 0.06 });

    Array.prototype.forEach.call(revealTargets, function (element, index) {
      if (element.closest('.eco-header')) return;
      element.setAttribute('data-reveal', '');
      element.style.setProperty('--reveal-delay', (index % 5) * 45 + 'ms');
      observer.observe(element);
    });
  }
})();
