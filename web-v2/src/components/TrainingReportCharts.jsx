import { formatVeraDate } from '../lib/veraDate'
import { evaluationCriteria, validTrainingScore } from '../lib/trainingReport'

const colors = ['#1f6149','#a77714','#3568a8','#a64f45','#7452a3','#31898a','#8a6b31']
function segments(items, value, point) {
  const result = []; let current = []
  items.forEach((item, index) => {
    if (value(item)) current.push(point(item, index))
    else if (current.length) { result.push(current.join(' ')); current = [] }
  })
  if (current.length) result.push(current.join(' '))
  return result
}

export function TrainingRadar({ values }) {
  const keys = ['craft', 'communication', 'attitude', 'conduct']
  if (!values || !keys.every(key => validTrainingScore(values[key]))) return <p className="training-empty">Chưa có đủ dữ liệu năng lực trong khoảng đã chọn.</p>
  const center = 110, radius = 65
  const point = (index, score = 5) => {
    const angle = -Math.PI / 2 + index * Math.PI / 2
    return `${center + Math.cos(angle) * radius * Number(score) / 5},${center + Math.sin(angle) * radius * Number(score) / 5}`
  }
  return <div className="training-radar"><svg viewBox="0 0 220 220" role="img" aria-label="Biểu đồ radar năng lực, thang điểm 1 đến 5">
    {[1, 2, 3, 4, 5].map(level => <polygon key={level} points={keys.map((_, i) => point(i, level)).join(' ')} className="radar-grid"/>)}
    <polygon points={keys.map((key, i) => point(i, values[key])).join(' ')} className="radar-score"/>
    <text x="110" y="26">Tay nghề {values.craft}/5</text><text x="182" y="106">Giao tiếp</text><text x="182" y="120">{values.communication}/5</text>
    <text x="110" y="198">Thái độ {values.attitude}/5</text><text x="35" y="106">Tác phong</text><text x="35" y="120">{values.conduct}/5</text>
  </svg><p className="center muted">{values.cycle_name || 'Kỳ đánh giá gần nhất trong khoảng đã chọn'}</p></div>
}

export function TrainingProgressChart({ points = [] }) {
  const entries = [...points].sort((a,b) => String(a.training_date).localeCompare(String(b.training_date)) || String(a.start_time).localeCompare(String(b.start_time)) || String(a.id).localeCompare(String(b.id)))
  if (!entries.some(item => validTrainingScore(item.skill_score, 6))) return <p className="training-empty">Chưa có dữ liệu kỹ năng trong khoảng đã chọn.</p>
  const width = 560, height = 210, left = 36, top = 20, bottom = 38
  const x = index => entries.length === 1 ? width / 2 : left + index * (width - 2 * left) / (entries.length - 1)
  const y = value => top + (6 - Number(value)) * (height - top - bottom) / 5
  return <div className="training-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Tiến độ kỹ năng theo buổi đào tạo, từ E đến A+">
    {['E','D','C','B','A','A+'].map((label, index) => <g key={label}><line x1={left} y1={y(index+1)} x2={width-left} y2={y(index+1)}/><text x="5" y={y(index+1)+4}>{label}</text></g>)}
    {segments(entries, item => validTrainingScore(item.skill_score, 6), (item,index) => `${x(index)},${y(item.skill_score)}`).map((segment,index) => <polyline key={index} points={segment}/>)}
    {entries.map((item,index) => validTrainingScore(item.skill_score,6) && <circle key={item.id} cx={x(index)} cy={y(item.skill_score)} r="4"><title>{formatVeraDate(item.training_date)} · {item.skill_grade}</title></circle>)}
    <text x={left} y={height-8}>{formatVeraDate(entries[0].training_date)}</text>{entries.length > 1 && <text x={width-left} y={height-8} textAnchor="end">{formatVeraDate(entries.at(-1).training_date)}</text>}
  </svg><p className="muted">{entries.length} buổi trong khoảng đã chọn · Điểm thiếu để trống.</p></div>
}

export function TrainingCriteriaChart({ history = [] }) {
  const entries = history.filter(item => item.type === 'comprehensive').sort((a,b) => String(a.date).localeCompare(String(b.date)) || String(a.id).localeCompare(String(b.id)))
  if (!entries.length) return <p className="training-empty">Chưa có đợt đánh giá tổng hợp trong khoảng đã chọn.</p>
  const width = 720, height = 260, left = 44, top = 24, bottom = 38
  const x = index => entries.length === 1 ? width / 2 : left + index * (width - 2*left) / (entries.length-1)
  const y = value => top + (5-Number(value)) * (height-top-bottom)/4
  const labelEvery = Math.max(1, Math.ceil(entries.length / 6))
  const missing = entries.some(item => evaluationCriteria.some(([key]) => !validTrainingScore(item.detail?.[key])))
  return <div className="criteria-history-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Biểu đồ các tiêu chí qua từng phiếu đánh giá, thang điểm 1 đến 5">
    {[1,2,3,4,5].map(score => <g key={score}><line x1={left} y1={y(score)} x2={width-left} y2={y(score)}/><text x="18" y={y(score)+4}>{score}/5</text></g>)}
    {evaluationCriteria.map(([key,label],criterion) => <g key={key}>
      {segments(entries, item => validTrainingScore(item.detail?.[key]), (item,index) => `${x(index)},${y(item.detail[key])}`).map((segment,index) => <polyline key={index} style={{stroke: colors[criterion]}} points={segment}/>)}
      {entries.map((item,index) => validTrainingScore(item.detail?.[key]) && <circle key={item.id} cx={x(index)} cy={y(item.detail[key])} r="4" fill={colors[criterion]}><title>{formatVeraDate(item.date)} · {item.title} · {label}: {item.detail[key]}/5</title></circle>)}
    </g>)}
    {entries.map((item,index) => (index % labelEvery === 0 || index === entries.length-1) && <text key={item.id} x={x(index)} y={height-10}>{formatVeraDate(item.date)}</text>)}
  </svg><div className="criteria-legend">{evaluationCriteria.map(([key,label],index) => <span key={key}><i style={{background:colors[index]}}/>{label}</span>)}</div>
    {missing && <p className="muted">Tiêu chí chưa có điểm được để trống trên biểu đồ.</p>}
  </div>
}
