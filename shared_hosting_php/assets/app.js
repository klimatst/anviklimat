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

