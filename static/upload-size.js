const itemForm = document.getElementById('item-form');
const sizeError = document.getElementById('upload-size-error');
const limitMiB = Number(itemForm.dataset.uploadMaxMib);
const limit = limitMiB * 1024 * 1024;

function validateUploadSize() {
  let total = 0;
  for (const input of itemForm.querySelectorAll('input[type="file"]')) {
    for (const file of input.files) total += file.size;
  }
  const tooLarge = total >= limit;
  sizeError.hidden = !tooLarge;
  sizeError.textContent = tooLarge
    ? `已选择 ${(total / 1024 / 1024).toFixed(1)} MiB，超过单次上传可用空间。请减少照片或压缩视频，合计需低于 ${limitMiB} MiB。`
    : '';
  return !tooLarge;
}

itemForm.addEventListener('change', validateUploadSize);
itemForm.addEventListener('submit', event => {
  if (!validateUploadSize()) {
    event.preventDefault();
    sizeError.scrollIntoView({ block: 'nearest' });
  }
});
