export const FACE_BATCH_LIMIT = 50
export const FACE_BATCH_BYTES = 100 * 1024 * 1024
export const FACE_STATUS = {
  invalid_filename: 'Tên file hoặc định dạng không hợp lệ',
  duplicate_filename: 'Nhiều file cùng tên nhân viên — chỉ giữ một ảnh',
  not_found: 'Không tìm thấy Tên nhân viên tương ứng',
  ambiguous: 'Tên nhân viên không duy nhất — cần kiểm tra tài khoản',
}

export function validateBatchFiles(files) {
  if (!files.length || files.length > FACE_BATCH_LIMIT) throw Error(`Chọn từ 1 đến ${FACE_BATCH_LIMIT} ảnh mỗi lần.`)
  if (files.reduce((total, file) => total + file.size, 0) > FACE_BATCH_BYTES) throw Error('Tổng ảnh gốc tối đa 100 MB mỗi lần.')
}

export async function prepareFacePhoto(file) {
  if (file.size > 20 * 1024 * 1024) throw Error('Ảnh gốc vượt quá 20 MB.')
  if (!/\.(jpe?g|png|webp)$/i.test(file.name)) throw Error('Chọn ảnh JPG, PNG hoặc WebP.')
  const url = URL.createObjectURL(file)
  try {
    const image = await new Promise((resolve, reject) => {
      const image = new Image()
      image.onload = () => resolve(image)
      image.onerror = () => reject(Error('Không đọc được ảnh.'))
      image.src = url
    })
    const { naturalWidth: width, naturalHeight: height } = image
    if (width < 160 || height < 160 || width > 6000 || height > 6000 || width * height > 24000000) throw Error('Ảnh cần từ 160 px đến 6000 px mỗi chiều, tối đa 24 megapixel.')
    // Preserve the complete image. Letterbox to 3:4 instead of automatically
    // cropping an employee's face. Operators may use the shared crop editor.
    const canvas = document.createElement('canvas')
    canvas.width = 900; canvas.height = 1200
    const ctx = canvas.getContext('2d')
    const scale = Math.min(canvas.width / width, canvas.height / height)
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(image, (canvas.width - width * scale) / 2, (canvas.height - height * scale) / 2, width * scale, height * scale)
    for (const quality of [0.88, 0.76, 0.64, 0.52]) {
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', quality))
      if (blob && blob.size <= 450 * 1024) return blob
    }
    throw Error('Ảnh chưa nén đủ nhỏ; hãy dùng Crop / Xoay / Nén để chỉnh lại.')
  } finally { URL.revokeObjectURL(url) }
}

export async function uploadFaceBatch(rows, upload, onResult, isActive = () => true) {
  // Sequential uploads avoid occupying a database connection for each file at
  // once. Each confirmed success stays saved if a later request fails.
  for (const row of rows.filter(row => row.selected && row.blob && row.state !== 'saved')) {
    if (!isActive()) break
    onResult(row.id, { state: 'uploading', message: 'Đang lưu…' })
    try {
      await upload(row)
      if (isActive()) onResult(row.id, { state: 'saved', selected: false, message: 'Đã lưu' })
    } catch (error) {
      if (isActive()) onResult(row.id, { state: 'error', message: error.message || 'Lưu thất bại. Có thể thử lại.' })
      if ([401, 403].includes(error.status)) break
    }
  }
}
