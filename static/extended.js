// Two optional collapsed panels keep the main query flow small.
function textEl(tag, text, cls){const el=document.createElement(tag);el.textContent=text;if(cls)el.className=cls;return el}
async function api(path, data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const j=await r.json();if(!r.ok)throw Error(j.error);return j}
const structurePanel=document.createElement('details');structurePanel.className='card';
const questionHint=textEl('p','You can also ask about monthly sales, products, or payments. These questions use the three demo report templates.','note');
$('query').closest('.sql-editor').after(questionHint);
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
    structureOutput.append(gnnVisualization(data.graph));
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
const chatPanel=document.createElement('details');chatPanel.className='card';
chatPanel.append(textEl('summary','Ask about performance'),textEl('p','Ask about sales, products or payments. Weekly reports use 23–29 June 2025 from the demo dataset.','note'));
const chatQuestion=document.createElement('input');chatQuestion.type='text';chatQuestion.maxLength=2000;chatQuestion.value='Why is the weekly sales reporting dashboard timing out?';chatQuestion.setAttribute('aria-label','Performance question');chatQuestion.style.cssText='width:100%;padding:12px;box-sizing:border-box;margin:12px 0';
const useSql=document.createElement('input');useSql.type='checkbox';
const sqlLabel=textEl('label','','query-choice');sqlLabel.append(useSql,document.createTextNode(' Analyze SQL in the main query box instead of a demo report'));
const chatButton=textEl('button','Diagnose');const chatOutput=document.createElement('div');chatOutput.className='diagnosis-output';chatOutput.setAttribute('aria-live','polite');
chatPanel.append(chatQuestion,sqlLabel,chatButton,chatOutput);structurePanel.before(chatPanel);
chatButton.onclick=async()=>{
  chatButton.disabled=true;chatOutput.replaceChildren(textEl('p','Analyzing the plan, checking the rewrite and measuring the sandbox…'));
  try{
    if(useSql.checked&&!$('query').value.trim())throw Error('Enter SQL in the main query box first.');
    const d=await api('/api/diagnose',{question:chatQuestion.value,query:useSql.checked?$('query').value:'',use_ai:$('ai').checked});
    chatOutput.replaceChildren(textEl('p','You asked: '+d.question,'question-bubble'));
    const groups=[['Report & plan',[]],['Recent history',[]],['Measured query results',[]],['Sandbox simulation',[]],['Privacy & scope',[]]];
    d.answer.forEach((t,i)=>{
      const group=i<2?0:t.startsWith('Recent masked')||t.startsWith('Their median')||t.startsWith('The ')||t.startsWith('No recent')?1:t.startsWith('Separate synthetic')||t.startsWith('Sandbox unavailable')?3:t.startsWith('These are separate')?4:2;
      groups[group][1].push(t);
    });
    groups.forEach(([title,paragraphs])=>{if(!paragraphs.length)return;const section=document.createElement('section');section.className='answer-section';section.append(textEl('h3',title));paragraphs.forEach(t=>section.append(textEl('p',t)));chatOutput.append(section)});
    chatOutput.append(gnnVisualization(d.result.graph));
    const evidence=document.createElement('details');evidence.append(textEl('summary','SQL & supporting evidence'),textEl('h3','Report SQL'),textEl('pre',d.report_query),textEl('h3','Selected SQL'),textEl('pre',d.result.optimized_query));
    d.recommendations.forEach(r=>evidence.append(textEl('h3',r.kind+(r.already_present?' · already present':'')),textEl('p',r.reason),textEl('pre',r.ddl)));
    evidence.append(textEl('h3','Masked optimizer input'),textEl('pre',d.result.masked_query));chatOutput.append(evidence);
  }catch(e){chatOutput.replaceChildren(textEl('p',e.message));}
  finally{chatButton.disabled=false;}
};
