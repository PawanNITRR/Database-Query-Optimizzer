// Visualize the actual operator graph returned by the GNN; no table names needed.
function gnnVisualization(nodes){
  const host=document.createElement('section');host.className='gnn-view';
  const note=document.createElement('p');note.className='note';note.textContent='Each node is a PostgreSQL plan operator. Lines connect parent and child operations used by the GNN. Color shows the model score: teal 0–0.39, amber 0.40–0.69, coral 0.70–1.00. Scores are prototype signals, not proven bottlenecks.';host.append(note);
  if(!nodes?.length){const p=document.createElement('p');p.textContent='Run a query to generate its graph.';host.append(p);return host;}
  const ns='http://www.w3.org/2000/svg';
  function el(tag,attrs,text){const e=document.createElementNS(ns,tag);Object.entries(attrs||{}).forEach(([k,v])=>e.setAttribute(k,v));if(text!==undefined)e.textContent=text;return e;}
  const levels=new Map(),positions=new Map();
  nodes.forEach(n=>{const depth=n.depth||0;if(!levels.has(depth))levels.set(depth,[]);levels.get(depth).push(n)});
  const width=Math.max(660,...[...levels.values()].map(a=>a.length*232+32)),height=(Math.max(...levels.keys())+1)*116+24;
  levels.forEach((group,depth)=>group.forEach((n,i)=>positions.set(n.node,{x:width/2+(i-(group.length-1)/2)*232,y:depth*116+20})));
  const wrap=document.createElement('div');wrap.className='gnn-scroll';
  const svg=el('svg',{viewBox:`0 0 ${width} ${height}`,width,height,role:'group','aria-label':`GNN query plan with ${nodes.length} operator nodes. Select a node to inspect its estimates and score.`});
  nodes.forEach(n=>{const p=positions.get(n.parent),c=positions.get(n.node);if(p)svg.append(el('path',{d:`M ${p.x} ${p.y+78} C ${p.x} ${p.y+98}, ${c.x} ${c.y-20}, ${c.x} ${c.y}`,fill:'none',stroke:'#668099','stroke-width':2}))});
  const detail=document.createElement('p');detail.className='gnn-detail';detail.textContent='Select a node to see its estimated rows, planner cost and GNN score.';
  nodes.forEach(n=>{
    const p=positions.get(n.node),color=n.score>=.7?'#ff9b91':n.score>=.4?'#f2c66d':'#7ce0be';
    const group=el('g',{transform:`translate(${p.x-104},${p.y})`,tabindex:0,role:'button','aria-label':`${n.operator}, node ${n.node}, GNN score ${n.score}`});
    group.append(el('rect',{width:208,height:78,rx:10,fill:'#172639',stroke:color,'stroke-width':2}),el('text',{x:12,y:23,fill:'#edf4fc','font-size':14,'font-weight':600},n.operator),el('text',{x:12,y:45,fill:color,'font-size':13},`GNN score ${Number(n.score).toFixed(3)}`),el('text',{x:12,y:64,fill:'#b7c9db','font-size':12},`Node ${n.node} · ${Number(n.rows).toLocaleString()} rows`));
    const inspect=()=>detail.textContent=`${n.operator} · Node ${n.node} · Estimated rows: ${Number(n.rows).toLocaleString()} · Planner cost: ${Number(n.cost).toLocaleString()} · GNN score: ${Number(n.score).toFixed(3)}. Planner cost is not milliseconds.`;
    group.addEventListener('click',inspect);group.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();inspect()}});svg.append(group);
  });
  wrap.append(svg);host.append(wrap,detail);return host;
}
