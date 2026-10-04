const $ = id => document.getElementById(id);
const messages = $('messages');
const seed = document.createElement('p');
seed.className = 'suggestions';
seed.innerHTML = '<button type="button">Why might this query be slow?</button><button type="button">Can you optimize it?</button><button type="button">Explain the execution plan</button>';
messages.after(seed);
seed.querySelectorAll('button').forEach(button => button.onclick = () => {
  $('message').value = button.textContent;
  $('message').focus();
});

['sales', 'products', 'payments'].forEach(name => $(name).onclick = () => {
  $('query').value = examples[name];
  $('query').focus();
});
$('example').onclick = () => $('query').value = examples.sales;
$('clear-chat').onclick = () => {
  messages.replaceChildren();
  $('evidence').hidden = true;
  $('error').hidden = true;
  messages.insertAdjacentHTML('beforeend', '<article class="message assistant"><span class="avatar">Q</span><div class="bubble"><strong>Chat cleared.</strong><p>Ask a new question about the query context below.</p></div></article>');
};
fetch('/api/status').then(r => r.json()).then(s => {
  $('connection').textContent = s.database ? 'PostgreSQL connected' : 'PostgreSQL not connected';
  if (!s.ai) {
    $('ai').disabled = true;
    $('ai').parentElement.querySelector('small').textContent = 'Ollama model unavailable';
  }
}).catch(() => $('connection').textContent = 'Server unavailable');

function addMessage(text, role) {
  const article = document.createElement('article');
  article.className = 'message ' + role;
  if (role === 'assistant') {
    const avatar = document.createElement('span');
    avatar.className = 'avatar';
    avatar.textContent = 'Q';
    article.append(avatar);
  }
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  article.append(bubble);
  messages.append(article);
  article.scrollIntoView({behavior: 'smooth', block: 'nearest'});
}
function row(values) {
  const tr = document.createElement('tr');
  values.forEach(value => {
    const td = document.createElement('td');
    td.textContent = value;
    tr.append(td);
  });
  return tr;
}
async function ask() {
  const question = $('message').value.trim();
  if (!question || $('send').disabled) return;
  addMessage(question, 'user');
  $('message').value = '';
  $('error').hidden = true;
  $('send').disabled = true;
  $('progress').hidden = false;
  $('progress').textContent = 'Reading the local plan and comparing query runtimes…';
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: question, query: $('query').value, use_ai: $('ai').checked})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed.');
    addMessage(data.reply, 'assistant');
    const m = data.metrics;
    $('old').textContent = m.original.execution_ms.toFixed(3) + ' ms';
    $('new').textContent = m.optimized.execution_ms.toFixed(3) + ' ms';
    $('gain').textContent = m.improvement_pct.toFixed(1) + '%';
    $('optimized').textContent = data.optimized_query;
    $('engine').textContent = data.engine + ' · response in ' + (data.total_ms / 1000).toFixed(2) + ' seconds';
    $('graph').replaceChildren(...data.graph.map(n => row([n.operator, n.rows, n.cost, n.score])));
    $('evidence').hidden = false;
  } catch (error) {
    $('error').textContent = error.message;
    $('error').hidden = false;
  } finally {
    $('send').disabled = false;
    $('progress').hidden = true;
    $('message').focus();
  }
}
$('send').onclick = ask;
$('message').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    ask();
  }
});
