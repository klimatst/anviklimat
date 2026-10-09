const app = document.querySelector('#app');
let data;
const asset = (name) => `/assets/images/catalog/${name}`;
const assetFromSource = (source, fallback = 'conditioners.jpg') => {
  const match = String(source || '').match(/(?:\/static\/images\/|\/assets\/images\/)(.+)$/);
  return match ? `/assets/images/${match[1]}` : asset(fallback);
};
const escapeHtml = (value = '') => String(value).replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[c]);
const productImage = (product) => product.image || asset('conditioners.jpg');
const money = value => new Intl.NumberFormat('ru-RU').format(Number(value || 0)) + ' ₽';
function route() { return location.hash.slice(1) || '/'; }
function categoryName(code) { return data.categories.find(c => c.code === code)?.title || 'Оборудование'; }
function navActive() { const page = route().split('?')[0]; document.querySelectorAll('.nav-link').forEach(a => a.classList.toggle('active', a.getAttribute('href') === `#${page}`)); }
function productCard(product) { return `<article class="product-card"><button data-product="${escapeHtml(product.sku)}"><div class="product-image"><img src="${escapeHtml(productImage(product))}" alt="" loading="lazy"><span class="badge">ДЕМО · КАТАЛОГ</span></div><div class="product-meta">${escapeHtml(product.brand || 'Оборудование')}</div><h3>${escapeHtml(product.model)}</h3><p class="card-description">${escapeHtml(product.description || '')}</p><div class="product-bottom"><strong>${money(product.sale_price)}</strong><span>Подробнее ↗</span></div></button></article>`; }
function home() {
  const featured = data.products.slice(0, 4);
  const categoryFallbacks = ['conditioners.jpg', 'vrv-vrf.jpg', 'ventilation.jpg', 'materials.jpg'];
  app.innerHTML = `<section class="hero local-hero"><div class="hero-photo"></div><div class="wrap hero-content"><p class="eyebrow">ПРОЕКТИРОВАНИЕ · ПОСТАВКА · МОНТАЖ</p><h1>Климатические системы<br><span>для вашего пространства</span></h1><p>Подбор оборудования и инженерные решения для дома и бизнеса.</p><div class="hero-actions"><a class="button" href="#/catalog">Открыть каталог <span>↗</span></a><a class="button button-ghost" href="#/contacts">Заказать консультацию</a></div><p class="local-note">Автономный просмотр репозитория. Цены и товары здесь демонстрационные, не для продажи.</p></div></section><section class="section wrap"><div class="section-heading"><div><p class="eyebrow">ОБОРУДОВАНИЕ</p><h2>Системы для климата</h2></div><a class="text-link" href="#/catalog">Весь каталог ↗</a></div><div class="category-grid">${data.categories.filter(c => !c.parent_code).slice(0,4).map((c, i) => `<a class="category-card" href="#/catalog?category=${encodeURIComponent(c.code)}"><img src="${escapeHtml(assetFromSource(c.image_url, categoryFallbacks[i]))}" alt="" loading="lazy"><span class="category-shade"></span><span class="category-info"><small>КАТАЛОГ</small><strong>${escapeHtml(c.title)}</strong><i>Открыть раздел ↗</i></span></a>`).join('')}</div></section><section class="section section-dark"><div class="wrap"><div class="section-heading"><div><p class="eyebrow">ВЫБОР РЕДАКТОРА</p><h2>Популярное оборудование</h2></div></div><div class="product-grid">${featured.map(productCard).join('')}</div></div></section>`;
}
function catalog() {
  const params = new URLSearchParams(route().split('?')[1]); const selected = params.get('category') || '';
  app.innerHTML = `<section class="page-hero"><div class="wrap"><p class="eyebrow">КЛИМАТ / ОБОРУДОВАНИЕ</p><h1>Каталог систем</h1><p>Подберите оборудование по разделу или найдите нужную модель.</p></div></section><section class="section wrap"><div class="catalog-filters"><input id="search" placeholder="Модель, бренд или назначение" aria-label="Поиск по каталогу"><select id="category" aria-label="Категория"><option value="">Все разделы</option>${data.categories.filter(c => !c.parent_code).map(c => `<option value="${escapeHtml(c.code)}" ${selected === c.code ? 'selected':''}>${escapeHtml(c.title)}</option>`).join('')}</select></div><div class="result-line"><span id="result-title">Все товары</span><span id="result-count"></span></div><div class="product-grid" id="products"></div></section>`;
  const search = document.querySelector('#search');
  const categorySelect = document.querySelector('#category');
  const render = () => {
    const query = search.value.toLowerCase().trim(); const category = categorySelect.value;
    const products = data.products.filter(p => (!query || `${p.model} ${p.brand} ${p.description}`.toLowerCase().includes(query)) && (!category || p.category_code === category || p.subcategory_code === category));
    document.querySelector('#products').innerHTML = products.map(productCard).join('') || '<div class="empty-state">Ничего не найдено.</div>';
    document.querySelector('#result-title').textContent = category ? categoryName(category) : 'Все товары';
    document.querySelector('#result-count').textContent = `${products.length} позиций`;
    bindProductCards();
  };
  search.addEventListener('input', render); categorySelect.addEventListener('change', render); render();
}
function details(sku) {
  const p = data.products.find(item => item.sku === sku);
  if (!p) return catalog();
  const specs = (p.specifications || []).map(s => `<div><dt>${escapeHtml(s[0])}</dt><dd>${escapeHtml(s[1])} ${escapeHtml(s[2] || '')}</dd></div>`).join('');
  app.innerHTML = `<section class="section wrap product-detail"><div><a class="detail-back" href="#/catalog">← Вернуться в каталог</a><div class="detail-image"><img src="${escapeHtml(productImage(p))}" alt="${escapeHtml(p.model)}"></div></div><div class="detail-info"><p class="eyebrow">${escapeHtml(categoryName(p.category_code))} / ${escapeHtml(p.brand)}</p><h1>${escapeHtml(p.model)}</h1><div class="notice warning">Демонстрационный товар: цена и параметры приведены для локальной проверки каталога.</div><p class="detail-copy">${escapeHtml(p.description)}</p><div class="detail-price">${money(p.sale_price)}</div><a class="button" href="#/contacts">Уточнить наличие <span>↗</span></a><h3 class="spec-heading">Характеристики</h3><dl class="spec-list">${specs}</dl></div></section>`;
}
function calculator() {
  app.innerHTML = `<section class="page-hero"><div class="wrap"><p class="eyebrow">ИНЖЕНЕРНЫЕ ИНСТРУМЕНТЫ</p><h1>Предварительный расчёт</h1><p>Оцените ориентировочную холодопроизводительность для помещения.</p></div></section><section class="section wrap calc-layout"><div class="calc-card"><p class="eyebrow">КОНДИЦИОНИРОВАНИЕ</p><h2>Нагрузка помещения</h2><form id="calculator"><label>Площадь помещения, м²<input name="area" type="number" value="25" min="1" max="10000" required></label><label>Высота потолка, м<input name="height" type="number" value="2.7" step=".1" min="2" max="20" required></label><label>Количество людей<input name="people" type="number" value="2" min="0" max="1000" required></label><label class="check-label"><input name="sun" type="checkbox"> Солнечная сторона или большие окна</label><button class="button">Рассчитать <span>↗</span></button></form></div><div class="calc-result" id="calculation" aria-live="polite"><div class="result-orbit">kW</div><p>Введите параметры комнаты, чтобы получить предварительную оценку.</p></div></section>`;
  document.querySelector('#calculator').addEventListener('submit', event => {
    event.preventDefault(); const f = new FormData(event.currentTarget);
    const area = Number(f.get('area')); const height = Number(f.get('height')); const people = Number(f.get('people'));
    if (!(area > 0) || !(height >= 2) || people < 0) return;
    const kw = area * .1 * (height / 2.7) * (f.get('sun') ? 1.15 : 1) + people * .1;
    document.querySelector('#calculation').innerHTML = `<p class="eyebrow">ОРИЕНТИРОВОЧНЫЙ РЕЗУЛЬТАТ</p><strong>${kw.toFixed(1).replace('.', ',')} <small>кВт</small></strong><p>Упрощённая оценка для демонстрации интерфейса, не инженерный расчёт. Для подбора оборудования нужна теплотехническая оценка.</p>`;
  });
}
function contacts() {
  app.innerHTML = `<section class="page-hero"><div class="wrap"><p class="eyebrow">КОНСУЛЬТАЦИЯ / СЕРВИС</p><h1>Обсудим вашу задачу</h1><p>В локальном режиме заявка сохранится только на этом компьютере.</p></div></section><section class="section wrap contact-layout"><div class="contact-details"><p class="eyebrow">НА СВЯЗИ</p><h2>Ответим и подскажем следующий шаг</h2><p class="contact-big">+7 (000) 000-00-00</p><p>info@example.ru</p><p class="local-note">Контакты выше — заглушки для предварительного просмотра.</p></div><form class="contact-form" id="lead-form"><label>Как к вам обращаться<input name="name" maxlength="160" required></label><label>Телефон<input name="phone" maxlength="80" required></label><label>Электронная почта<input name="email" type="email" maxlength="200"></label><label>Что нужно сделать?<textarea name="message" rows="5" maxlength="4000"></textarea></label><button class="button">Сохранить локальную заявку <span>↗</span></button><p class="contact-result" id="lead-result" aria-live="polite"></p></form></section>`;
  document.querySelector('#lead-form').addEventListener('submit', async event => {
    event.preventDefault(); const result = document.querySelector('#lead-result'); const button = event.currentTarget.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch('/api/leads', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
      const body = await response.json(); if (!response.ok) throw new Error(body.error);
      result.textContent = 'Заявка сохранена локально.'; event.currentTarget.reset();
    } catch (error) { result.className = 'contact-result error'; result.textContent = error.message || 'Не удалось сохранить заявку.'; }
    finally { button.disabled = false; }
  });
}
function bindProductCards() {
  document.querySelectorAll('[data-product]').forEach(button => button.addEventListener('click', () => { location.hash = `/product?sku=${encodeURIComponent(button.dataset.product)}`; }));
}
function render() {
  const [page] = route().split('?');
  if (page === '/catalog') catalog();
  else if (page === '/product') details(new URLSearchParams(route().split('?')[1]).get('sku'));
  else if (page === '/calculator') calculator();
  else if (page === '/contacts') contacts();
  else home();
  navActive(); bindProductCards();
}
fetch('/api/catalog').then(response => { if (!response.ok) throw new Error('catalog'); return response.json(); }).then(value => { data = value; render(); }).catch(() => {
  app.innerHTML = '<div class="wrap section"><h1>Не удалось загрузить локальные данные.</h1><p>Проверьте адрес <a href="/api/sync">/api/sync</a> и окно сервера.</p></div>';
});
window.addEventListener('hashchange', render);
const repositoryEvents = new EventSource('/events');
repositoryEvents.addEventListener('repository-update', () => location.reload());
