(() => {
  const body = document.body;
  const table = document.getElementById('dataTable');
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const number = (value) => Number(value || 0).toLocaleString();
  const showStatus = (message, isError = false) => {
    let status = document.getElementById('portfolioStatus');
    if (!status) {
      status = document.createElement('div'); status.id = 'portfolioStatus';
      document.querySelector('main .topbar')?.after(status);
    }
    status.className = isError ? 'alert' : 'notice';
    status.setAttribute('role', isError ? 'alert' : 'status');
    status.textContent = message;
  };
  if (document.querySelector('.grid.kpis') && body.dataset.columns !== '0') {
    const metrics = [
      ['Columns', number(body.dataset.columns), 'Fields in the active dataset', '▥'],
      ['IQR outlier rows', number(body.dataset.outliers), 'Rows flagged by numeric bounds', '⌁'],
      ['Anomaly rows', body.dataset.anomalies === '' ? '—' : number(body.dataset.anomalies), body.dataset.anomalies === '' ? 'Run Isolation Forest to calculate' : 'Flagged by Isolation Forest', '◉'],
    ];
    const grid = document.querySelector('.grid.kpis');
    metrics.forEach(([label,value,detail,icon]) => {
      const card=document.createElement('article'); card.className='card';
      card.innerHTML=`<div class="kpi-top">${label}<span class="kpi-mark">${icon}</span></div><div class="kpi-value">${value}</div><div class="kpi-foot">${detail}</div>`;
      grid.append(card);
    });
    const distribution=document.createElement('section'); distribution.className='card';
    distribution.innerHTML='<div class="panel-head"><div><h2>Cell completeness</h2><p>Measured from the active dataset</p></div></div><div id="qualityChart" class="chart" role="img" aria-label="Complete and missing cell distribution"></div>';
    document.querySelector('.upper-grid')?.append(distribution);
    const chart=document.getElementById('qualityChart');
    const total=Number(body.dataset.totalCells||0), missing=Number(body.dataset.missing||0);
    if (chart && window.Plotly) Plotly.newPlot(chart,[{type:'pie',hole:.72,labels:['Complete cells','Missing cells'],values:[Math.max(0,total-missing),missing],marker:{colors:['#42dec5','#f2bd6c']},textinfo:'label+percent',hovertemplate:'%{label}<br>%{value:,} cells<extra></extra>'}],{margin:{l:10,r:10,t:10,b:10},paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{color:'#dce8eb',size:11},showlegend:false},{displayModeBar:false,responsive:true});
  }
  if (body.dataset.notice || body.dataset.error) {
    showStatus(body.dataset.error || body.dataset.notice, Boolean(body.dataset.error));
  }
  document.getElementById('uploadForm')?.addEventListener('submit', async (event) => {
    const button = event.submitter;
    if (!button || !['download','download_report','download_script'].includes(button.value)) return;
    event.preventDefault();
    const originalText = button.textContent;
    button.disabled = true; button.textContent = 'Preparing download…';
    try {
      const formData = new FormData(event.currentTarget);
      formData.set('action', button.value);
      const response = await fetch(event.currentTarget.action || window.location.href, {method:'POST',body:formData});
      const disposition = response.headers.get('Content-Disposition') || '';
      if (!response.ok || !disposition.toLowerCase().includes('attachment')) {
        throw new Error('The export could not be prepared. Check the dataset and try again.');
      }
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || 'datadoctor_export';
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      showStatus(`${filename} is ready. Your browser started the download.`);
    } catch (error) {
      showStatus(error.message || 'The export failed. Please try again.', true);
    } finally {
      button.disabled = false; button.textContent = originalText;
    }
  });
  document.querySelectorAll('button[name="action"][value^="apply_"],button[name="action"][value="reset_dataset"]').forEach((button) => {
    button.addEventListener('click', (event) => {
      const label = button.textContent.trim().replace(/[✓↗]/g, '').trim();
      const detail = button.value === 'reset_dataset'
        ? 'The active dataset and cleaning history will return to the uploaded data.'
        : 'The change applies to the active in-memory dataset. You can undo it.';
      if (!window.confirm(`${label}? ${detail}`)) event.preventDefault();
    });
  });
  if (table && body.dataset.explorerApi) {
    const toolbar = document.createElement('div');
    toolbar.className = 'explorer-tools';
    toolbar.innerHTML = '<input type="search" aria-label="Search dataset" placeholder="Search all columns…"><select aria-label="Rows per page"><option>10</option><option>25</option><option>50</option></select><button type="button" data-prev>Previous</button><button type="button" data-next>Next</button><span class="page-label" aria-live="polite"></span>';
    table.closest('.table-wrap').before(toolbar);
    const profile = document.createElement('div'); profile.className = 'column-profile'; toolbar.before(profile);
    let page = 1, timer;
    const search = toolbar.querySelector('input'), size = toolbar.querySelector('select');
    const render = async () => {
      const params = new URLSearchParams({q:search.value,page:String(page),page_size:size.value});
      try {
        const response = await fetch(`${body.dataset.explorerApi}?${params}`), data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not load dataset.');
        table.tHead.innerHTML = `<tr><th scope="col">Row</th>${data.columns.map((column) => `<th scope="col">${esc(column.name)}<small class="dtype">${esc(column.dtype)}</small></th>`).join('')}</tr>`;
        table.tBodies[0].innerHTML = data.rows.map((row) => `<tr><td>${row.index}</td>${row.cells.map((cell) => `<td class="${cell.missing?'missing-cell':''}">${cell.missing?'Missing':esc(cell.value)}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${data.columns.length+1}">No rows match this search.</td></tr>`;
        profile.innerHTML = data.columns.map((column) => `<span class="column-chip"><b>${esc(column.name)}</b> · ${esc(column.dtype)} · ${column.missing} missing · ${column.unique} unique</span>`).join('');
        toolbar.querySelector('.page-label').textContent = `${data.total_rows.toLocaleString()} matches · page ${data.page} of ${data.pages}`;
        toolbar.querySelector('[data-prev]').disabled = data.page <= 1; toolbar.querySelector('[data-next]').disabled = data.page >= data.pages; page = data.page;
      } catch (error) { toolbar.querySelector('.page-label').textContent = error.message; }
    };
    search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { page=1; render(); },180); });
    size.addEventListener('change', () => { page=1; render(); });
    toolbar.querySelector('[data-prev]').addEventListener('click', () => { page--; render(); });
    toolbar.querySelector('[data-next]').addEventListener('click', () => { page++; render(); }); render();
  }
  const nav = document.getElementById('nav');
  document.getElementById('mobileMenu')?.addEventListener('click', () => nav?.classList.toggle('open'));
  document.querySelectorAll('.nav a').forEach((link) => link.addEventListener('click', () => nav?.classList.remove('open')));
  if (body.dataset.activity) {
    let activities=[]; try { activities=JSON.parse(body.dataset.activity); } catch (_) { /* Empty history is valid. */ }
    if (!Array.isArray(activities)) activities=[];
    const section=document.createElement('section'); section.className='card'; section.id='activity';
    section.innerHTML=`<div class="panel-head"><div><h2>Recent cleaning activity</h2><p>Actions applied to this uploaded dataset in the current session</p></div><span class="subtle">${activities.length} ACTIONS</span></div>${activities.length?`<div class="activity-list">${activities.map((item)=>`<div class="activity-item"><span>${esc(item.label)}</span><time>${esc(item.time)}</time></div>`).join('')}</div>`:'<p>No cleaning actions yet. Preview a change in Cleaning Studio to get started.</p>'}`;
    document.getElementById('export')?.before(section);
  }
})();
