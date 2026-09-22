import fs from 'node:fs'
import path from 'node:path'
import { parse } from '@babel/parser'
import traverseModule from '@babel/traverse'
const traverse=traverseModule.default||traverseModule
const root=path.resolve(import.meta.dirname,'../src'),registry=JSON.parse(fs.readFileSync(path.resolve(root,'../../vera_ui_registry.json')))
for(const file of fs.readdirSync(root,{recursive:true}).filter(p=>p.endsWith('.jsx')&&!/LayoutDesigner|AppearanceSettingsPage|UiToolbar/.test(p))){
 const full=path.join(root,file),source=fs.readFileSync(full,'utf8'),edits=[]
 traverse(parse(source,{sourceType:'module',plugins:['jsx']}),{JSXElement(p){const el=p.node,op=el.openingElement;if(op.name.name!=='div')return;const key=op.attributes.find(a=>a.name?.name==='data-ui-key')?.value?.value;if(!registry[key]?.group)return;edits.push([op.name.start,op.name.end,'UiToolbar']);if(el.closingElement)edits.push([el.closingElement.name.start,el.closingElement.name.end,'UiToolbar'])}})
 if(!edits.length)continue
 const rel=path.relative(path.dirname(full),path.join(root,'components/UiToolbar')).replaceAll('\\','/')
 edits.push([0,0,`import UiToolbar from '${rel.startsWith('.')?rel:'./'+rel}'\n`])
 let next=source;for(const [start,end,text]of edits.sort((a,b)=>b[0]-a[0]))next=next.slice(0,start)+text+next.slice(end)
 fs.writeFileSync(full,next)
}
