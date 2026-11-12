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

const english = new Map(Object.entries({
  '闲置商品': 'Items for Sale', '联系卖家': 'Contact seller', '搜索物品': 'Search items',
  '关闭': 'Close', '物品分类': 'Categories', '正在加载商品…': 'Loading items…',
  '查看详情': 'View details', '视频': 'Video', '照片': 'Photo', '查看照片': 'View photo',
  '没有找到符合条件的物品。': 'No matching items.', '暂无在售商品。': 'No items for sale.',
  '商品暂时无法加载，请刷新页面重试。': 'Unable to load items. Refresh to try again.',
  '发送邮件': 'Send email', '打开 WhatsApp': 'Open WhatsApp', '打开 Telegram': 'Open Telegram',
  '卖家暂未填写联系方式。': 'No contact details available.', '物品介绍': 'Description', '看货说明': 'Viewing and pickup',
  '购买日期': 'Purchase date', '全部': 'All', '家居家具': 'Home & Furniture', '数码电器': 'Electronics & Appliances',
  '运动户外': 'Sports & Outdoors', '服饰鞋包': 'Clothing & Accessories', '母婴用品': 'Baby & Kids',
  '图书文具': 'Books & Stationery', '交通工具': 'Vehicles', '其他': 'Other',
  '全新未使用': 'New and unused', '几乎全新': 'Like new', '外观良好': 'Good condition',
  '轻微使用痕迹': 'Light wear', '正常使用痕迹': 'Normal wear',
  '明显使用痕迹': 'Visible wear', '需维修': 'Needs repair'
}));
let language = new URLSearchParams(location.search).get('lang') === 'en' ? 'en' : 'zh-CN';
let catalogFailed = false;
const t = text => language === 'en' ? (english.get(text) ?? text) : text;
const localized = (item, field) => language === 'en' && item[field + '_en'] ? item[field + '_en'] : item[field];

function productTitle(item) {
  const englishName = item.name_en?.trim();
  if (!englishName || item.name.toLowerCase().includes(englishName.toLowerCase())) {
    return html(item.name);
  }
  return `${html(item.name)} <span class="english-name" lang="en">${html(englishName)}</span>`;
}

function purchaseDateLabel(item) {
  if (!item.purchase_date) return '';
  const value = html(item.purchase_date);
  return `<span class="condition purchase-date">${t('购买日期')} <time datetime="${value}">${value}</time></span>`;
}

function renderLanguage() {
  document.documentElement.lang = language;
  byId('contact').textContent = t('联系卖家') + ' ↗';
  byId('search').placeholder = t('搜索物品');
  byId('search').setAttribute('aria-label', t('搜索物品'));
  byId('categories').setAttribute('aria-label', t('物品分类'));
  byId('close').setAttribute('aria-label', t('关闭'));
  byId('language').lang = language === 'en' ? 'zh-CN' : 'en';
  byId('language').textContent = language === 'en' ? '中文' : 'English';
  if (!catalogReady) {
    const message = byId('grid').querySelector('p');
    message.textContent = t(catalogFailed ? '商品暂时无法加载，请刷新页面重试。' : '正在加载商品…');
    if (catalogFailed) message.setAttribute('role', 'alert');
    return;
  }
  const categories = ['全部', ...new Set(items.map(item => item.category).filter(category => category !== '全部'))];
  byId('categories').innerHTML = categories.map(category =>
    `<button class="pill" data-category="${html(category)}" aria-pressed="${category === selectedCategory}">${html(t(category))}</button>`
  ).join('');
  render();
}

function render() {
  if (!catalogReady) return;
  const query = byId('search').value.trim().toLowerCase();
  const matches = items.filter(item => (
    (selectedCategory === '全部' || item.category === selectedCategory) &&
    [item.name, item.name_en, item.category, t(item.category), item.description, item.description_en]
      .some(text => text?.toLowerCase().includes(query))
  ));
  byId('count').textContent = language === 'en'
    ? `${matches.length} ${matches.length === 1 ? 'item' : 'items'}` : `共 ${matches.length} 件`;
  byId('grid').innerHTML = matches.map(item => `
    <article class="card">
      <button class="listing" data-id="${html(item.id)}">
        <div class="photo"><img src="${html(item.image)}" alt="" loading="lazy">${item.video ? `<span class="media-badge">▶ ${t('视频')}</span>` : ''}</div>
        <div class="card-body"><span class="condition">${html(t(item.condition))}</span>${purchaseDateLabel(item)}<h3>${productTitle(item)}</h3>
          <div class="card-bottom"><strong>${item.price} VT</strong><span>${t('查看详情')} ↗</span></div>
        </div>
      </button>
    </article>`).join('') || (items.length ? `<p class="empty">${t('没有找到符合条件的物品。')}</p>` : `<p class="empty">${t('暂无在售商品。')}</p>`);
}

function showContact() {
  detail.innerHTML = `<div class="dialog-body"><h2 id="dialog-title">${t('联系卖家')}</h2><div id="channels"></div></div>`;
  const channels = byId('channels');
  for (const [label, value, prefix] of [
    ['发送邮件', seller.email, 'mailto:'],
    ['打开 WhatsApp', seller.whatsapp, 'https://wa.me/'],
    ['打开 Telegram', seller.telegram, 'https://t.me/']
  ]) {
    if (!value) continue;
    const link = document.createElement('a');
    link.textContent = t(label) + ' ↗';
    link.href = prefix + encodeURIComponent(value).replace(/%40/g, '@');
    if (prefix.startsWith('https://')) {
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
    }
    channels.append(link);
  }
  if (!channels.childElementCount) channels.textContent = t('卖家暂未填写联系方式。');
  if (!dialog.open) dialog.showModal();
  else byId('close').focus();
}

function showItem(id) {
  const item = items.find(entry => entry.id === id);
  if (!item) return;
  detail.innerHTML = `
    <div class="detail-media"><img src="${html(item.image)}" alt="${html(localized(item, 'name'))} ${t('照片')}">${item.video ? `<video controls hidden playsinline preload="none" src="${html(item.video)}" poster="${html(item.image)}" aria-label="${html(localized(item, 'name'))} ${t('视频')}"></video>` : ''}</div>
    <div class="dialog-body">
      ${item.images.length > 1 || item.video ? `<div class="media-actions">
        ${item.images.map((url, index) => `<button type="button" class="thumbnail" data-photo="${index}" aria-label="${t('查看照片')} ${index + 1}" aria-pressed="${index === 0}"><img src="${html(url)}" alt=""></button>`).join('')}
        ${item.video ? `<button type="button" class="pill" data-video aria-pressed="false">${t('视频')}</button>` : ''}
      </div>` : ''}
      <h2 id="dialog-title">${productTitle(item)}</h2>
      <div class="detail-price"><strong>${item.price} VT</strong><span class="condition">${html(t(item.condition))}</span></div>
      ${purchaseDateLabel(item)}
      <h3>${t('物品介绍')}</h3><p>${html(localized(item, 'description'))}</p>
      ${localized(item, 'notes') ? `<h3>${t('看货说明')}</h3><p>${html(localized(item, 'notes'))}</p>` : ''}
      <button class="primary" id="item-contact">${t('联系卖家')} ↗</button>
    </div>`;
  const video = detail.querySelector('video');
  const photo = detail.querySelector('img');
  const tabs = [...detail.querySelectorAll('.media-actions button')];
  tabs.forEach(tab => tab.addEventListener('click', () => {
    const showVideo = tab.hasAttribute('data-video');
    photo.hidden = showVideo;
    if (!showVideo) photo.src = item.images[Number(tab.dataset.photo)];
    if (video) {
      video.hidden = !showVideo;
      if (!showVideo) video.pause();
    }
    tabs.forEach(entry => entry.setAttribute('aria-pressed', String(entry === tab)));
  }));
  byId('item-contact').addEventListener('click', showContact);
  dialog.showModal();
}

byId('categories').addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  selectedCategory = button.dataset.category;
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
  renderLanguage();
}).catch(() => {
  catalogFailed = true;
  renderLanguage();
});
byId('language').addEventListener('click', () => {
  language = language === 'en' ? 'zh-CN' : 'en';
  const url = new URL(location.href);
  url.searchParams.set('lang', language);
  history.replaceState(null, '', url);
  renderLanguage();
});
renderLanguage();
