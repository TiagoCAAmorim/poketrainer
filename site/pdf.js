/* Gerador do PDF de cartas simplificadas (texto, preto e branco). Port de ptcg/imprimir.py (reportlab → jsPDF).
   Unidades: o desenho da carta usa o espaço de 63×88 mm em pontos, com y para cima, como no original. */
(function () {
  'use strict';
  const MM = 72 / 25.4;
  const CARTA_MM = [63, 88];
  const PAPEIS = { A4: [210, 297], Office: [216, 330], A5: [148, 210], Letter: [215.9, 279.4], Legal: [215.9, 355.6], A3: [297, 420] };
  const ESCALA_MIN = 20, ESCALA_MAX = 150;

  const L10N = {
    pt: {
      basic: 'Básico', s1: 'Fase 1', s2: 'Fase 2', from: 'evolui de',
      cat: { p: 'POKÉMON', supporter: 'APOIADOR', item: 'ITEM', tool: 'FERRAMENTA', stadium: 'ESTÁDIO', e: 'ENERGIA' }, basicE2: 'Básica', specialE2: 'Especial', hp: 'PS',
      trainer: 'Treinador', sub: { supporter: 'Apoiador', item: 'Item', tool: 'Ferramenta Pokémon', stadium: 'Estádio' },
      basicE: 'Energia Básica', specialE: 'Energia Especial', provides: t => `Fornece Energia de ${t}.`,
      weak: 'Fraqueza', res: 'Resistência', retreat: 'Recuo', abil: 'HAB', foot: 'cópia para teste', ace: ' · ACE SPEC',
      tipos: { G: 'Planta', R: 'Fogo', W: 'Água', L: 'Elétrico', P: 'Psíquico', F: 'Lutador', D: 'Escuridão', M: 'Metal', N: 'Dragão', C: 'Incolor', Y: 'Fada' }
    },
    en: {
      basic: 'Basic', s1: 'Stage 1', s2: 'Stage 2', from: 'evolves from',
      cat: { p: 'POKÉMON', supporter: 'SUPPORTER', item: 'ITEM', tool: 'TOOL', stadium: 'STADIUM', e: 'ENERGY' }, basicE2: 'Basic', specialE2: 'Special', hp: 'HP',
      trainer: 'Trainer', sub: { supporter: 'Supporter', item: 'Item', tool: 'Pokémon Tool', stadium: 'Stadium' },
      basicE: 'Basic Energy', specialE: 'Special Energy', provides: t => `Provides ${t} Energy.`,
      weak: 'Weakness', res: 'Resistance', retreat: 'Retreat', abil: 'ABILITY', foot: 'playtest copy', ace: ' · ACE SPEC',
      tipos: { G: 'Grass', R: 'Fire', W: 'Water', L: 'Lightning', P: 'Psychic', F: 'Fighting', D: 'Darkness', M: 'Metal', N: 'Dragon', C: 'Colorless', Y: 'Fairy' }
    }
  };

  // ---------------------------------------------------------------- papel e layout
  function tamanhoPapel(papel) {
    let w, h;
    const s = String(papel || 'A4').trim();
    const k = Object.keys(PAPEIS).find(x => x.toLowerCase() === s.toLowerCase());
    if (k) [w, h] = PAPEIS[k];
    else {
      const m = s.match(/^(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)(?:\s*mm)?$/i);
      if (!m) throw new Error('paper');
      w = parseFloat(m[1].replace(',', '.')); h = parseFloat(m[2].replace(',', '.'));
    }
    if (Math.min(w, h) < 40) throw new Error('paper');
    return [Math.min(w, h), Math.max(w, h)];
  }

  function layout(papel, escala, margem, espaco) {
    if (!(ESCALA_MIN / 100 <= escala && escala <= ESCALA_MAX / 100)) throw new Error('scale');
    const [pw, ph] = tamanhoPapel(papel);
    const cw = CARTA_MM[0] * escala, ch = CARTA_MM[1] * escala;
    let melhor = null;
    for (const [nome, W, H] of [['p', pw, ph], ['l', ph, pw]]) {
      const cols = Math.floor((W - 2 * margem + espaco + 1e-6) / (cw + espaco));
      const lins = Math.floor((H - 2 * margem + espaco + 1e-6) / (ch + espaco));
      if (cols > 0 && lins > 0 && (!melhor || cols * lins > melhor.cols * melhor.lins)) melhor = { o: nome, W, H, cols, lins };
    }
    if (!melhor) throw new Error('fit');
    return Object.assign(melhor, { porPagina: melhor.cols * melhor.lins, cw, ch });
  }

  // ---------------------------------------------------------------- texto
  function lat(s) {
    s = (s || '').replace(/[’‘]/g, "'").replace(/[“”]/g, '"').replace(/[–—]/g, '-').replace(/•/g, '*').replace(/→/g, '->')
      .replace(/♀/g, '(F)').replace(/♂/g, '(M)').replace(/\n/g, ' ');
    return s.replace(/[^\x00-\xff]/g, '?');
  }

  const FONTES = { 'Helvetica': ['helvetica', 'normal'], 'Helvetica-Bold': ['helvetica', 'bold'], 'Helvetica-Oblique': ['helvetica', 'italic'] };

  // contexto de desenho de uma carta: origem (ox, oy) no topo-esquerdo da página, escala s, altura base alt
  function contexto(doc, ox, oy, s, alt) {
    const X = x => ox + x * s, Y = y => oy + (alt - y) * s;
    const c = {
      lw: w => doc.setLineWidth(w * s),
      font(f, size) { const [a, b] = FONTES[f]; doc.setFont(a, b); doc.setFontSize(size * s); },
      sw(txt, f, size) { const [a, b] = FONTES[f]; doc.setFont(a, b); return doc.getStringUnitWidth(txt) * size; },
      roundRect: (x, y, w, h, r) => doc.roundedRect(X(x), Y(y + h), w * s, h * s, r * s, r * s, 'S'),
      rect: (x, y, w, h) => doc.rect(X(x), Y(y + h), w * s, h * s, 'S'),
      line: (x1, y1, x2, y2) => doc.line(X(x1), Y(y1), X(x2), Y(y2)),
      circle: (x, y, r, st) => doc.circle(X(x), Y(y), r * s, st || 'S'),
      cor(v) { doc.setFillColor(v); doc.setDrawColor(v); },
      poly(pts, st) {   // polígono fechado; st: 'F' preenche, 'S' contorno
        const q = pts.map(([x, y]) => [X(x), Y(y)]);
        doc.lines(q.slice(1).map((p, i) => [p[0] - q[i][0], p[1] - q[i][1]]), q[0][0], q[0][1], [1, 1], st || 'F', true);
      },
      text: (t, x, y, align) => doc.text(t, X(x), Y(y), { align: align || 'left' }),
      split(texto, f, size, largura) {
        texto = lat(texto);
        if (!texto) return [];
        const linhas = []; let atual = '';
        for (const w of texto.split(/\s+/).filter(Boolean)) {
          const t = atual ? atual + ' ' + w : w;
          if (atual && c.sw(t, f, size) > largura) { linhas.push(atual); atual = w; } else atual = t;
        }
        if (atual) linhas.push(atual);
        return linhas;
      }
    };
    doc.setDrawColor(0); doc.setTextColor(0);
    return c;
  }


  // ---------------------------------------------------------------- ícones de tipo (preto e branco, vetoriais)
  // Cada glifo é desenhado em coordenadas -1..1 (y para cima) dentro de um círculo.
  function estrela(n, ri) {
    const p = [];
    for (let i = 0; i < 2 * n; i++) { const a = Math.PI / 2 + i * Math.PI / n, r = i % 2 ? ri : 1; p.push([r * Math.cos(a), r * Math.sin(a)]); }
    return p;
  }
  function lente(a, b, n, larg, vert) {   // forma de folha/olho entre os pontos a e b
    const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy), nx = -dy / len, ny = dx / len, lado = (sg) => {
      const r = [];
      for (let i = 0; i <= n; i++) { const t = i / n, w = sg * larg * Math.pow(Math.sin(Math.PI * t), vert || 1); r.push([a[0] + dx * t + nx * w, a[1] + dy * t + ny * w]); }
      return r;
    };
    return lado(1).concat(lado(-1).reverse().slice(1, -1));
  }
  const GLIFOS = {
    R(g) { g.f([[0.1, 1], [0.55, 0.3], [0.8, -0.25], [0.5, -0.85], [0, -1], [-0.5, -0.85], [-0.8, -0.25], [-0.45, 0.2], [-0.25, -0.15], [-0.2, 0.45]]); g.b(0, -0.5, 0.28); },
    W(g) { g.f([[0, 1], [-0.6, -0.05], [0.6, -0.05]]); g.c(0, -0.35, 0.65); },
    L(g) { g.f([[0.25, 1], [-0.55, -0.1], [-0.05, -0.1], [-0.25, -1], [0.55, 0.15], [0.05, 0.15]]); },
    G(g) { g.f(lente([-0.8, -0.8], [0.8, 0.8], 10, 0.55, 0.8)); g.bl([-0.95, -0.95], [0.55, 0.55]); },
    P(g) { g.s(lente([-1, 0], [1, 0], 12, 0.6, 0.9)); g.c(0, 0, 0.3); },
    F(g) { g.f([[-0.8, -0.5], [-0.5, 0.5], [0.1, 0.85], [0.8, 0.3], [0.7, -0.6], [0, -0.85]]); g.bl([-0.2, 0.5], [0.05, -0.1]); g.bl([0.05, -0.1], [0.45, -0.25]); },
    D(g) { g.c(0, 0, 0.85); g.b(0.42, 0.28, 0.72); },
    M(g) { g.f(estrela(6, 0.87)); g.b(0, 0, 0.34); },
    N(g) { g.f([[0, 1], [0.7, 0], [0, -1], [-0.7, 0]]); g.bp([[0, 0.5], [0.3, 0], [0, -0.5], [-0.3, 0]]); },
    C(g) { g.f(estrela(5, 0.42)); },
    Y(g) { g.f(estrela(4, 0.27)); }
  };

  // desenha o ícone do tipo `t` com centro (x, y) e raio externo R; sem cor (preto e branco)
  function icone(c, t, x, y, R) {
    const u = R * 0.72, P = pts => pts.map(([a, b]) => [x + a * u, y + b * u]);
    c.lw(Math.max(0.4, R * 0.09)); c.cor(0);
    c.circle(x, y, R, 'S');
    const g = {
      f: pts => { c.cor(0); c.poly(P(pts), 'F'); },
      s: pts => { c.cor(0); c.lw(Math.max(0.5, R * 0.13)); c.poly(P(pts), 'S'); },
      c: (a, b, r) => { c.cor(0); c.circle(x + a * u, y + b * u, r * u, 'F'); },
      b: (a, b, r) => { c.cor(255); c.circle(x + a * u, y + b * u, r * u, 'F'); c.cor(0); },
      bp: pts => { c.cor(255); c.poly(P(pts), 'F'); c.cor(0); },
      bl: (p1, p2) => { c.cor(255); c.lw(Math.max(0.5, R * 0.1)); c.line(x + p1[0] * u, y + p1[1] * u, x + p2[0] * u, y + p2[1] * u); c.cor(0); }
    };
    (GLIFOS[t] || GLIFOS.C)(g);
    c.cor(0);
  }

  function custo(c, x, y, cst, r) {
    for (const t of cst) {
      icone(c, t, x + r, y + r * 0.35, r);
      x += 2 * r + 1.2;
    }
    return x;
  }

  // textos de uma carta no idioma: nome, texto, habilidades [[nome, texto]], ataques [[nome, texto]]
  function textos(d, idioma) {
    const t = d[idioma] || d.en;
    const abN = (idioma === 'pt' && d.abp) ? d.abp : (d.ab || []).map(a => a[0]);
    const atN = (idioma === 'pt' && d.atp) ? d.atp : (d.at || []).map(a => a[0]);
    return {
      nome: d.n, nomePt: idioma === 'pt' ? (d.p || '') : '', texto: t[0],
      ab: abN.map((n, i) => [n, t[1][i] || '']), at: atN.map((n, i) => [n, t[2][i] || ''])
    };
  }

  function cartaSimplificada(c, d, idioma, larg, alt) {
    const S = L10N[idioma], T = textos(d, idioma);
    const m = 7.0, iw = larg - 2 * m;
    c.lw(1.2); c.roundRect(0.6, 0.6, larg - 1.2, alt - 1.2, 8);
    c.lw(0.4); c.roundRect(4, 4, larg - 8, alt - 8, 5);
    let y = alt - m - 9, tag = '', sub = '', hp = '';
    const tipo = t => S.tipos[t] || t;
    if (d.k === 'p') {
      tag = S.cat.p;
      sub = [S.basic, S.s1, S.s2][d.s] + (d.f ? ` · ${S.from} ${d.f}` : '');
      hp = `${S.hp} ${d.h}`;
    } else if (d.k === 't') { tag = S.cat[d.st] || S.trainer.toUpperCase(); sub = d.a ? S.ace.replace(' · ', '') : ''; }
    else { tag = S.cat.e; sub = d.b ? S.basicE2 : S.specialE2; }
    // cabeçalho: nome, ícone(s) de tipo e PS
    const R = 5.2, nIc = d.k === 'p' ? d.t.length : 0;
    const wIc = nIc ? nIc * (2 * R + 1.5) : 0;
    const wHp = hp ? c.sw(hp, 'Helvetica-Bold', 9) + 5 : 0;
    let tam = 11.0;
    const wmax = iw - wHp - wIc - 2;
    while (tam > 6 && c.sw(lat(T.nome), 'Helvetica-Bold', tam) > wmax) tam -= 0.5;
    c.font('Helvetica-Bold', tam); c.text(lat(T.nome), m, y);
    if (hp) { c.font('Helvetica-Bold', 9); c.text(hp, larg - m, y, 'right'); }
    d.k === 'p' && d.t.forEach((t, i) => icone(c, t, larg - m - wHp - R - i * (2 * R + 1.5) - 1, y + 3.1, R));
    y -= 9.6;
    // linha da categoria: [POKÉMON] Fase 2 · evolui de X
    c.font('Helvetica-Bold', 5.8);
    const wt = c.sw(tag, 'Helvetica-Bold', 5.8) + 5;
    c.lw(0.5); c.rect(m, y - 1.7, wt, 7.4); c.text(tag, m + 2.5, y);
    c.font('Helvetica-Oblique', 5.8);
    const ls = c.split(sub, 'Helvetica-Oblique', 5.8, iw - wt - 4);
    if (ls.length) c.text(ls[0], m + wt + 4, y);
    y -= 6.6;
    for (const ln of ls.slice(1)) { c.text(ln, m, y); y -= 6.4; }
    if (T.nomePt && T.nomePt !== T.nome) { c.font('Helvetica', 5.8); c.text(lat(`(${T.nomePt})`), m, y); y -= 6.4; }
    y -= 1.5;
    c.lw(0.5); c.line(m, y, larg - m, y);
    const topo = y - 4, base = 22.0;
    const blocos = [];
    if (d.k === 'p') {
      for (const [n, t] of T.ab) blocos.push(['hab', n, [], '', t]);
      d.at.forEach((a, i) => blocos.push(['atq', T.at[i][0], a[1], a[2], T.at[i][1]]));
    } else if (T.texto) blocos.push(['txt', '', [], '', T.texto]);
    if (d.k === 'e' && !T.texto) blocos.push(['txt', '', [], '', S.provides(tipo(d.pv))]);
    if (d.k === 'p' && T.texto) blocos.push(['txt', '', [], '', T.texto]);

    if (d.k === 'e' && d.b && d.pv) icone(c, d.pv, larg / 2, base + (topo - base) * 0.62, 24);
    const montar = tam => {
      const linhas = []; let h = 0;
      for (const [tp, nome, cst, dano, texto] of blocos) {
        const ltxt = c.split(texto, 'Helvetica', tam, iw);
        h += (tp !== 'txt' ? tam * 1.35 : 0) + ltxt.length * tam * 1.2 + tam * 0.9;
        linhas.push([tp, nome, cst, dano, ltxt, tam * 0.7]);
      }
      return [linhas, h];
    };
    tam = 8.2;
    let linhas, h;
    for (;;) { [linhas, h] = montar(tam); if (h <= topo - base || tam <= 4.2) break; tam -= 0.2; }
    let yy = topo;
    for (const [tp, nome, cst, dano, ltxt, r] of linhas) {
      if (tp !== 'txt') {
        yy -= tam * 1.1;
        let x = m;
        if (tp === 'hab') {
          c.font('Helvetica-Bold', tam); c.lw(0.5);
          const w = c.sw(S.abil, 'Helvetica-Bold', tam);
          c.rect(x, yy - 1, w + 4, tam + 1.5); c.text(S.abil, x + 2, yy);
          x += w + 8;
        } else x = custo(c, x, yy - 0.5, cst, r) + 2;
        c.font('Helvetica-Bold', tam + 0.6); c.text(lat(nome), x, yy);
        if (dano) c.text(lat(dano), larg - m, yy, 'right');
        yy -= tam * 0.25;
      }
      c.font('Helvetica', tam);
      for (const ln of ltxt) { yy -= tam * 1.2; c.text(ln, m, yy); }
      yy -= tam * 0.9;
    }
    c.lw(0.5); c.line(m, base - 2, larg - m, base - 2);
    c.font('Helvetica', 6);
    if (d.k === 'p') {
      const r = 3.5, yb = base - 10;
      // "Fraqueza: [ícone] ×2" | "Resistência: [ícone] -30" | "Recuo: [ícones]"
      const grupo = (x0, rot, tp, suf) => {
        c.font('Helvetica', 6); c.text(lat(rot + ':'), x0, yb);
        let x = x0 + c.sw(lat(rot + ':'), 'Helvetica', 6) + 2;
        if (tp) { icone(c, tp, x + r, yb + 2, r); x += 2 * r + 2; c.font('Helvetica', 6); c.text(lat(suf), x, yb); } else c.text('-', x, yb);
      };
      grupo(m, S.weak, d.w, '×2');
      const wRes = c.sw(lat(S.res + ':'), 'Helvetica', 6) + 2 + (d.r ? 2 * r + 2 + c.sw(lat(`-${d.rv}`), 'Helvetica', 6) : 4);
      grupo(larg / 2 + 4 - wRes / 2, S.res, d.r, d.r ? `-${d.rv}` : '');
      const nr = d.rt, wRec = c.sw(lat(S.retreat + ':'), 'Helvetica', 6) + 2 + (nr ? nr * (2 * r + 1.2) : 4);
      const xr = larg - m - wRec;
      c.font('Helvetica', 6); c.text(lat(S.retreat + ':'), xr, yb);
      let x = xr + c.sw(lat(S.retreat + ':'), 'Helvetica', 6) + 2;
      if (nr) for (let i = 0; i < nr; i++) { icone(c, 'C', x + r, yb + 2, r); x += 2 * r + 1.2; } else c.text('-', x, yb);
    }
    c.font('Helvetica', 5);
    c.text(lat(d.id.replace('-', ' ')), m, 6.5);
    c.text(S.foot, larg - m, 6.5, 'right');
  }

  /* cartas: lista de objetos de carta (com .id), uma por cópia. Devolve {doc, paginas, porPagina, colunas, linhas}. */
  function gerar(cartas, { idioma = 'pt', papel = 'A4', escala = 0.9, margem = 6, espaco = 1 } = {}) {
    if (!cartas.length) throw new Error('empty');
    const L = layout(papel, escala, margem, espaco);
    const { jsPDF } = window.jspdf;
    const orient = L.W > L.H ? 'l' : 'p';
    const doc = new jsPDF({ unit: 'pt', format: [Math.min(L.W, L.H) * MM, Math.max(L.W, L.H) * MM], orientation: orient, compress: true });
    doc.setProperties({ title: 'Playtest cards', author: 'PTCG Lab' });
    const cw = L.cw * MM, ch = L.ch * MM, gap = espaco * MM, PW = L.W * MM, PH = L.H * MM;
    const gx = (PW - (L.cols * cw + (L.cols - 1) * gap)) / 2;
    const gy = (PH - (L.lins * ch + (L.lins - 1) * gap)) / 2;
    const bw = CARTA_MM[0] * MM, bh = CARTA_MM[1] * MM;
    let paginas = 0;
    cartas.forEach((d, i) => {
      const pos = i % L.porPagina;
      if (pos === 0) { if (i) doc.addPage([Math.min(PW, PH), Math.max(PW, PH)], orient); paginas++; }
      const col = pos % L.cols, lin = Math.floor(pos / L.cols);
      const c = contexto(doc, gx + col * (cw + gap), gy + lin * (ch + gap), cw / bw, bh);
      cartaSimplificada(c, d, idioma, bw, bh);
    });
    return { doc, paginas, porPagina: L.porPagina, colunas: L.cols, linhas: L.lins, orientacao: L.o };
  }

  window.PTCGPdf = { gerar, layout, PAPEIS, ESCALA_MIN, ESCALA_MAX };
})();
