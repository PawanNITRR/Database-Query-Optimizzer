// Two optional collapsed panels keep the main query flow small.
function textEl(tag, text, cls){const el=document.createElement(tag);el.textContent=text;if(cls)el.className=cls;return el}
async function api(path, data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const j=await r.json();if(!r.ok)throw Error(j.error);return j}
const structurePanel=document.createElement('details');structurePanel.className='card';
const questionHint=textEl('p','You can also ask about monthly sales, products, or payments. These questions use the three demo report templates.','note');
$('query').after(questionHint);
structurePanel.append(textEl('summary','Structural recommendations & sandbox'));
structurePanel.append(textEl('p','Analyze the query using metadata only, then test an RL-selected strategy in a separate synthetic PostgreSQL sandbox. Source tables are never altered.','note'));
const analyzeButton=textEl('button','Analyze structure');
const simulateButton=textEl('button','Simulate proposal');simulateButton.hidden=true;
const approveButton=textEl('button','Approve & download review plan');approveButton.hidden=true;
const toolbar=document.createElement('div');toolbar.className='demo-buttons';toolbar.append(analyzeButton,simulateButton,approveButton);
const structureOutput=textEl('div','');structurePanel.append(toolbar,structureOutput);
$('results').after(structurePanel);
let proposalToken=null;
analyzeButton.onclick=async()=>{
  analyzeButton.disabled=true;simulateButton.hidden=true;approveButton.hidden=true;
  structureOutput.replaceChildren(textEl('p','Analyzing catalog metadata and plan…'));
  try{
    const data=await api('/api/advice',{query:$('query').value});proposalToken=data.token;
    structureOutput.replaceChildren(textEl('p','RL recommends: '+data.action+'. '+data.decision),textEl('p',data.mode,'note'));
    const h=data.historical_evidence;
    structureOutput.append(textEl('p','Historical evidence: '+h.structurally_similar_logs+' structurally similar logs'+(h.median_logged_duration_ms===null?'':', median recorded runtime '+h.median_logged_duration_ms.toFixed(3)+' ms')+'. '+h.scope,'note'));
    data.gnn_explanations.forEach(n=>structureOutput.append(textEl('p',n.reason,'note')));
    data.recommendations.forEach(n=>{
      structureOutput.append(textEl('h3',n.kind.toUpperCase()+' · '+n.table+(n.already_present?' · already indexed':'')),textEl('p',n.reason,'note'),textEl('pre',n.ddl));
    });
    if(!data.recommendations.length)structureOutput.append(textEl('p','No structural recommendation for this query.'));
    simulateButton.hidden=false;
  }catch(e){structureOutput.replaceChildren(textEl('p',e.message));}
  finally{analyzeButton.disabled=false;}
};
simulateButton.onclick=async()=>{
  simulateButton.disabled=true;
  try{
    const data=await api('/api/simulate',{token:proposalToken}),s=data.simulation;
    const panel=document.createElement('section');panel.className='simulation-result';
    panel.append(textEl('h3','Measured sandbox results'),textEl('p',s.scope,'note'));
    const table=document.createElement('table');const tbody=document.createElement('tbody');
    [['Metric','Baseline','Proposed'],['Read time (ms)',s.baseline.read_ms.toFixed(3),s.proposed.read_ms.toFixed(3)],['Insert time per row (ms)',s.baseline.insert_ms_per_row.toFixed(6),s.proposed.insert_ms_per_row.toFixed(6)],['Storage (bytes)',s.baseline.storage_bytes,s.proposed.storage_bytes]].forEach(v=>tbody.append(row(v)));table.append(tbody);panel.append(table);
    panel.append(textEl('p','Read improvement: '+s.read_improvement_pct+'% · RL reward: '+data.rl.reward+' · Learned score: '+data.rl.q_value));
    if(s.hypothetical)panel.append(textEl('p','HypoPG planner cost: '+s.hypothetical.original_cost+' → '+s.hypothetical.hypothetical_cost+'. Estimated index size: '+s.hypothetical.estimated_index_bytes+' bytes; measured physical size: '+s.hypothetical.physical_index_bytes+' bytes; estimate error: '+s.hypothetical.storage_estimate_error_pct+'%. Planner costs are not milliseconds.','note'));
    panel.append(textEl('p','Source tables modified: No. Distributed network simulated: No.','note'));
    structureOutput.querySelector('.simulation-result')?.remove();structureOutput.append(panel);approveButton.hidden=false;
  }catch(e){structureOutput.append(textEl('p',e.message));}
  finally{simulateButton.disabled=false;}
};
approveButton.onclick=async()=>{
  try{
    const data=await api('/api/approve',{token:proposalToken});
    const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download='querylab-review-plan.json';a.click();URL.revokeObjectURL(url);
    structureOutput.append(textEl('p',data.message,'note'));
  }catch(e){structureOutput.append(textEl('p',e.message));}
};
const logPanel=document.createElement('details');logPanel.className='card';
logPanel.append(textEl('summary','Masked slow-query logs & plan history'),textEl('p','Import a JSON array of query, plan, and duration_ms records. Raw fields are scrubbed locally before storage. No logs are sent automatically to AI.','note'));
const logInput=document.createElement('textarea');logInput.setAttribute('aria-label','Query log JSON');logInput.placeholder='[{"query":"SELECT ...", "duration_ms":120, "plan":{"Plan":{"Node Type":"Seq Scan","Plan Rows":1000,"Total Cost":80}}}]';
const importButton=textEl('button','Import logs'),historyButton=textEl('button','View masked history'),sampleButton=textEl('button','Load sample log','text-button');
const logActions=document.createElement('div');logActions.className='demo-buttons';logActions.append(sampleButton,importButton,historyButton);
const logOutput=textEl('pre','');logOutput.className='history-output';logPanel.append(logInput,logActions,logOutput);structurePanel.after(logPanel);
sampleButton.onclick=()=>logInput.value=JSON.stringify([{query:"SELECT id FROM orders WHERE status = 'completed'",duration_ms:150,plan:{Plan:{'Node Type':'Seq Scan','Relation Name':'orders',Filter:"status='completed'",'Plan Rows':50000,'Total Cost':6000}}}],null,2);
importButton.onclick=async()=>{try{const d=await api('/api/history',{records:JSON.parse(logInput.value)});logOutput.textContent=d.privacy+' Imported: '+d.imported;logInput.value='';}catch(e){logOutput.textContent=e.message}};
historyButton.onclick=async()=>{try{const d=await(await fetch('/api/history')).json();logOutput.textContent=JSON.stringify(d.records,null,2);}catch(e){logOutput.textContent=e.message}};
