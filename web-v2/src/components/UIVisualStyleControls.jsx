import { useState } from 'react'
import { visualPreset } from '../lib/uiVisualStyle'
const states = [['normal','Bình thường'],['hover','Rê chuột'],['pressed','Đang nhấn'],['selected','Đang chọn'],['focus','Focus bàn phím']]
export default function UIVisualStyleControls({ value = {}, onChange }) {
  const [state, setState] = useState('normal')
  const patch = (key, next) => onChange({ ...value, [key]: next === '' ? undefined : next })
  const patchState = (key, next) => patch(state, { ...value[state], [key]: next === '' ? undefined : next })
  return <fieldset className="layout-align-tools"><legend>Phong cách & hiệu ứng</legend>
    <small>Áp dụng cho thành phần đã chọn trên website. Xem trước ngay; bấm Lưu cho tất cả để áp dụng.</small>
    <div className="layout-designer-actions"><button type="button" onClick={() => onChange(structuredClone(visualPreset))}>Mẫu xanh 3D</button><button type="button" onClick={() => onChange(undefined)}>Xóa hiệu ứng</button></div>
    <label>Trạng thái<select value={state} onChange={event => setState(event.target.value)}>{states.map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    {[['background','Màu nền'],['gradient','Màu cuối gradient'],['text','Màu chữ'],['border','Màu viền']].map(([key,label]) => <div className="layout-color-control" key={key}><label>{label}<input type="color" aria-label={label} value={value[state]?.[key] || '#ffffff'} onChange={event => patchState(key,event.target.value)}/></label><button type="button" aria-label={`Mặc định ${label}`} onClick={() => patchState(key,'')}>↺</button></div>)}
    <label>Bóng đổ<select value={value[state]?.shadow || ''} onChange={event => patchState('shadow',event.target.value)}>{[['','Mặc định'],['none','Không bóng'],['soft','Nhẹ'],['medium','Vừa'],['strong','Đậm'],['inset','Lõm'],['raised','Nổi 3D']].map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <small>Gradient cần chọn cả màu nền và màu cuối. Các thông số dưới đây dùng chung cho các trạng thái.</small>
    {[['radius','Bo góc (px)',0,40],['border_width','Dày viền (px)',1,6],['padding_x','Đệm ngang (px)',0,40],['padding_y','Đệm dọc (px)',0,32],['font_size','Cỡ chữ (px)',12,32],['glass_blur','Kính mờ (px)',0,20],['glass_opacity','Độ đậm nền (%)',20,100],['depth','Độ nổi 3D (px)',0,8],['hover_lift','Nâng khi rê (px)',0,6],['press_sink','Lún khi nhấn (px)',0,6],['transition_ms','Chuyển động (ms)',0,600]].map(([key,label,min,max]) => <label key={key}>{label}<input type="number" min={min} max={max} placeholder="Mặc định" value={value[key] ?? ''} onChange={event => patch(key,event.target.value === '' ? '' : Number(event.target.value))}/></label>)}
    <label>Độ đậm chữ<select value={value.font_weight || ''} onChange={event => patch('font_weight',event.target.value ? Number(event.target.value) : '')}><option value="">Mặc định</option>{[400,500,600,700,800].map(n => <option key={n} value={n}>{n}</option>)}</select></label>
    <label>Phông chữ<select value={value.font_family || ''} onChange={event => patch('font_family',event.target.value)}>{[['','Mặc định'],['system','Hệ thống'],['segoe','Segoe UI'],['roboto','Roboto / Arial'],['serif','Georgia']].map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
  </fieldset>
}
