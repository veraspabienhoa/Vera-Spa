// Run when adding controls. Existing data-ui-key values are permanent identities.
import fs from 'node:fs'
import path from 'node:path'
import { createHash } from 'node:crypto'
import { parse } from '@babel/parser'
import traverseModule from '@babel/traverse'
const traverse = traverseModule.default || traverseModule
const root=path.resolve(import.meta.dirname,'../src')
const registryPath=path.resolve(root,'../../vera_ui_registry.json')
const registry=fs.existsSync(registryPath)?JSON.parse(fs.readFileSync(registryPath,'utf8')):{}
const files=fs.readdirSync(root,{recursive:true}).filter(p=>p.endsWith('.jsx')&&!/^App\.jsx$|LoginPage|LayoutDesigner|AppearanceSettingsPage|UiCustomText|UiToolbar|UICustomization/.test(p))
for(const file of files){
 const full=path.join(root,file),source=fs.readFileSync(full,'utf8'),edits=[]
 let labels=false
 const ast=parse(source,{sourceType:'module',plugins:['jsx']})
 traverse(ast,{JSXElement(p){
  const el=p.node,op=el.openingElement,tag=op.name.name
  if(!['button','a','div','section','table','th'].includes(tag))return
  const attr=name=>op.attributes.find(a=>a.name?.name===name)
  const classes=attr('className')?.value?.value||''
  const group=/toolbar|tabs|nav-list|actions|filters/.test(classes)||attr('role')?.value?.value==='tablist'
  if(tag==='div'&&!group&&!/panel|card|heading/.test(classes))return
  const existing=attr('data-ui-key')?.value?.value
  const key=existing||`u-${createHash('sha256').update(file+':'+op.start).digest('hex').slice(0,12)}`
  if(!existing)edits.push([op.name.end,op.name.end,` data-ui-key="${key}"`])
  const texts=el.children.filter(n=>n.type==='JSXText'&&n.value.trim())
  const dynamic=el.children.some(n=>n.type==='JSXExpressionContainer')
  const label=['button','a','th'].includes(tag)&&texts.length===1&&!dynamic?texts[0].value.trim().replace(/\s+/g,' '):null
  const old=registry[key]||{}
  registry[key]={...old,file,tag,group, label:old.label||label,locked:old.locked||!!(label&&/^(Đóng|Hủy|Đăng xuất|Lưu)(\s|$)/i.test(label))}
  if(label&&!el.children.some(n=>n.openingElement?.name?.name==='UiCustomText')){
   edits.push([texts[0].start,texts[0].end,`<UiCustomText uiKey="${key}">${texts[0].value}</UiCustomText>`]);labels=true
  }
 }})
 if(labels&&!source.includes("import UiCustomText from")){
  const rel=path.relative(path.dirname(full),path.join(root,'components/UiCustomText')).replaceAll('\\','/')
  edits.push([0,0,`import UiCustomText from '${rel.startsWith('.')?rel:'./'+rel}'\n`])
 }
 let next=source
 for(const [start,end,text]of edits.sort((a,b)=>b[0]-a[0]))next=next.slice(0,start)+text+next.slice(end)
 if(next!==source)fs.writeFileSync(full,next)
}
fs.writeFileSync(registryPath,JSON.stringify(registry,null,2)+'\n')
