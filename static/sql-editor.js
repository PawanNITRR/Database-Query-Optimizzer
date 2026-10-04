// Local highlighting only: SQL values and submission behavior stay unchanged.
const sqlKeywords=new Set(('SELECT FROM WHERE WITH AS MATERIALIZED NOT JOIN INNER LEFT RIGHT FULL OUTER CROSS ON AND OR IN EXISTS IS NULL TRUE FALSE DISTINCT ALL UNION EXCEPT INTERSECT GROUP BY ORDER HAVING LIMIT OFFSET ASC DESC CASE WHEN THEN ELSE END INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE INDEX PARTITION RANGE HASH FOR MODULUS REMAINDER DEFAULT LIKE PRIMARY KEY REFERENCES ALTER DROP CAST DATE BETWEEN OVER FILTER RETURNING USING NULLS FIRST LAST RECURSIVE').split(' '));
function sqlTokens(source){
  const fragment=document.createDocumentFragment();
  const pattern=/--[^\n]*|\/\*[\s\S]*?(?:\*\/|$)|\$(\w*)\$[\s\S]*?\$\1\$|'(?:''|\\.|[^'])*'|"(?:""|[^"])*"|%\([\w]+\)s|\$\d+|\b\d+(?:\.\d+)?(?:e[+-]?\d+)?\b|\b[a-z_][\w$]*\b|[<>!=~+*/|%-]+/gi;
  let end=0;
  for(const match of source.matchAll(pattern)){
    fragment.append(document.createTextNode(source.slice(end,match.index)));
    const token=match[0],upper=token.toUpperCase();let type='';
    if(token.startsWith('--')||token.startsWith('/*'))type='comment';
    else if(token.startsWith("'")||/^\$\w*\$/.test(token))type='string';
    else if(token.startsWith('"'))type='identifier';
    else if(token.startsWith('%(')||/^\$\d/.test(token))type='parameter';
    else if(/^\d/.test(token))type='number';
    else if(sqlKeywords.has(upper))type='keyword';
    else if(/^[a-z_]/i.test(token)&&/^\s*\(/.test(source.slice(match.index+token.length)))type='function';
    else if(/^[<>!=~+*/|%-]+$/.test(token))type='operator';
    if(type){const span=document.createElement('span');span.className='sql-'+type;span.textContent=token;fragment.append(span)}
    else fragment.append(document.createTextNode(token));
    end=match.index+token.length;
  }
  fragment.append(document.createTextNode(source.slice(end)));return fragment;
}
const queryInput=document.getElementById('query');
const sqlEditor=document.createElement('div');sqlEditor.className='sql-editor';
const sqlBackdrop=document.createElement('pre');sqlBackdrop.className='sql-backdrop';sqlBackdrop.setAttribute('aria-hidden','true');
queryInput.before(sqlEditor);sqlEditor.append(sqlBackdrop,queryInput);
function refreshSqlEditor(){
  sqlBackdrop.style.width=queryInput.clientWidth+'px';
  sqlBackdrop.replaceChildren(sqlTokens(queryInput.value+'\n'));
  sqlBackdrop.scrollTop=queryInput.scrollTop;sqlBackdrop.scrollLeft=queryInput.scrollLeft;
}
queryInput.addEventListener('input',refreshSqlEditor);
queryInput.addEventListener('scroll',()=>{sqlBackdrop.scrollTop=queryInput.scrollTop;sqlBackdrop.scrollLeft=queryInput.scrollLeft});
queryInput.addEventListener('keydown',e=>{
  if(e.key==='Tab'&&!e.shiftKey){e.preventDefault();queryInput.setRangeText('  ',queryInput.selectionStart,queryInput.selectionEnd,'end');refreshSqlEditor()}
});
// Keep programmatically loaded examples in sync with the highlighted layer.
const inputValue=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value');
Object.defineProperty(queryInput,'value',{get(){return inputValue.get.call(this)},set(value){inputValue.set.call(this,value);refreshSqlEditor()}});
refreshSqlEditor();
new ResizeObserver(refreshSqlEditor).observe(queryInput);
const highlighted=new WeakMap();
function highlightSqlOutputs(){
  document.querySelectorAll('pre:not(.sql-backdrop)').forEach(pre=>{
    const text=pre.textContent;
    if(highlighted.get(pre)===text)return;
    highlighted.set(pre,text);pre.classList.add('sql-output');pre.replaceChildren(sqlTokens(text));
  });
}
new MutationObserver(highlightSqlOutputs).observe(document.querySelector('main'),{childList:true,subtree:true,characterData:true});
highlightSqlOutputs();
