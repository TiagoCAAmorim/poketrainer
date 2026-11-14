/* PTCG Lab — página estática: monta a lista de cartas e gera o PDF no navegador. */
(function () {
  'use strict';
  // ⚙️ Configuração: troque pela sua chave Pix (deixe '' para esconder o convite do café)
  const PIX_KEY = 'bcd8d244-8aeb-4003-99ca-d8ba4f5f5952';
  // Ko-fi (gorjetas internacionais): cole o endereço da sua página, ex. 'https://ko-fi.com/seunome' ('' esconde o botão)
  const KOFI_URL = 'https://ko-fi.com/tiagoamorim';

  const BASE = window.DADOS_CARTAS, CARTAS = BASE.cartas;
  const TEMPORADA = window.DADOS_DECKS || { torneios: [] };
  Object.keys(CARTAS).forEach(id => { CARTAS[id].id = id; });

  const I18N = {
    en: {
      title: 'Proxy PDF', intro: 'Build a printable PDF of simplified cards: text only, black and white, no artwork, so it saves ink. Great for playtesting a deck. Everything runs in your browser; nothing is uploaded.',
      h_import: '1. Start from a deck', load: 'Load', paste: 'or paste a deck list (TCG Live / Limitless)', import: 'Import list',
      h_add: '2. Add cards', add_hint: 'Start typing a card name (English or Portuguese). ↑ ↓ to choose, Enter to add. Tip: "3 ultra" adds 3 copies.',
      search_ph: 'Card name…', h_cards: 'Cards to print', copies: 'copies', clear: 'Clear', empty: 'Pick a deck above or search for cards.',
      h_pdf: '3. PDF', pdf_lang: 'Card text language', paper: 'Paper size', custom: 'Custom size, width x height in mm', scale: 'Card size (% of real, 63 × 88 mm)',
      margin: 'Margin (mm)', gap: 'Gap (mm)', generate: 'Generate PDF', pages: (p, n, c, l) => `${p} page(s), ${n} cards per page (${c} × ${l})`,
      g_p: 'Pokémon', g_t: 'Trainers', g_e: 'Energy', tourney: 'Top 16 of each event — pick one', season: (y, atual) => `${y} season${atual ? ' (current)' : ''}`, deckpick: 'Pick a deck', place: n => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th')),
      players: 'players', loaded: n => `Loaded ${n} cards.`, imported: n => `Imported ${n} cards.`, missing: l => `Not found / not in the current format:\n${l}`,
      e_empty: 'Add some cards first.', e_paper: 'Invalid paper size.', e_scale: 'Card size must be between 20% and 150%.', e_fit: 'Cards at this size do not fit the paper with this margin.',
      done: (n, p) => `PDF generated: ${n} cards, ${p} page(s).`, lang_note: 'Standard format (marks H, I, J).',
      cafe: 'If this helped you, you can buy me a coffee:', kofi: 'Ko-fi', pix: 'Pix (Brazil)', copy: 'Copy', copied: 'Copied!', remove: 'remove',
      disclaimer: 'PTCG Lab is a personal, non-profit project, not affiliated with The Pokémon Company, Nintendo, Creatures or Game Freak. Pokémon and the names and texts of the cards belong to their respective owners. The generated PDFs contain plain text only, with no artwork, and are meant for personal playtesting. Deck lists come from public tournament results on Limitless.',
      deckof: (p, a) => `${p} — ${a}`, warn: 'incomplete'
    },
    pt: {
      title: 'PDF de proxies', intro: 'Monte um PDF para imprimir com cartas simplificadas: só texto, preto e branco, sem arte, para gastar pouca tinta. Ótimo para testar um deck. Tudo roda no seu navegador; nada é enviado.',
      h_import: '1. Comece por um deck', load: 'Carregar', paste: 'ou cole uma lista de deck (TCG Live / Limitless)', import: 'Importar lista',
      h_add: '2. Adicionar cartas', add_hint: 'Comece a digitar o nome da carta (inglês ou português). ↑ ↓ para escolher, Enter para adicionar. Dica: "3 ultra" adiciona 3 cópias.',
      search_ph: 'Nome da carta…', h_cards: 'Cartas a imprimir', copies: 'cópias', clear: 'Limpar', empty: 'Escolha um deck acima ou busque cartas.',
      h_pdf: '3. PDF', pdf_lang: 'Idioma do texto das cartas', paper: 'Tamanho do papel', custom: 'Tamanho personalizado, largura x altura em mm', scale: 'Tamanho das cartas (% do real, 63 × 88 mm)',
      margin: 'Margem (mm)', gap: 'Espaço (mm)', generate: 'Gerar PDF', pages: (p, n, c, l) => `${p} página(s), ${n} cartas por página (${c} × ${l})`,
      g_p: 'Pokémon', g_t: 'Treinadores', g_e: 'Energias', tourney: 'Top 16 de cada evento — escolha um', season: (y, atual) => `Temporada ${y}${atual ? ' (atual)' : ''}`, deckpick: 'Escolha um deck', place: n => n + 'º',
      players: 'jogadores', loaded: n => `${n} cartas carregadas.`, imported: n => `${n} cartas importadas.`, missing: l => `Não encontradas / fora do formato atual:\n${l}`,
      e_empty: 'Adicione cartas primeiro.', e_paper: 'Tamanho de papel inválido.', e_scale: 'O tamanho da carta deve ficar entre 20% e 150%.', e_fit: 'A carta neste tamanho não cabe no papel com essa margem.',
      done: (n, p) => `PDF gerado: ${n} cartas, ${p} página(s).`, lang_note: 'Formato Padrão (marcas H, I, J).',
      cafe: 'Se isto te ajudou, você pode me pagar um café:', kofi: 'Ko-fi (exterior)', pix: 'Pix', copy: 'Copiar', copied: 'Copiado!', remove: 'remover',
      disclaimer: 'O PTCG Lab é um projeto pessoal, sem fins lucrativos e sem nenhuma associação com a The Pokémon Company, a Nintendo, a Creatures ou a Game Freak. Pokémon e os nomes e textos das cartas pertencem aos seus respectivos donos. Os PDFs gerados têm apenas texto, sem arte, e servem para teste pessoal. As listas de deck vêm dos resultados públicos de torneios da Limitless.',
      deckof: (p, a) => `${p} — ${a}`, warn: 'incompleto'
    }
  };

  const $ = id => document.getElementById(id);
  const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* sem armazenamento */ } } };
  let lang = store.get('ptcg_lang') || ((navigator.language || '').toLowerCase().startsWith('pt') ? 'pt' : 'en');
  let idiomaPdfManual = store.get('ptcg_pdflang');
  const t = k => I18N[lang][k];
  let lista = new Map();   // id → cópias
  try { (JSON.parse(store.get('ptcg_lista') || '[]')).forEach(([id, n]) => { if (CARTAS[id] && n > 0) lista.set(id, n); }); } catch (e) { /* ignora */ }

  // ------------------------------------------------------------ normalização e busca
  const norm = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[’‘`]/g, "'").toLowerCase().replace(/\s+/g, ' ').trim();
  const POR_NOME = new Map(), ENTRADAS = [];
  const ORD = { p: 0, t: 1, e: 2 };
  Object.values(CARTAS).forEach(d => {
    const n1 = norm(d.n), n2 = d.p ? norm(d.p) : '';
    if (!POR_NOME.has(n1)) POR_NOME.set(n1, d.id);
    if (n2 && !POR_NOME.has(n2)) POR_NOME.set(n2, d.id);
    ENTRADAS.push({ d, n1, n2 });
  });
  [['Grass', 'Planta'], ['Fire', 'Fogo'], ['Water', 'Água'], ['Lightning', 'Elétrico'], ['Psychic', 'Psíquico'], ['Fighting', 'Lutador'], ['Darkness', 'Escuridão'], ['Metal', 'Metal']].forEach(([en, pt]) => {
    const id = BASE.nomes['Basic ' + en + ' Energy'];
    if (!id) return;
    [en + ' energy', `energia de ${pt} basica`, `energia basica de ${pt}`, `energia de ${pt}`, `energia ${pt} basica`, `energia ${pt}`].forEach(a => { const k = norm(a); if (!POR_NOME.has(k)) POR_NOME.set(k, id); });
  });

  function pontos(e, q) {   // menor é melhor; -1 = não casa
    let best = -1;
    for (const n of [e.n1, e.n2]) {
      if (!n) continue;
      let p = -1;
      if (n === q) p = 0; else if (n.startsWith(q)) p = 1;
      else if (n.split(/[\s\-:]+/).some(w => w.startsWith(q))) p = 2; else if (n.includes(q)) p = 3;
      if (p >= 0 && (best < 0 || p < best)) best = p;
    }
    if (best < 0 && norm(e.d.id).startsWith(q)) best = 4;
    return best;
  }
  function buscar(q, max = 12) {
    q = norm(q);
    if (!q) return [];
    const r = [];
    for (const e of ENTRADAS) { const p = pontos(e, q); if (p >= 0) r.push([p, e]); }
    r.sort((a, b) => a[0] - b[0] || ORD[a[1].d.k] - ORD[b[1].d.k] || a[1].d.n.localeCompare(b[1].d.n));
    return r.slice(0, max).map(x => x[1].d);
  }

  // ------------------------------------------------------------ importação de listas
  function resolver(nome, set, num) {
    if (set && num) {
      const n = String(num).replace(/^0+(?=\d)/, '');
      for (const code of [set.toUpperCase(), set.toUpperCase().replace(/^PR-/, '')]) {
        const id = BASE.impressoes[`${code}-${n}`];
        if (id) return id;
      }
    }
    return POR_NOME.get(norm(nome)) || null;
  }
  function parseLista(texto) {
    const cont = new Map(), faltam = [];
    for (const raw of String(texto).split(/\r?\n/)) {
      const ln = raw.trim();
      if (!ln || ln.startsWith('#') || /^(pok[eé]mon|trainer|treinador(es)?|energy|energia(s)?|total)\b.*:?\s*\d*\s*$/i.test(ln) && !/^\d/.test(ln)) continue;
      let m = ln.match(/^(\d+)x?\s+(.+?)\s+([A-Z][A-Z0-9-]{1,5})\s+(\d+[a-z]?)$/);
      let n, nome, set = null, num = null;
      if (m) { n = +m[1]; nome = m[2]; set = m[3]; num = m[4]; }
      else if ((m = ln.match(/^(\d+)x?\s+(.+)$/))) { n = +m[1]; nome = m[2]; }
      else continue;
      const id = resolver(nome, set, num);
      if (id) cont.set(id, (cont.get(id) || 0) + n); else faltam.push(ln);
    }
    return { cont, faltam };
  }
  function substituir(cont) { lista = new Map(cont); salvar(); render(); }

  // ------------------------------------------------------------ lista de cartas
  function salvar() { store.set('ptcg_lista', JSON.stringify([...lista])); }
  function nomeCarta(d) { return lang === 'pt' && d.p ? d.p : d.n; }
  function adicionar(id, n = 1) { lista.set(id, Math.max(0, (lista.get(id) || 0) + n)); if (!lista.get(id)) lista.delete(id); salvar(); render(); }
  function ordenadas() {
    return [...lista.keys()].map(id => CARTAS[id]).sort((a, b) => ORD[a.k] - ORD[b.k] || a.n.localeCompare(b.n) || a.id.localeCompare(b.id));
  }
  function render() {
    const el = $('lista');
    el.textContent = '';
    let total = 0, atual = null;
    for (const d of ordenadas()) {
      if (d.k !== atual) { atual = d.k; const g = document.createElement('div'); g.className = 'grp'; g.textContent = t('g_' + d.k); el.appendChild(g); }
      const n = lista.get(d.id); total += n;
      const it = document.createElement('div'); it.className = 'item';
      const nm = document.createElement('span'); nm.className = 'nm'; nm.textContent = nomeCarta(d); nm.title = d.n + (d.p ? ' / ' + d.p : '');
      const id = document.createElement('span'); id.className = 'id'; id.textContent = d.id;
      const q = document.createElement('span'); q.className = 'q';
      const menos = document.createElement('button'); menos.textContent = '−'; menos.title = t('remove'); menos.onclick = () => adicionar(d.id, -1);
      const b = document.createElement('b'); b.textContent = n;
      const mais = document.createElement('button'); mais.textContent = '+'; mais.onclick = () => adicionar(d.id, 1);
      q.append(menos, b, mais); it.append(nm, id, q); el.appendChild(it);
    }
    if (!lista.size) { const s = document.createElement('span'); s.className = 'mut'; s.textContent = t('empty'); el.appendChild(s); }
    $('total').textContent = total;
    atualizarInfo();
  }

  // ------------------------------------------------------------ autocompletar
  let sugestoes = [], sel = 0;
  const sug = $('sug'), busca = $('busca');
  function realce(parent, texto, q) {
    const nt = norm(texto), i = nt.length === texto.length ? nt.indexOf(q) : -1;   // só realça se norm preservar o comprimento
    if (i < 0) { parent.appendChild(document.createTextNode(texto)); return; }
    parent.append(document.createTextNode(texto.slice(0, i)));
    const mk = document.createElement('mark'); mk.textContent = texto.slice(i, i + q.length); parent.appendChild(mk);
    parent.append(document.createTextNode(texto.slice(i + q.length)));
  }
  function mostrarSug() {
    let txt = busca.value, qtd = 1;
    const m = txt.match(/^\s*(\d{1,2})\s+(.*)$/);
    if (m) { qtd = +m[1]; txt = m[2]; }
    sugestoes = buscar(txt);
    sel = 0; sug.textContent = '';
    if (!sugestoes.length) { sug.hidden = true; busca.setAttribute('aria-expanded', 'false'); return; }
    const q = norm(txt);
    sugestoes.forEach((d, i) => {
      const li = document.createElement('li'); li.setAttribute('role', 'option'); if (i === 0) li.className = 'sel';
      const n = document.createElement('span'); n.className = 'n';
      realce(n, d.n, q);
      if (d.p && d.p !== d.n) { const p = document.createElement('i'); p.append(document.createTextNode('  ')); realce(p, d.p, q); n.appendChild(p); }
      const id = document.createElement('span'); id.className = 'id'; id.textContent = d.id;
      li.append(n, id);
      li.onmousedown = ev => { ev.preventDefault(); escolher(d, qtd); };
      sug.appendChild(li);
    });
    sug.hidden = false; busca.setAttribute('aria-expanded', 'true');
  }
  function escolher(d, qtd) { adicionar(d.id, qtd || 1); busca.value = ''; sug.hidden = true; busca.focus(); }
  function qtdDigitada() { const m = busca.value.match(/^\s*(\d{1,2})\s+/); return m ? +m[1] : 1; }
  busca.addEventListener('input', mostrarSug);
  busca.addEventListener('focus', () => { if (busca.value) mostrarSug(); });
  busca.addEventListener('blur', () => { sug.hidden = true; });
  busca.addEventListener('keydown', ev => {
    const lis = sug.children;
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      if (!sugestoes.length) return; ev.preventDefault();
      lis[sel].className = ''; sel = (sel + (ev.key === 'ArrowDown' ? 1 : -1) + sugestoes.length) % sugestoes.length;
      lis[sel].className = 'sel'; lis[sel].scrollIntoView({ block: 'nearest' });
    } else if (ev.key === 'Enter') { if (sugestoes.length && !sug.hidden) { ev.preventDefault(); escolher(sugestoes[sel], qtdDigitada()); } }
    else if (ev.key === 'Escape') { sug.hidden = true; }
  });

  // ------------------------------------------------------------ decks da temporada
  const TORNEIOS = [...TEMPORADA.torneios].sort((a, b) => b.data.localeCompare(a.data));
  function preencherTorneios() {
    const s = $('torneio'), antes = s.value;
    s.textContent = '';
    const o0 = document.createElement('option'); o0.value = ''; o0.textContent = t('tourney'); s.appendChild(o0);
    let grupo = null, temp = null;
    TORNEIOS.forEach((tn, i) => {
      if (tn.temporada !== temp) { temp = tn.temporada; grupo = document.createElement('optgroup'); grupo.label = t('season')(temp, temp === TORNEIOS[0].temporada); s.appendChild(grupo); }
      const o = document.createElement('option'); o.value = i; o.textContent = `${tn.data} — ${tn.nome}` + (tn.jogadores ? ` (${tn.jogadores} ${t('players')})` : ''); grupo.appendChild(o);
    });
    s.value = antes; preencherDecks();
  }
  function preencherDecks() {
    const s = $('deck'), tn = TORNEIOS[$('torneio').value];
    s.textContent = '';
    const o0 = document.createElement('option'); o0.value = ''; o0.textContent = t('deckpick'); s.appendChild(o0);
    if (tn) tn.decks.forEach((dk, i) => { const o = document.createElement('option'); o.value = i; o.textContent = `${t('place')(dk.lugar)} ${t('deckof')(dk.jogador, dk.arq)}` + (dk.faltam ? ` ⚠ ${t('warn')}` : ''); s.appendChild(o); });
    $('carregar').disabled = !tn;
  }
  $('torneio').onchange = preencherDecks;
  $('carregar').onclick = () => {
    const tn = TORNEIOS[$('torneio').value], dk = tn && tn.decks[$('deck').value];
    if (!dk) return;
    substituir(new Map(dk.cartas));
    const total = dk.cartas.reduce((a, [, n]) => a + n, 0);
    msg('msgImp', t('loaded')(total) + (dk.faltam ? '\n' + t('missing')(dk.faltam.join('\n')) : ''), dk.faltam ? 'err' : 'ok');
  };
  $('importar').onclick = () => {
    const { cont, faltam } = parseLista($('texto').value);
    if (cont.size) substituir(cont);
    const total = [...cont.values()].reduce((a, n) => a + n, 0);
    msg('msgImp', (cont.size ? t('imported')(total) : '') + (faltam.length ? '\n' + t('missing')(faltam.join('\n')) : ''), faltam.length ? 'err' : 'ok');
  };
  $('limpar').onclick = () => { lista.clear(); salvar(); render(); };
  function msg(id, texto, cls) { const e = $(id); e.className = cls || ''; e.style.whiteSpace = 'pre-wrap'; e.style.marginTop = '8px'; e.textContent = texto; }

  // ------------------------------------------------------------ PDF
  function opcoes() {
    const papel = $('papel').value === 'custom' ? $('custom').value : $('papel').value;
    return { idioma: $('idioma').value, papel, escala: (parseFloat($('escala').value) || 0) / 100, margem: parseFloat($('margem').value) || 0, espaco: parseFloat($('espaco').value) || 0 };
  }
  const ERROS = { paper: 'e_paper', scale: 'e_scale', fit: 'e_fit', empty: 'e_empty' };
  function atualizarInfo() {
    try { const L = PTCGPdf.layout(opcoes().papel, opcoes().escala, opcoes().margem, opcoes().espaco); const n = [...lista.values()].reduce((a, b) => a + b, 0);
      $('info').textContent = t('pages')(Math.max(1, Math.ceil(n / L.porPagina)), L.porPagina, L.cols, L.lins); $('info').className = 'mut';
    } catch (e) { $('info').textContent = t(ERROS[e.message] || 'e_fit'); $('info').className = 'err'; }
  }
  $('gerar').onclick = () => {
    try {
      const cartas = []; ordenadas().forEach(d => { for (let i = 0; i < lista.get(d.id); i++) cartas.push(d); });
      const r = PTCGPdf.gerar(cartas, opcoes());
      r.doc.save('proxies.pdf');
      msg('msgPdf', t('done')(cartas.length, r.paginas), 'ok');
    } catch (e) { msg('msgPdf', t(ERROS[e.message]) || String(e), 'err'); }
  };
  const PAPEIS = { A4: 'A4 (210 × 297 mm)', Office: 'Office / Ofício (216 × 330 mm)', A5: 'A5 (148 × 210 mm)', Letter: 'Letter (216 × 279 mm)', Legal: 'Legal (216 × 356 mm)', A3: 'A3 (297 × 420 mm)' };
  Object.entries(PAPEIS).forEach(([k, v]) => { const o = document.createElement('option'); o.value = k; o.textContent = v; $('papel').appendChild(o); });
  const oc = document.createElement('option'); oc.value = 'custom'; oc.textContent = '…'; $('papel').appendChild(oc);
  $('papel').onchange = () => { $('lblCustom').hidden = $('papel').value !== 'custom'; atualizarInfo(); };
  ['custom', 'escala', 'margem', 'espaco'].forEach(id => $(id).addEventListener('input', atualizarInfo));
  $('idioma').onchange = () => { idiomaPdfManual = $('idioma').value; store.set('ptcg_pdflang', idiomaPdfManual); };

  // ------------------------------------------------------------ idioma da página, café, aviso
  function aplicarIdioma() {
    document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en';
    document.querySelectorAll('[data-i]').forEach(e => { e.textContent = t(e.dataset.i); });
    document.querySelectorAll('#langPage button').forEach(b => b.classList.toggle('on', b.dataset.l === lang));
    busca.placeholder = t('search_ph');
    $('idioma').value = idiomaPdfManual || lang;
    $('disclaimer').textContent = t('disclaimer');
    const cafe = $('cafe'); cafe.textContent = '';
    if (PIX_KEY || KOFI_URL) {
      const w = document.createElement('span'); w.className = 'pix';
      const txt = document.createElement('span'); txt.textContent = '☕ ' + t('cafe');
      w.appendChild(txt);
      const kofi = () => {
        if (!KOFI_URL) return;
        const a = document.createElement('a'); a.className = 'btn'; a.style.padding = '2px 10px'; a.style.textDecoration = 'none';
        a.href = KOFI_URL; a.target = '_blank'; a.rel = 'noopener'; a.textContent = t('kofi'); w.appendChild(a);
      };
      const pix = () => {
        if (!PIX_KEY) return;
        const rot = document.createElement('span'); rot.className = 'mut'; rot.textContent = t('pix') + ':';
        const code = document.createElement('code'); code.textContent = PIX_KEY;
        const b = document.createElement('button'); b.className = 'btn'; b.style.padding = '2px 10px'; b.textContent = t('copy');
        b.onclick = () => { (navigator.clipboard ? navigator.clipboard.writeText(PIX_KEY) : Promise.reject()).then(() => { b.textContent = t('copied'); setTimeout(() => { b.textContent = t('copy'); }, 1500); }, () => { const r = document.createRange(); r.selectNodeContents(code); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }); };
        w.append(rot, code, b);
      };
      (lang === 'pt' ? [pix, kofi] : [kofi, pix]).forEach(f => f());   // Pix primeiro em português; Ko-fi primeiro em inglês
      cafe.appendChild(w);
    }
    document.title = 'PTCG Lab — ' + t('title');
    preencherTorneios(); render();
  }
  document.querySelectorAll('#langPage button').forEach(b => { b.onclick = () => { lang = b.dataset.l; store.set('ptcg_lang', lang); aplicarIdioma(); }; });
  aplicarIdioma();
})();
