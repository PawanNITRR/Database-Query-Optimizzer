// Two optional collapsed panels keep the main query flow small.
function textEl(tag, text, cls){const el=document.createElement(tag);el.textContent=text;if(cls)el.className=cls;return el}
async function api(path, data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const j=await r.json();if(!r.ok)throw Error(j.error);return j}
const structurePanel=document.createElement('details');structurePanel.className='card';
const questionHint=textEl('p','You can also ask about monthly sales, products, or payments. These questions use the three demo report templates.','note');
$('query').closest('.sql-editor').after(questionHint);
structurePanel.append(textEl('summary','Prediction Layer'));
const structureOutput=textEl('div','');
const predictionSuggestions=textEl('section','');predictionSuggestions.append(textEl('h2','Suggestions & improvements'),textEl('p','Enter SQL above, then open Prediction Layer to see recommendations.','note'));
const predictionScale=textEl('section','','prediction-scale');
const scaleHeading=textEl('h3','Data scale · 1×');
const scaleSlider=document.createElement('input');scaleSlider.type='range';scaleSlider.min='1';scaleSlider.max='100';scaleSlider.step='0.1';scaleSlider.value='1';scaleSlider.disabled=true;scaleSlider.setAttribute('aria-label','Data scale');
const scales=[1,10,20,30,40,50,60,70,80,90,100];
const scaleTicks=textEl('div','','scale-ticks');scales.forEach(v=>scaleTicks.append(textEl('span',v+'×')));
const scalePrediction=textEl('div','','scale-prediction');scalePrediction.setAttribute('aria-live','polite');
scalePrediction.append(textEl('p','The estimate will appear after the query is analyzed.','note'));
const scaleNote=textEl('p','Linear extrapolation from a separate 50,000-row synthetic benchmark. Assumes the same plan and selectivity as runtimes scale. Larger scales are estimates, not measured source-query results.','note');
 predictionScale.append(scaleHeading,scaleSlider,scaleTicks,scalePrediction,scaleNote);
structureOutput.append(predictionSuggestions,predictionScale);structurePanel.append(structureOutput);$('results').after(structurePanel);
let predictionResult=null,predictionSql=null,predictionBusy=false;
function updatePrediction(){
  const scale=Number(scaleSlider.value),scaleText=Number.isInteger(scale)?String(scale):scale.toFixed(1);scaleHeading.textContent='Data scale · '+scaleText+'×';scaleSlider.setAttribute('aria-valuetext',scaleText+' times the baseline data');
  scaleSlider.style.setProperty('--scale-fill',((scale-1)/99*100)+'%');
  if(!predictionResult)return;
  const s=predictionResult,baseline=s.baseline.read_ms*scale,proposed=s.proposed.read_ms*scale;
  const saved=baseline-proposed;
  const headline=textEl('div','','prediction-headline');
  headline.append(textEl('span',scale===1?'Measured sandbox time saved':'Estimated time saved','prediction-label'),textEl('strong',Math.abs(saved).toFixed(3)+' ms','prediction-percentage'),textEl('span',saved>0?'LESS READ TIME':saved<0?'ADDITIONAL READ TIME':'NO MEASURED READ GAIN','prediction-caption'));
  const times=textEl('div','','prediction-times');
  [['Without the strategy',baseline.toFixed(3)+' ms'],['With the strategy',proposed.toFixed(3)+' ms'],[baseline>=proposed?'Time saved':'Additional time',Math.abs(baseline-proposed).toFixed(3)+' ms']].forEach(([label,value])=>{const item=textEl('div','');item.append(textEl('span',label),textEl('strong',value));times.append(item)});
  scalePrediction.replaceChildren(headline,times,textEl('p',(50000*scale).toLocaleString()+' synthetic rows at '+scaleText+'× data scale. The comparison describes the selected strategy only; the other recommendations have not been measured together.','note'));
}
scaleSlider.oninput=updatePrediction;
async function loadPrediction(){
  const query=$('query').value.trim();
  if(predictionBusy||query===predictionSql)return;
  predictionResult=null;predictionSql=null;scaleSlider.disabled=true;
  if(!query){predictionSuggestions.replaceChildren(textEl('h2','Suggestions & improvements'),textEl('p','Enter a SELECT query in the editor above.','note'));return}
  predictionBusy=true;predictionSuggestions.replaceChildren(textEl('h2','Suggestions & improvements'),textEl('p','Analyzing recommendations and measuring the selected strategy…','note'));
  scalePrediction.replaceChildren(textEl('p','Preparing the scale estimate…','note'));
  try{
    const data=await api('/api/advice',{query});
    predictionSuggestions.replaceChildren(textEl('h2','Suggestions & improvements'));
    const list=document.createElement('ul');list.className='prediction-suggestions';
    const descriptions={
      index:['An index gives PostgreSQL a shorter path to matching rows instead of scanning every row. Putting equality columns before date-range columns can help the query narrow its search earlier.','The potential benefit depends on filter selectivity and the execution plan. An extra index also consumes storage and adds work to inserts and updates.'],
      range:['Monthly partitions split the table into smaller date-based pieces. For a query restricted to a date range, PostgreSQL can skip months outside that range and read fewer partitions.','The benefit is strongest when the date filter allows partition pruning. Keys, partition bounds and migration need review; broad date ranges may see little benefit.'],
      hash:['Hash partitioning routes rows into buckets using a join or lookup key. Queries that constrain that key can potentially inspect fewer buckets rather than the entire table.','Joins without a selective key filter may still read every bucket. Local hash partitioning does not establish a distributed-sharding speedup; that requires separate testing.']
    };
    data.recommendations.filter(r=>!r.already_present).forEach(r=>{const li=document.createElement('li');li.append(textEl('strong',({index:'Composite index',range:'Monthly partitioning',hash:'Hash partitioning candidate'})[r.kind]+' · '+r.table),textEl('p',r.reason,'note'),textEl('p',descriptions[r.kind][0]),textEl('p',descriptions[r.kind][1],'note'));list.append(li)});
    if(!list.children.length)predictionSuggestions.append(textEl('p','No additional structural change suggested. Existing indexes already cover the candidate keys.','note'));
    predictionSuggestions.append(list,textEl('p','Strategy evaluated: '+data.action,'note'));
    const result=await api('/api/simulate',{token:data.token});predictionResult=result.simulation;predictionSql=query;scaleSlider.disabled=false;updatePrediction();
  }catch(e){scalePrediction.replaceChildren(textEl('p',e.message,'file-error'))}
  finally{predictionBusy=false;}
}
const chatPanel=document.createElement('details');chatPanel.className='card';
chatPanel.append(textEl('summary','Ask about performance'),textEl('h2','Analyze historical queries'),textEl('p','Upload 2–10 past SELECT queries as a .sql file, or a JSON array with query and optional plan / duration_ms. Each query is checked against local PostgreSQL.','note'));
const diagnosisLabel=textEl('label','What do you want to diagnose?');diagnosisLabel.htmlFor='diagnosis-statement';
const diagnosisStatement=document.createElement('input');diagnosisStatement.type='text';diagnosisStatement.id='diagnosis-statement';diagnosisStatement.maxLength=2000;diagnosisStatement.placeholder='Why is the sales report slow? Check its joins.';
const statementHint=textEl('p','Your statement selects relevant reports, table names, joins, sorting or aggregation from the file. Matching runs locally.','note');
const historyFile=document.createElement('input');historyFile.type='file';historyFile.accept='.sql,.json';historyFile.setAttribute('aria-label','Historical query file');historyFile.className='history-file';
const fileStatus=textEl('p','No file selected.','note');historyFile.onchange=()=>fileStatus.textContent=historyFile.files[0]?.name||'No file selected.';
const sampleLink=document.createElement('a');sampleLink.href='/static/historic-queries.json';sampleLink.download='historic-queries.json';sampleLink.textContent='Download sample history file';sampleLink.className='sample-link';
const chatButton=textEl('button','Analyze history file');const chatOutput=document.createElement('div');chatOutput.className='diagnosis-output';chatOutput.setAttribute('aria-live','polite');
chatPanel.append(diagnosisLabel,diagnosisStatement,statementHint,historyFile,fileStatus,sampleLink,chatButton,chatOutput);structurePanel.before(chatPanel);
chatButton.onclick=async()=>{
  chatButton.disabled=true;chatOutput.replaceChildren(textEl('p','Matching your statement to uploaded queries and measuring improvements…'));
  try{
    const file=historyFile.files[0];if(!file)throw Error('Choose a historical query file first.');
    if(!diagnosisStatement.value.trim())throw Error('Enter what you want to diagnose first.');
    if(file.size>200000)throw Error('Choose a file smaller than 200 KB.');
    const d=await api('/api/diagnose-file',{question:diagnosisStatement.value,filename:file.name,content:await file.text(),use_ai:$('ai').checked});
    chatOutput.replaceChildren(textEl('h3','Improvements'));
    const summary=textEl('div','','workload-summary');summary.append(textEl('p','Diagnosing: '+d.question,'question-bubble'),textEl('strong',d.matched_queries+' of '+d.query_count+' historical queries matched · '+d.measured_queries+' measured'));
    summary.append(textEl('p','Matched focus: '+d.focus+' · Query numbers: '+d.selected_query_numbers.join(', '),'note'));
    if(d.combined_improvement_pct!==null)summary.append(gainBadge(d.combined_improvement_pct));
    summary.append(textEl('p',d.scope,'note'));chatOutput.append(summary);
    const list=document.createElement('ol');list.className='improvement-list';
    d.improvements.forEach(item=>{
      const li=document.createElement('li');li.append(textEl('strong',item.title),item.improvement_pct===null?textEl('span','Not measured','improvement-neutral'):gainBadge(item.improvement_pct));
      li.append(textEl('p',item.detail),textEl('p',item.scope,'note'));
      if(item.before_ms!==undefined)li.append(metricBars('Query runtime','ms',item.before_ms,item.after_ms,3));
      if(item.historical_duration_ms!==undefined&&item.historical_duration_ms!==null)li.append(textEl('p','Uploaded historical runtime: '+item.historical_duration_ms.toFixed(3)+' ms','note'));
      if(item.evidence)li.append(textEl('p',item.evidence,'note'));
      if(item.optimized_sql)li.append(textEl('pre',item.optimized_sql));
      if(item.ddl)li.append(textEl('pre',item.ddl));list.append(li);
    });chatOutput.append(list);
    d.failures.forEach(f=>chatOutput.append(textEl('p','Query '+f.query_number+': '+f.error,'file-error')));
  }catch(e){chatOutput.replaceChildren(textEl('p',e.message,'file-error'));}
  finally{chatButton.disabled=false;}
};
function gainBadge(gain){return textEl('span',(gain>=0?'+':'')+gain.toFixed(2)+'% '+(gain>=0?'faster':'(slower)'),gain>0?'improvement-gain':'improvement-neutral')}
function metricBars(title,unit,baseline,proposed,precision){
  const card=textEl('section','','bar-chart');card.append(textEl('h3',title),textEl('p','Lower is better · '+unit,'note'));
  const max=Math.max(baseline,proposed,.000001);
  [['Baseline',baseline,'baseline'],['Proposed',proposed,'proposed']].forEach(([label,value,kind])=>{
    const line=textEl('div','','bar-row');line.append(textEl('span',label));
    const track=textEl('div','','bar-track'),bar=textEl('div','','bar '+kind);bar.style.width=Math.max(value/max*100,1)+'%';track.append(bar);
    line.append(track,textEl('strong',value.toFixed(precision)+' '+unit));card.append(line);
  });return card;
}
function simulationVisual(s,rl){
  const panel=textEl('section','','simulation-result');panel.append(textEl('h3','Simulation comparison'),textEl('p',s.scope,'note'));
  const metrics=textEl('div','','simulation-kpis');
  [['Read improvement',(s.read_improvement_pct>=0?'+':'')+s.read_improvement_pct.toFixed(2)+'%'],['Write change per row',(s.write_latency_delta_ms_per_row>=0?'+':'')+s.write_latency_delta_ms_per_row.toFixed(6)+' ms'],['Storage change',(s.storage_delta_bytes/1048576).toFixed(2)+' MiB']].forEach(([label,value])=>{const card=textEl('article','');card.append(textEl('span',label),textEl('strong',value));metrics.append(card)});panel.append(metrics);
  const charts=textEl('div','','simulation-charts');charts.append(metricBars('Read runtime','ms',s.baseline.read_ms,s.proposed.read_ms,3),metricBars('Insert latency per row','ms',s.baseline.insert_ms_per_row,s.proposed.insert_ms_per_row,6),metricBars('Storage','MiB',s.baseline.storage_bytes/1048576,s.proposed.storage_bytes/1048576,2));panel.append(charts);
  if(s.hypothetical){const h=s.hypothetical;panel.append(metricBars('HypoPG planner cost','cost units',h.original_cost,h.hypothetical_cost,2),textEl('p','Index size estimate error: '+h.storage_estimate_error_pct.toFixed(2)+'%. Planner cost is not runtime.','note'))}
  panel.append(textEl('p','RL reward: '+rl.reward.toFixed(3)+' · Learned score: '+rl.q_value.toFixed(3)+' · Source tables changed: No','note'));return panel;
}
