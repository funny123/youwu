const itemForm = document.getElementById('item-form');
const imageInput = itemForm.elements.image;
const sizeError = document.getElementById('upload-size-error');
const uploadStatus = document.getElementById('upload-status');
const limitMiB = Number(itemForm.dataset.uploadMaxMib);
const limit = limitMiB * 1024 * 1024;
const photoThreshold = 1024 * 1024;
const maxPhotoEdge = 1920;
let preparing = false;
let preparedImages = null;

async function compressPhoto(file) {
  if (file.size <= photoThreshold || !/\.(jpe?g|png|webp)$/i.test(file.name)) return file;
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    const scale = Math.min(1, maxPhotoEdge / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const context = canvas.getContext('2d', { alpha: false });
    context.fillStyle = '#fff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.82));
    if (!blob || blob.type !== 'image/jpeg' || blob.size >= file.size) return file;
    return new File([blob], file.name.replace(/\.[^.]+$/, '.jpg'), { type: blob.type });
  } catch {
    return file;
  } finally {
    URL.revokeObjectURL(url);
  }
}

function validateUploadSize(photos) {
  const files = [...photos, ...itemForm.elements.video.files];
  const total = files.reduce((sum, file) => sum + file.size, 0);
  const tooLarge = total >= limit;
  sizeError.hidden = !tooLarge;
  sizeError.textContent = tooLarge
    ? `本次文件合计 ${(total / 1024 / 1024).toFixed(1)} MiB，请减少照片或压缩视频，合计需低于 ${limitMiB} MiB。`
    : '';
  return !tooLarge;
}

itemForm.addEventListener('change', () => {
  sizeError.hidden = true;
  uploadStatus.textContent = '';
});

itemForm.addEventListener('formdata', event => {
  if (!preparedImages) return;
  event.formData.delete('image');
  for (const file of preparedImages) event.formData.append('image', file);
});

itemForm.addEventListener('submit', async event => {
  if (preparedImages) return;
  event.preventDefault();
  if (preparing) return;

  preparing = true;
  const submitter = event.submitter;
  const originalPhotos = [...imageInput.files];
  uploadStatus.textContent = '正在准备照片…';
  try {
    const photos = [];
    const supportsFormDataEvent = typeof FormDataEvent === 'function';
    for (const file of originalPhotos) {
      photos.push(supportsFormDataEvent ? await compressPhoto(file) : file);
    }
    if (originalPhotos.length !== imageInput.files.length ||
        originalPhotos.some((file, index) => file !== imageInput.files[index])) {
      uploadStatus.textContent = '照片选择已变更，请重新提交。';
      return;
    }
    if (!validateUploadSize(photos)) {
      uploadStatus.textContent = '';
      sizeError.scrollIntoView({ block: 'nearest' });
      return;
    }
    preparedImages = photos;
    uploadStatus.textContent = '正在上传，请保持页面打开…';
    itemForm.requestSubmit(submitter || undefined);
  } finally {
    preparedImages = null;
    preparing = false;
  }
});
