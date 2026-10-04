let tabGroupNumber=0;
function makeTabs(items,label){
  const root=document.createElement('div');root.className='tab-group';
  const list=document.createElement('div');list.className='tab-list';list.setAttribute('role','tablist');list.setAttribute('aria-label',label);
  const id='tabs-'+(++tabGroupNumber),buttons=[],panels=[];
  function activate(index,focus=false){
    buttons.forEach((b,i)=>{b.setAttribute('aria-selected',String(i===index));b.tabIndex=i===index?0:-1;panels[i].hidden=i!==index});
    if(focus)buttons[index].focus();
    if(label==='Analysis workspace'&&index===2)loadPrediction();
  }
  items.forEach(([title,content],i)=>{
    const button=document.createElement('button');button.type='button';button.id=id+'-tab-'+i;button.textContent=title;button.setAttribute('role','tab');button.setAttribute('aria-controls',id+'-panel-'+i);
    const panel=document.createElement('section');panel.className='tab-panel';panel.id=id+'-panel-'+i;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',button.id);panel.tabIndex=0;panel.append(content);
    button.onclick=()=>activate(i);
    button.onkeydown=e=>{let next=i;if(e.key==='ArrowRight')next=(i+1)%items.length;else if(e.key==='ArrowLeft')next=(i-1+items.length)%items.length;else if(e.key==='Home')next=0;else if(e.key==='End')next=items.length-1;else return;e.preventDefault();activate(next,true)};
    buttons.push(button);panels.push(panel);list.append(button);
  });
  root.append(list,...panels);activate(0);return {root,activate};
}

// Keep the original controls and results intact while changing their layout.
const comparison=document.getElementById('results');
const overview=document.createElement('div');
overview.append(document.getElementById('verdict'),document.getElementById('rl-summary'),comparison.querySelector('.metrics'));
const graphCard=document.getElementById('gnn-visual').closest('.card');
const sqlCard=document.getElementById('optimized').closest('.card');
const privacyCard=document.getElementById('masked').closest('.card');
const detailsCard=document.getElementById('graph').closest('.card');
function unfold(card){if(card.tagName==='DETAILS'){card.open=true;card.querySelector(':scope > summary').hidden=true}return card}
const resultTabs=makeTabs([['Overview',overview],['Optimized SQL',sqlCard],['GNN graph',graphCard],['AI privacy',unfold(privacyCard)],['Runtime details',unfold(detailsCard)]],'Query comparison sections');
comparison.querySelector('.result-heading').after(resultTabs.root);
const comparisonPanel=document.createElement('div');
const emptyComparison=document.createElement('p');emptyComparison.className='note';emptyComparison.textContent='Run Optimize & compare above to see timings, SQL and GNN analysis.';comparisonPanel.append(emptyComparison);
const workspaceAnchor=document.createElement('div');comparison.before(workspaceAnchor);comparisonPanel.append(comparison);
const workspaceTabs=makeTabs([['Query comparison',comparisonPanel],['Ask about performance',unfold(chatPanel)],['Prediction Layer',unfold(structurePanel)]],'Analysis workspace');
workspaceAnchor.replaceWith(workspaceTabs.root);
new MutationObserver(()=>{emptyComparison.hidden=!comparison.hidden;if(!comparison.hidden){workspaceTabs.activate(0);resultTabs.activate(0)}}).observe(comparison,{attributes:true,attributeFilter:['hidden']});
