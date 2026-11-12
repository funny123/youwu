const byId = id => document.getElementById(id);
const dialog = byId('dialog');
const detail = byId('detail');
let items = [];
let seller = {};
let catalogReady = false;
const html = value => String(value).replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
})[char]);
let selectedCategory = '全部';

function render() {
  if (!catalogReady) return;
  const query = byId('search').value.trim().toLowerCase();
  const matches = items.filter(item => (
    (selectedCategory === '全部' || item.category === selectedCategory) &&
    [item.name, item.category, item.description].some(text => text.toLowerCase().includes(query))
  ));
  byId('count').textContent = `共 ${matches.length} 件`;
  byId('grid').innerHTML = matches.map(item => `
    <article class="card">
      <button class="listing" data-id="${html(item.id)}">
        <div class="photo"><img src="${html(item.image)}" alt="" loading="lazy">${item.video ? '<span class="media-badge">▶ 视频</span>' : ''}</div>
        <div class="card-body"><span class="condition">${html(item.condition)}</span><h3>${html(item.name)}</h3>
          <div class="card-bottom"><strong>${item.price} VT</strong><span>查看详情 ↗</span></div>
        </div>
      </button>
    </article>`).join('') || (items.length ? '<p class="empty">没有找到符合条件的物品。</p>' : '<p class="empty">暂无在售商品。</p>');
}

function showContact() {
  detail.innerHTML = '<div class="dialog-body"><h2 id="dialog-title">联系卖家</h2><div id="channels"></div></div>';
  const channels = byId('channels');
  for (const [label, value, prefix] of [
    ['发送邮件', seller.email, 'mailto:'],
    ['打开 WhatsApp', seller.whatsapp, 'https://wa.me/'],
    ['打开 Telegram', seller.telegram, 'https://t.me/']
  ]) {
    if (!value) continue;
    const link = document.createElement('a');
    link.textContent = label + ' ↗';
    link.href = prefix + encodeURIComponent(value).replace(/%40/g, '@');
    if (prefix.startsWith('https://')) {
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
    }
    channels.append(link);
  }
  if (!channels.childElementCount) channels.textContent = '卖家暂未填写联系方式。';
  if (!dialog.open) dialog.showModal();
  else byId('close').focus();
}

function showItem(id) {
  const item = items.find(entry => entry.id === id);
  if (!item) return;
  detail.innerHTML = `
    <div class="detail-media"><img src="${html(item.image)}" alt="${html(item.name)}照片">${item.video ? `<video controls hidden playsinline preload="none" src="${html(item.video)}" poster="${html(item.image)}" aria-label="${html(item.name)}视频"></video>` : ''}</div>
    <div class="dialog-body">
      ${item.video ? `<div class="media-actions"><button class="pill" aria-pressed="true">照片</button><button class="pill" aria-pressed="false">视频</button></div>` : ''}
      <h2 id="dialog-title">${html(item.name)}</h2>
      <div class="detail-price"><strong>${item.price} VT</strong><span class="condition">${html(item.condition)}</span></div>
      <h3>物品介绍</h3><p>${html(item.description)}</p>
      ${item.notes ? `<h3>看货说明</h3><p>${html(item.notes)}</p>` : ''}
      <button class="primary" id="item-contact">联系卖家 ↗</button>
    </div>`;
  const video = detail.querySelector('video');
  const photo = detail.querySelector('img');
  const tabs = [...detail.querySelectorAll('.pill')];
  tabs.forEach((tab, index) => tab.addEventListener('click', () => {
    photo.hidden = index === 1;
    video.hidden = index === 0;
    if (video.hidden) video.pause();
    tabs.forEach((entry, position) => entry.setAttribute('aria-pressed', String(index === position)));
  }));
  byId('item-contact').addEventListener('click', showContact);
  dialog.showModal();
}

byId('categories').addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  selectedCategory = button.textContent;
  for (const entry of byId('categories').children) entry.setAttribute('aria-pressed', String(entry === button));
  render();
});
byId('grid').addEventListener('click', event => showItem(event.target.closest('[data-id]')?.dataset.id));
byId('search').addEventListener('input', render);
byId('contact').addEventListener('click', showContact);
byId('close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
dialog.addEventListener('close', () => { detail.replaceChildren(); });
fetch('/api/catalog').then(response => {
  if (!response.ok) throw new Error('Catalog request failed');
  return response.json();
}).then(catalog => {
  items = catalog.items;
  seller = catalog.seller;
  catalogReady = true;
  const categories = ['全部', ...new Set(items.map(item => item.category).filter(category => category !== '全部'))];
  byId('categories').innerHTML = categories.map(category =>
    `<button class="pill" aria-pressed="${category === selectedCategory}">${html(category)}</button>`
  ).join('');
  render();
}).catch(() => {
  byId('grid').innerHTML = '<p class="empty" role="alert">商品暂时无法加载，请刷新页面重试。</p>';
});
