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



/* Accessible responsive navigation and lightweight UI polish */
document.addEventListener('DOMContentLoaded', function () {
  var nav = document.querySelector('.main-nav');
  var navInner = nav && nav.querySelector('.nav-inner');
  if (nav && navInner) {
    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'ke-mobile-toggle';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-controls', 'ke-primary-navigation');
    toggle.innerHTML = '<span>Меню сайта</span><span aria-hidden="true">＋</span>';
    navInner.id = 'ke-primary-navigation';
    nav.insertBefore(toggle, navInner);
    toggle.addEventListener('click', function () {
      var opened = nav.classList.toggle('ke-nav-open');
      toggle.setAttribute('aria-expanded', String(opened));
      toggle.lastElementChild.textContent = opened ? '−' : '＋';
    });
    nav.querySelectorAll('.eco-menu-group > .nav-link').forEach(function (link) {
      link.addEventListener('click', function (event) {
        if (window.matchMedia('(max-width: 760px)').matches) {
          var group = link.closest('.eco-menu-group');
          if (group && group.querySelector('.eco-dropdown')) {
            event.preventDefault();
            var opened = group.classList.toggle('ke-submenu-open');
            link.setAttribute('aria-expanded', String(opened));
          }
        }
      });
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && nav.classList.contains('ke-nav-open')) {
        nav.classList.remove('ke-nav-open');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.lastElementChild.textContent = '＋';
        toggle.focus();
      }
    });
  }

  document.querySelectorAll('a[href^="#"]').forEach(function (link) {
    link.addEventListener('click', function (event) {
      var target = document.querySelector(link.getAttribute('href'));
      if (target) {
        event.preventDefault();
        target.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
      }
    });
  });

  document.querySelectorAll('input[type="search"]').forEach(function (input) {
    input.setAttribute('autocomplete', 'off');
  });
});
