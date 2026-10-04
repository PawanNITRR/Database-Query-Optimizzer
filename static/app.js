const $ = id => document.getElementById(id);
const rlSummary = document.createElement('p');
rlSummary.className = 'note';
rlSummary.id = 'rl-summary';
$('verdict').after(rlSummary);
$('example').onclick = () => $('query').value = examples.sales;
['sales', 'products', 'payments'].forEach(name => $(name).onclick = () => $('query').value = examples[name]);
fetch('/api/status').then(r=>r.json()).then(s=>{
  $('connection').textContent=s.database?'PostgreSQL connected':'PostgreSQL not connected';
  if(!s.ai){$('ai').checked=false;$('ai').parentElement.querySelector('small').textContent='Model unavailable · using local rules';}
}).catch(()=>$('connection').textContent='Server unavailable');
function row(values){const tr=document.createElement('tr');values.forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.appendChild(td)});return tr}
$('run').onclick = async () => {
  $('error').hidden=true;$('results').hidden=true;$('run').disabled=true;$('progress').hidden=false;
  $('progress').textContent='Masking SQL, analyzing the plan, and comparing local runtimes…';
  try {
    const response=await fetch('/api/optimize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:$('query').value,use_ai:$('ai').checked})});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'Request failed.');
    const m=data.metrics;
    const rl=data.rl;
    rlSummary.textContent = 'RL action: ' + rl.label + ' · Reward: ' + rl.reward.toFixed(3) +
      ' · Learned mean reward: ' + rl.q_value.toFixed(3) + ' · Action observations: ' + rl.action_trials +
      '. ' + rl.decision;
    $('old').textContent=m.original.execution_ms.toFixed(3)+' ms';$('new').textContent=m.optimized.execution_ms.toFixed(3)+' ms';$('gain').textContent=m.improvement_pct.toFixed(1)+'%';
    $('optimized').textContent=data.optimized_query;$('masked').textContent=data.masked_query;$('masked-result').textContent=data.masked_optimized;$('reason').textContent=data.explanation;$('engine').textContent=data.engine;
    $('verdict').textContent=(data.changed?'Rewrite passed the result-row check.':'No safe structural rewrite was applied. These repeated runs show normal timing variation.') + ' Total response: ' + (data.total_ms / 1000).toFixed(2) + ' seconds.';
    $('graph').replaceChildren(...data.graph.map(n=>row(['  '.repeat(n.depth || 0) + n.operator,n.rows,n.cost,n.score])));
    let reasons = document.getElementById('gnn-reasons');
    if(!reasons){reasons=document.createElement('p');reasons.id='gnn-reasons';reasons.className='note';$('graph').closest('.table-wrap').before(reasons);}
    reasons.textContent=(data.gnn_explanations || []).map(n=>n.reason).join(' ');
    $('details').replaceChildren(...[['Planning time (last run)','planning_ms'],['Result rows','rows'],['Shared buffer hits (last run)','buffer_hits'],['Shared buffer reads (last run)','buffer_reads'],['Execution samples (ms)','runs_ms']].map(([name,key])=>row([name,[m.original[key]].flat().join(', '),[m.optimized[key]].flat().join(', ')])));
    $('results').hidden=false;
  }catch(e){$('error').textContent=e.message;$('error').hidden=false}
  finally{$('run').disabled=false;$('progress').hidden=true}
};
