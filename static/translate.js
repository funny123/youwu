const translateButton = document.getElementById('auto-translate');
const translationStatus = document.getElementById('translation-status');
const editForm = translateButton.form;

translateButton.addEventListener('click', async () => {
  const fields = ['name', 'description', 'notes'].filter(field =>
    editForm.elements[field].value.trim() && !editForm.elements[field + '_en'].value.trim()
  );
  translationStatus.hidden = false;
  if (!fields.length) {
    translationStatus.textContent = '请填写中文内容，并留出要自动填写的英文栏。';
    return;
  }

  const body = new URLSearchParams({ csrf: editForm.elements.csrf.value });
  for (const field of fields) body.set(field + '_en', editForm.elements[field].value.trim());
  translateButton.disabled = true;
  translationStatus.textContent = '正在翻译…';
  try {
    const response = await fetch(translateButton.dataset.url, { method: 'POST', body });
    const result = await response.json();
    if (!response.ok) {
      translationStatus.textContent = result.error || '翻译失败，请稍后重试。';
      return;
    }
    let applied = 0;
    for (const field of fields) {
      const key = field + '_en';
      const input = editForm.elements[key];
      if (!input.value.trim() && editForm.elements[field].value.trim() === body.get(key)) {
        input.value = result.translations[key];
        applied += 1;
      }
    }
    translationStatus.textContent = applied ? '已填写译文，请校对后保存。' : '表单内容已变更，请重新翻译。';
  } catch {
    translationStatus.textContent = '翻译失败，请稍后重试。';
  } finally {
    translateButton.disabled = false;
  }
});
