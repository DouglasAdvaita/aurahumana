    // INFORME PDF — gráfico P1 + ficha básica
    (function(){
        const btn=document.getElementById('btn-informe');
        const est=document.getElementById('informe-estado');
        if(!btn) return;
        function setEst(t, err){ if(est){ est.textContent=t; est.style.color=err?'#c62828':'var(--muted)'; } }
        async function capturePng(){
            const box=document.getElementById('svg-persona-a');
            if(!box) return '';
            const svg=box.querySelector('svg');
            if(!svg) return '';
            try{
                const clone=svg.cloneNode(true);
                clone.setAttribute('xmlns','http://www.w3.org/2000/svg');
                const s=new XMLSerializer().serializeToString(clone);
                const blob=new Blob([s],{type:'image/svg+xml;charset=utf-8'});
                const url=URL.createObjectURL(blob);
                const img=new Image();
                img.decoding='sync';
                const loaded=await new Promise((res,rej)=>{ img.onload=()=>res(true); img.onerror=()=>rej(new Error('img load')); img.src=url; });
                const w=svg.viewBox && svg.viewBox.baseVal && svg.viewBox.baseVal.width ? svg.viewBox.baseVal.width : (svg.clientWidth||800);
                const h=svg.viewBox && svg.viewBox.baseVal && svg.viewBox.baseVal.height ? svg.viewBox.baseVal.height : (svg.clientHeight||800);
                const scale=2;
                const canvas=document.createElement('canvas');
                canvas.width=Math.max(1,Math.round(w*scale));
                canvas.height=Math.max(1,Math.round(h*scale));
                const ctx=canvas.getContext('2d');
                ctx.fillStyle='#ffffff'; ctx.fillRect(0,0,canvas.width,canvas.height);
                ctx.drawImage(img,0,0,canvas.width,canvas.height);
                URL.revokeObjectURL(url);
                return canvas.toDataURL('image/png');
            }catch(e){ return ''; }
        }
        async function capturarSvgRaw(){
            try{ const box=document.getElementById('svg-persona-a'); const svg=box&&box.querySelector('svg'); return svg? new XMLSerializer().serializeToString(svg):''; }catch(e){ return ''; }
        }
        btn.addEventListener('click', async ()=>{
            const sel=document.getElementById('selector-persona-a');
            const persona=(sel&&sel.value||'').trim();
            if(!persona){ setEst('Elegí Persona 1 primero.', true); return; }
            btn.disabled=true; setEst('Generando PDF…');
            try{
                const png=await capturePng();
                const svg=png? '' : await capturarSvgRaw();
                const r=await fetch('/api/informe_pdf',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({persona, png, svg})});
                if(!r.ok){
                    const j=await r.json().catch(()=>({error: r.statusText}));
                    throw new Error(j.error||('HTTP '+r.status));
                }
                const blob=await r.blob();
                const cd=r.headers.get('Content-Disposition')||'';
                let fname='Informe-'+persona.replace(/\s+/g,'_')+'.pdf';
                const m=cd.match(/filename="?([^"]+)"?/); if(m) fname=m[1];
                const url=URL.createObjectURL(blob);
                const a=document.createElement('a'); a.href=url; a.download=fname; document.body.appendChild(a); a.click();
                setTimeout(()=>{ URL.revokeObjectURL(url); a.remove(); }, 2000);
                setEst('PDF descargado en Descargas — '+fname);
            }catch(err){ setEst('Error: '+err.message, true); }
            finally{ btn.disabled=false; }
        });
    })();
    /* ===== CLAN aislado: no toca A/B/compuesto/adicionales. Todo prefijo clan-. ===== */
    (function(){
        if (document.getElementById('clan-fila-abuelos').dataset.clanInit) return;
        document.getElementById('clan-fila-abuelos').dataset.clanInit = '1';
        var COLORES = { p1:'#2E7D32', padre:'#29B6F6', madre:'#F06292', ap_abuelo:'#1565C0', ap_abuela:'#7B1FA2', am_abuela:'#E53935', am_abuelo:'#FB8C00', pareja:'#795548' };
        var HERMANO_COLORES = ['#FDD835','#FFE0B2','#DCE775','#CE93D8','#F8BBD0','#B3E5FC'];
        var HIJO_COLORES = ['#66BB6A','#43A047','#81C784','#388E3C','#A5D6A7','#1B5E20'];
        // Gris mezclado con el color del abuelo (bisabuelos = tonos de gris con color de su rama).
        function grisCon(hex, t){
            var g = [158,158,158];
            var m = String(hex||'#9E9E9E').replace('#','');
            var rr = parseInt(m.substr(0,2),16), vv = parseInt(m.substr(2,2),16), aa = parseInt(m.substr(4,2),16);
            if (isNaN(rr)||isNaN(vv)||isNaN(aa)) return '#9E9E9E';
            function mix(i, c){ return Math.round(g[i]*(1-t) + c*t); }
            function h2(n){ n = Math.max(0, Math.min(255, n)).toString(16); return n.length<2 ? '0'+n : n; }
            return '#'+h2(mix(0,rr))+h2(mix(1,vv))+h2(mix(2,aa));
        }
        // 8 bisabuelos, en el mismo orden que los abuelos de la fila de abajo.
        var FIJOS_BISABUELOS = [
            {etiqueta:'Bisabuelo pat. A', base:'#1565C0', t:0.28, titulo:'Padre del abuelo paterno'},
            {etiqueta:'Bisabuela pat. A', base:'#1565C0', t:0.52, titulo:'Madre del abuelo paterno'},
            {etiqueta:'Bisabuelo pat. B', base:'#7B1FA2', t:0.28, titulo:'Padre de la abuela paterna'},
            {etiqueta:'Bisabuela pat. B', base:'#7B1FA2', t:0.52, titulo:'Madre de la abuela paterna'},
            {etiqueta:'Bisabuelo mat. A', base:'#E53935', t:0.28, titulo:'Padre de la abuela materna'},
            {etiqueta:'Bisabuela mat. A', base:'#E53935', t:0.52, titulo:'Madre de la abuela materna'},
            {etiqueta:'Bisabuelo mat. B', base:'#FB8C00', t:0.28, titulo:'Padre del abuelo materno'},
            {etiqueta:'Bisabuela mat. B', base:'#FB8C00', t:0.52, titulo:'Madre del abuelo materno'}
        ];
        var FIJOS_ABUELOS = [
            {id:'ap_abuelo', etiqueta:'Abuelo paterno'},
            {id:'ap_abuela', etiqueta:'Abuela paterna'},
            {id:'am_abuela', etiqueta:'Abuela materna'},
            {id:'am_abuelo', etiqueta:'Abuelo materno'}
        ];
        var FIJOS_PADRES = [
            {id:'padre', etiqueta:'Padre'},
            {id:'madre', etiqueta:'Madre'}
        ];
        var S = { miembros:{}, mayores:[], menores:[], parejas:[], bisabuelos:[], hijos:[] };
        ['ap_abuelo','ap_abuela','am_abuela','am_abuelo','padre','madre','p1','pareja'].forEach(function(k){ S.miembros[k]={nombre:'',data:null,foto:'',overlays:[]}; });
        var uidN = 0;
        var CLAN_MEM_KEY = 'rave_clan_v1';
        function claveLocalP1(p1){ return 'rave_clan_P1_' + String(p1||'').toLowerCase(); }
        function memoriaDeS(){
            var m = {};
            Object.keys(S.miembros).forEach(function(k){ m[k] = S.miembros[k].nombre || ''; });
            (S.bisabuelos||[]).forEach(function(h){ if (h && h.nombre) m['bis_'+(h.slot+1)] = h.nombre; });
            return { v:3, m:m,
                mayores:(S.mayores||[]).map(function(h){ return h.nombre||''; }),
                menores:(S.menores||[]).map(function(h){ return h.nombre||''; }),
                parejas:(S.parejas||[]).map(function(h){ return h.nombre||''; }),
                hijos:(S.hijos||[]).map(function(h){ return h.nombre||''; }) };
        }
        function cargarBisabuelosDeM(m){
            S.bisabuelos.length = 0;
            for (var i=0;i<8;i++){
                var n = (m && m['bis_'+(i+1)]) ? String(m['bis_'+(i+1)]).trim() : '';
                if (n) S.bisabuelos.push({uid:++uidN, slot:i, nombre:n, data:null, foto:'', overlays:[]});
            }
        }
        function cargarHijosDeLista(lista){
            S.hijos.length = 0;
            (lista||[]).forEach(function(n){ if(String(n||'').trim()) S.hijos.push({uid:++uidN, nombre:n||'', data:null, foto:'', overlays:[]}); });
        }
        function aplicarMemoriaClan(mem, conservarP1){
            var p1keep = S.miembros.p1.nombre || '';
            try{
                Object.keys(S.miembros).forEach(function(k){
                    if (conservarP1 && k==='p1') return;
                    if (mem.m && mem.m[k]) S.miembros[k].nombre = mem.m[k];
                    else if (!conservarP1 || (k!=='p1')) { if (S.miembros[k] && !mem.m) S.miembros[k].nombre = ''; }
                });
                ['ap_abuelo','ap_abuela','am_abuela','am_abuelo','padre','madre','pareja'].forEach(function(k){
                    if (!mem.m || !mem.m[k]) S.miembros[k].nombre = '';
                });
                S.mayores.length = 0; S.menores.length = 0; (S.parejas||[]).length = 0;
                (mem.mayores||[]).forEach(function(n){ if(String(n||'').trim()) S.mayores.push({uid:++uidN, nombre:n||'', data:null, foto:'', overlays:[]}); });
                (mem.menores||[]).forEach(function(n){ if(String(n||'').trim()) S.menores.push({uid:++uidN, nombre:n||'', data:null, foto:'', overlays:[]}); });
                (mem.parejas||[]).forEach(function(n){ if(String(n||'').trim()) S.parejas.push({uid:++uidN, nombre:n||'', data:null, foto:'', overlays:[]}); });
                cargarBisabuelosDeM(mem.m);
                cargarHijosDeLista(mem.hijos);
                Object.keys(S.miembros).forEach(function(k){ S.miembros[k].data = null; S.miembros[k].overlays = []; });
                if (conservarP1) S.miembros.p1.nombre = p1keep;
            }catch(e){}
        }
        function guardarClan(){
            try{
                var mem = memoriaDeS();
                localStorage.setItem(CLAN_MEM_KEY, JSON.stringify(mem));
                var p1 = S.miembros.p1.nombre || '';
                if (p1) try{ localStorage.setItem(claveLocalP1(p1), JSON.stringify(mem)); }catch(e2){}
            }catch(e){}
            try{
                var p1n = S.miembros.p1.nombre || '';
                if (!p1n) return;
                var mem2 = memoriaDeS();
                fetch('/api/clan', {method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({p1:p1n, m:mem2.m, mayores:mem2.mayores, menores:mem2.menores, parejas:mem2.parejas, hijos:mem2.hijos})}).catch(function(){});
            }catch(e){}
        }
        function cargarMemoriaClan(){
            var mem = null;
            try{ mem = JSON.parse(localStorage.getItem(CLAN_MEM_KEY) || 'null'); }catch(e){ mem = null; }
            if (!mem) return;
            try{
                Object.keys(S.miembros).forEach(function(k){ if (mem.m && mem.m[k]) S.miembros[k].nombre = mem.m[k]; });
                (mem.mayores||[]).forEach(function(n){ S.mayores.push({uid:++uidN, nombre:n||'', data:null, foto:'', overlays:[]}); });
                (mem.menores||[]).forEach(function(n){ S.menores.push({uid:++uidN, nombre:n||'', data:null, foto:'', overlays:[]}); });
                (mem.parejas||[]).forEach(function(n){ S.parejas.push({uid:++uidN, nombre:n||'', data:null, foto:'', overlays:[]}); });
                cargarBisabuelosDeM(mem.m);
                cargarHijosDeLista(mem.hijos);
            }catch(e){}
        }
        function nombresDelClan(){
            var ns = [];
            try{
                Object.keys(S.miembros).forEach(function(k){ if (S.miembros[k] && S.miembros[k].nombre) ns.push(S.miembros[k].nombre); });
                S.mayores.concat(S.menores).concat(S.parejas||[]).concat(S.bisabuelos||[]).concat(S.hijos||[]).forEach(function(h){ if (h && h.nombre) ns.push(h.nombre); });
            }catch(e){}
            return Array.from(new Set(ns.filter(function(n){ return String(n||'').trim(); })));
        }
        function aplicarDatosCacheados(){
            try{
                Object.keys(S.miembros).forEach(function(k){ var e=S.miembros[k]; if (e && e.nombre && _clanCache[e.nombre]) e.data = _clanCache[e.nombre]; });
                S.mayores.concat(S.menores).concat(S.parejas||[]).concat(S.bisabuelos||[]).concat(S.hijos||[]).forEach(function(h){ if (h && h.nombre && _clanCache[h.nombre]) h.data = _clanCache[h.nombre]; });
            }catch(e){}
        }
        function renderClanPorPartes(done){
            // Pinta por filas en cuadros separados: evita un congelamiento largo con clan completo.
            var raf = window.requestAnimationFrame
                ? function(f){ requestAnimationFrame(f); }
                : function(f){ setTimeout(f, 0); };
            try{ renderBisabuelos(); }catch(e){}
            raf(function(){
                try{ renderAbuelos(); }catch(e0){}
                raf(function(){
                    try{ renderPadres(); }catch(e1){}
                    raf(function(){
                        try{ renderP1(); }catch(e2){}
                        try{ renderHijos(); }catch(e3){}
                        if (done) done();
                    });
                });
            });
        }
        function refrescarConBatch(done){
            var ns = nombresDelClan();
            if (!ns.length){ renderClanPorPartes(done); return; }
            try{
                cargarPersonasBatch(ns, function(){
                    aplicarDatosCacheados();
                    renderClanPorPartes(done);
                });
            }catch(e){ renderClanPorPartes(done); }
        }
        function cargarClanDeP1(p1, done){
            function refrescar(){ refrescarConBatch(done); }
            var aplocado = false;
            try{
                var loc = JSON.parse(localStorage.getItem(claveLocalP1(p1)) || 'null');
                if (loc){ aplicarMemoriaClan(loc, true); aplocado = true; refrescar(); }
            }catch(e){}
            if (!p1){ if (!aplocado) refrescar(); return; }
            fetch('/api/clan?p1=' + encodeURIComponent(p1)).then(function(r){ return r.json(); }).then(function(j){
                if (!j) return;
                var tiene = (j.m && Object.keys(j.m).length) || (j.mayores&&j.mayores.length) || (j.menores&&j.menores.length) || (j.parejas&&j.parejas.length);
                if (!tiene && aplocado) return;
                aplicarMemoriaClan({m:j.m||{}, mayores:j.mayores||[], menores:j.menores||[], parejas:j.parejas||[], hijos:j.hijos||[]}, true);
                try{ localStorage.setItem(claveLocalP1(p1), JSON.stringify(memoriaDeS())); }catch(e){}
                refrescar();
            }).catch(function(){ if (!aplocado) refrescar(); });
        }
        window._clanSetP1 = function(nuevoP1){
            try{
                nuevoP1 = String(nuevoP1 || '');
                if ((S.miembros.p1.nombre || '') === nuevoP1) { cargarClanDeP1(nuevoP1); return; }
                S.miembros.p1.nombre = nuevoP1;
                S.miembros.p1.data = null; S.miembros.p1.overlays = [];
                cargarClanDeP1(nuevoP1);
            }catch(e){}
        };
        window._clanOlvidar = function(nombres, p1Nuevo){
            try{
                (nombres || []).forEach(function(n){
                    n = String(n || '');
                    if (!n) return;
                    try{ delete _clanCache[n]; }catch(e){}
                    try{ localStorage.removeItem(claveLocalP1(n)); }catch(e){}
                });
                try{ localStorage.removeItem(CLAN_MEM_KEY); }catch(e){}
                var p1 = S.miembros.p1.nombre || '';
                if (p1Nuevo && String(p1).toLowerCase() === String(window._editandoP1 || '').toLowerCase()) p1 = p1Nuevo;
                S.miembros.p1.nombre = p1;
                window._clanSetP1(p1);
            }catch(e){}
        };
        function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
        function opcionesPersonas(){
            var sel = document.getElementById('selector-persona-a');
            if (!sel) return [];
            return Array.prototype.map.call(sel.options, function(o){ return {v:o.value, t:o.textContent}; });
        }
        function setPuertas(data){ try{ return new Set(data.todas_puertas||[]); }catch(e){ return new Set(); } }
        var _canalesBaseCache = null;
        function canalesBase(){
            if (_canalesBaseCache) return _canalesBaseCache;
            var out = [];
            try{
                document.querySelectorAll('#svg-persona-a svg [id^="c"]').forEach(function(el){
                    var m = el.id.match(/^c(\d+)-(\d+)$/);
                    if (m) out.push([parseInt(m[1],10), parseInt(m[2],10)]);
                });
            }catch(e){}
            _canalesBaseCache = out;
            return out;
        }
        function clanEntryByKey(key){
            if (S.miembros[key]) return S.miembros[key];
            var hs = S.mayores.concat(S.menores).concat(S.parejas||[]).concat(S.bisabuelos||[]).concat(S.hijos||[]);
            for (var i=0;i<hs.length;i++){ if (('hM'+hs[i].uid)===key || ('hm'+hs[i].uid)===key || ('px'+hs[i].uid)===key || ('bs'+hs[i].uid)===key || ('hj'+hs[i].uid)===key) return hs[i]; }
            return null;
        }
        // Al elegir padre/madre/hermano, buscar su ficha en clan y autollenar
        // familiares vacíos: padre->abuelos paternos, madre->abuelos maternos,
        // hermano->padres+abuelos de P1. Solo rellena combos vacíos, no pisa manual.
        function clanAutocompletarDesde(key, nombreSel){
            if (!nombreSel) return;
            var esPadre = (key === 'padre'), esMadre = (key === 'madre');
            var esHermano = (key && (key.indexOf('hM') === 0 || key.indexOf('hm') === 0));
            if (!esPadre && !esMadre && !esHermano) return;
            fetch('/api/clan?p1=' + encodeURIComponent(nombreSel)).then(function(r){ return r.json(); }).then(function(j){
                if (!j || !j.m) return;
                var m = j.m || {};
                var cambios = false;
                function poner(slot, val){
                    if (!val) return;
                    val = String(val).trim();
                    if (!val || !S.miembros[slot]) return;
                    if ((S.miembros[slot].nombre || '').trim()) return;
                    S.miembros[slot].nombre = val;
                    S.miembros[slot].data = null; S.miembros[slot].overlays = [];
                    cambios = true;
                }
                if (esPadre){ poner('ap_abuelo', m.padre); poner('ap_abuela', m.madre); }
                else if (esMadre){ poner('am_abuelo', m.padre); poner('am_abuela', m.madre); }
                else if (esHermano){
                    poner('padre', m.padre); poner('madre', m.madre);
                    poner('ap_abuelo', m.ap_abuelo); poner('ap_abuela', m.ap_abuela);
                    poner('am_abuela', m.am_abuela); poner('am_abuelo', m.am_abuelo);
                }
                if (!cambios) return;
                try{ renderAbuelos(); renderPadres(); renderP1(); }catch(e){}
                try{ guardarClan(); }catch(e){}
            }).catch(function(){});
        }
        // Pinta EXACTO como personas adicionales (misma función, color único del
        // pariente para incon+consc+mixto), guardando y restaurando lo de P2
        // para no interferir con Grafica-B ni paneles.
        function clanPintarBase(box, data, color){
            var sub = document.getElementById('subtitulo-grafico-b');
            var subTxt = sub ? sub.textContent : '';
            var cB = (window._canalesB) ? window._canalesB.slice() : null;
            var ids = ['centros-detalle-b','canales-detalle-b','puertas-detalle-b'];
            var saved = ids.map(function(id){ var e=document.getElementById(id); return e ? e.innerHTML : ''; });
            try { actualizarSVGIndividual(box, data, color, color, color); } catch(e){}
            try {
                if (sub) sub.textContent = subTxt;
                if (cB) window._canalesB = cB;
                ids.forEach(function(id,i){ var e=document.getElementById(id); if (e) e.innerHTML = saved[i]; });
            } catch(e){}
            try { actualizarCapasLineasEmojis(); } catch(e){}
        }
        // Mezcla por arrastre: puertas del origen en su color sobre el destino;
        // compartidas = base sólida + clon punteado con el color origen.
        function clanAplicarOverlays(box, entry, colorBase){
            if (!entry.overlays || !entry.overlays.length) return;
            var svg = box.querySelector('svg');
            if (!svg) return;
            var gmap = (typeof gateToCircleMap !== 'undefined') ? gateToCircleMap : {};
            var base = entry.data ? setPuertas(entry.data) : new Set();
            var union = new Set(base);
            entry.overlays.forEach(function(ov){ ov.puertas.forEach(function(p){ union.add(p); }); });
            entry.overlays.forEach(function(ov){
                var set = new Set(ov.puertas);
                set.forEach(function(p){
                    var tramo = svg.querySelector('#tramo'+p);
                    if (tramo){
                        if (base.has(p)){
                            tramo.style.stroke = colorBase;
                            tramo.style.visibility = 'visible';
                            tramo.style.strokeDasharray = '';
                            var clon = tramo.cloneNode(true);
                            clon.removeAttribute('id');
                            clon.style.stroke = ov.color;
                            clon.style.strokeDasharray = '4 3';
                            clon.style.visibility = 'visible';
                            tramo.parentNode.appendChild(clon);
                        } else {
                            tramo.style.stroke = ov.color;
                            tramo.style.visibility = 'visible';
                            tramo.style.strokeDasharray = '';
                        }
                    }
                    var cid = gmap[p];
                    if (cid){ var c = svg.querySelector('#'+cid); if (c) c.style.visibility = 'visible'; }
                });
            });
            svg.querySelectorAll('[id^="c"]').forEach(function(canal){
                var m = canal.id.match(/^c(\d+)-(\d+)$/);
                if (!m) return;
                if (union.has(parseInt(m[1],10)) && union.has(parseInt(m[2],10))){ canal.style.visibility='visible'; canal.style.opacity='1'; }
            });
        }
        function clanRepintar(box, entry, color){
            var svgBase = document.querySelector('#svg-persona-a svg');
            if (!svgBase) return;
            box.innerHTML = '';
            var clon = svgBase.cloneNode(true);
            clon.removeAttribute('id');
            try {
                quitarDescripcionesP1(clon);
                quitarFotoPublica(clon); // la foto pública es solo de P1
                clon.querySelectorAll('#Capa_panel_planetas').forEach(function(el){ el.remove(); }); // tabla planetas solo en P1/P2
            } catch(e){
                clon.querySelectorAll('[data-capa-descripciones]').forEach(function(el){ el.remove(); });
                var vb = clon.getAttribute('data-desc-viewbox');
                if (vb){ clon.setAttribute('viewBox', vb); clon.removeAttribute('data-desc-viewbox'); }
            }
            try {
                clon.querySelectorAll('[data-simpl]').forEach(function(el){ el.remove(); });
                clon.querySelectorAll('[data-transito-clon]').forEach(function(el){ el.remove(); });
                clon.querySelectorAll('linearGradient[id^="grad-comp-simpl-"]').forEach(function(el){ el.remove(); });
                clon.querySelectorAll('[data-simpl-oculto]').forEach(function(t){ delete t.dataset.simplOculto; });
            } catch(e2){}
            box.appendChild(clon);
            if (entry && entry.data){
                clanPintarBase(box, entry.data, color);
                clanAplicarOverlays(box, entry, color);
            } else {
                try { limpiarSVG(box); } catch(e){
                    clon.querySelectorAll('[id^="tramo"]').forEach(function(t){ t.style.visibility='hidden'; });
                    clon.querySelectorAll('[id^="c"]').forEach(function(c){ c.style.visibility='visible'; c.style.opacity='0.01'; });
                }
            }
        }
        // ===== Crisol: olla vacía a la derecha de Padres, solo canales superpuestos =====
        if (!S.crisol) S.crisol = { layers: [] };
        function crisolPintarMulti(tramo, svg, idx, colores){
            if (!colores || !colores.length) return;
            tramo.style.opacity = '1';
            if (colores.length === 1){ tramo.style.stroke = colores[0]; tramo.style.visibility='visible'; tramo.style.strokeDasharray=''; return; }
            if (colores.length === 2 && typeof pintarBicolor === 'function'){ pintarBicolor(tramo, svg, 'crisol'+idx, colores[0], colores[1]); tramo.style.visibility='visible'; return; }
            try{
                var defs = svg.querySelector('defs');
                var gid = 'grad-crisol-'+idx;
                var viejo = defs ? defs.querySelector('#'+gid) : null;
                if (viejo) viejo.remove();
                var len = tramo.getTotalLength();
                var p0 = tramo.getPointAtLength(0);
                var p1 = tramo.getPointAtLength(Math.max(len-0.01,0));
                if (!defs || !len){ tramo.style.stroke = colores[0]; tramo.style.visibility='visible'; return; }
                var NS = 'http://www.w3.org/2000/svg';
                var gr = document.createElementNS(NS,'linearGradient');
                gr.setAttribute('id', gid); gr.setAttribute('gradientUnits','userSpaceOnUse');
                gr.setAttribute('x1',p0.x); gr.setAttribute('y1',p0.y); gr.setAttribute('x2',p1.x); gr.setAttribute('y2',p1.y);
                var n = Math.max(colores.length, Math.round(len/7));
                for (var k=0;k<n;k++){
                    var c = colores[k % colores.length];
                    [[k/n,c],[(k+1)/n,c]].forEach(function(par){
                        var s = document.createElementNS(NS,'stop');
                        s.setAttribute('offset',par[0]); s.setAttribute('stop-color',par[1]);
                        gr.appendChild(s);
                    });
                }
                defs.appendChild(gr);
                tramo.style.stroke = 'url(#'+gid+')';
                tramo.style.strokeDasharray=''; tramo.style.strokeLinecap='butt';
                tramo.style.visibility='visible';
            }catch(e){ tramo.style.stroke = colores[0]; tramo.style.visibility='visible'; }
        }
        function crisolRepintar(box){
            var svgBase = document.querySelector('#svg-persona-a svg');
            if (!svgBase || !box) return;
            box.innerHTML = '';
            var clon = svgBase.cloneNode(true);
            clon.removeAttribute('id');
            try{
                quitarDescripcionesP1(clon);
                quitarFotoPublica(clon); // la foto pública es solo de P1
                clon.querySelectorAll('#Capa_panel_planetas').forEach(function(el){ el.remove(); }); // tabla planetas solo en P1/P2
            }catch(e){
                clon.querySelectorAll('[data-capa-descripciones]').forEach(function(el){ el.remove(); });
                var vb = clon.getAttribute('data-desc-viewbox');
                if (vb){ clon.setAttribute('viewBox', vb); clon.removeAttribute('data-desc-viewbox'); }
            }
            try{
                clon.querySelectorAll('[data-simpl]').forEach(function(el){ el.remove(); });
                clon.querySelectorAll('[data-transito-clon]').forEach(function(el){ el.remove(); });
                clon.querySelectorAll('[id^="grad-comp-"]').forEach(function(el){ el.remove(); });
            }catch(e2){}
            box.appendChild(clon);
            var svg = box.querySelector('svg');
            if (!svg) return;
            try{ limpiarSVG(box); }catch(e){}
            box.querySelectorAll('[id^="tramo"]').forEach(function(t){ t.style.visibility='hidden'; t.style.opacity=''; });
            var gmap = (typeof gateToCircleMap !== 'undefined') ? gateToCircleMap : {};
            var porPuerta = {};
            (S.crisol.layers||[]).forEach(function(L){
                (L.puertas||[]).forEach(function(p){ (porPuerta[p]=porPuerta[p]||[]).push(L.color); });
            });
            var union = new Set(Object.keys(porPuerta).map(function(x){ return parseInt(x,10); }));
            Object.keys(porPuerta).forEach(function(pk){
                var p = parseInt(pk,10);
                var tramo = svg.querySelector('#tramo'+p);
                if (tramo) crisolPintarMulti(tramo, svg, p, porPuerta[p]);
                var cid = gmap[p];
                if (cid){ var c = svg.querySelector('#'+cid); if (c) c.style.visibility='visible'; }
            });
            try{
                svg.querySelectorAll('[id^="c"]').forEach(function(canal){
                    var m = canal.id.match(/^c(\d+)-(\d+)$/);
                    if (!m) return;
                    if (union.has(parseInt(m[1],10)) && union.has(parseInt(m[2],10))){ canal.style.visibility='visible'; canal.style.opacity='1'; }
                });
            }catch(e3){}
            try{ actualizarCapasLineasEmojis(); }catch(e4){}
        }
        function crisolRefreshLista(cont, box){
            cont.innerHTML = '';
            var layers = S.crisol.layers || [];
            if (!layers.length){
                var v = document.createElement('div');
                v.className = 'crisol-vacio';
                v.textContent = 'Arrastrá familiares acá';
                cont.appendChild(v);
                return;
            }
            layers.forEach(function(L){
                var it = document.createElement('div');
                it.className = 'crisol-item';
                var b = document.createElement('button');
                b.type = 'button'; b.textContent = '×'; b.title = 'Quitar '+(L.nombre||'');
                b.style.borderColor = L.color; b.style.color = L.color;
                b.addEventListener('click', function(ev){
                    ev.stopPropagation();
                    S.crisol.layers = (S.crisol.layers||[]).filter(function(o){ return o.key!==L.key; });
                    crisolRepintar(box); crisolRefreshLista(cont, box);
                });
                var nm = document.createElement('span');
                nm.textContent = L.nombre || L.key;
                it.appendChild(b); it.appendChild(nm);
                cont.appendChild(it);
            });
        }
        function buildCrisolCard(){
            var card = document.createElement('div');
            card.className = 'clan-card crisol';
            card.title = 'Arrastrá familiares del clan para superponer canales';
            var tit = document.createElement('div');
            tit.className = 'clan-titulo'; tit.style.color = '#616161'; tit.textContent = 'Crisol';
            card.appendChild(tit);
            var wrap = document.createElement('div');
            wrap.className = 'clan-svgwrap';
            var box = document.createElement('div');
            box.className = 'svg-box';
            wrap.appendChild(box);
            card.appendChild(wrap);
            var lista = document.createElement('div');
            lista.className = 'crisol-lista';
            card.appendChild(lista);
            crisolRepintar(box); crisolRefreshLista(lista, box);
            card.addEventListener('dragover', function(ev){ ev.preventDefault(); card.classList.add('drop-hover'); });
            card.addEventListener('dragleave', function(){ card.classList.remove('drop-hover'); });
            card.addEventListener('drop', function(ev){
                ev.preventDefault(); ev.stopPropagation(); card.classList.remove('drop-hover');
                var txt = ''; try{ txt = ev.dataTransfer.getData('text/plain'); }catch(e){}
                if (!txt || txt.indexOf('clan:')!==0) return;
                var srcKey = txt.slice(5);
                if (srcKey === 'crisol') return;
                var src = clanEntryByKey(srcKey);
                if (!src || !src.data) return;
                if ((S.crisol.layers||[]).some(function(o){ return o.key===srcKey; })) return;
                var setS = setPuertas(src.data);
                var soloCanales = [];
                try{
                    canalesBase().forEach(function(par){
                        if (setS.has(par[0]) && setS.has(par[1])){ soloCanales.push(par[0]); soloCanales.push(par[1]); }
                    });
                }catch(e){}
                var unicas = Array.from(new Set(soloCanales));
                S.crisol.layers.push({key:srcKey, nombre:src.nombre||srcKey, color:src._color||'#999999', puertas:unicas});
                crisolRepintar(box); crisolRefreshLista(lista, box);
            });
            return card;
        }
        // Ruta guardada en la ficha -> dirección que el navegador puede mostrar.
        function fotoMostrable(valor){
            var v = String(valor || '').trim();
            if (!v) return '';
            if (/^(https?:|data:|\/)/i.test(v)) return v;
            return '/api/foto_local?ruta=' + encodeURIComponent(v);
        }
        // Recuadro de foto del clan: muestra y guarda la MISMA foto de la ficha
        // de la persona (no una copia aparte).
        function fotoBox(entry, color){
            var f = document.createElement('div');
            f.className = 'clan-foto';
            f.title = 'Clic o arrastrar para elegir la foto de esta persona';
            function ponerFoto(src){
                entry.foto = src || '';
                f.innerHTML = '';
                var s = fotoMostrable(src);
                if (!s){ f.textContent = '📷'; return; }
                var im = document.createElement('img'); im.src = s; f.appendChild(im);
            }
            var inicial = entry.foto || (entry.data && entry.data.foto) || '';
            ponerFoto(inicial);
            function avisar(txt){ try{ alert(txt); }catch(e){} }
            // Selector del navegador (funciona igual en local y en Render).
            var inpFile = document.createElement('input');
            inpFile.type = 'file'; inpFile.accept = 'image/*';
            inpFile.style.cssText = 'position:absolute;width:1px;height:1px;opacity:0;overflow:hidden;clip:rect(0 0 0 0)';
            f.appendChild(inpFile);
            inpFile.addEventListener('click', function(ev){ ev.stopPropagation(); });
            inpFile.addEventListener('change', function(){
                var file = inpFile.files && inpFile.files[0];
                inpFile.value = '';
                if (!file) return;
                window.DHFotoDataUrl(file, function(dataUrl){
                    if (!dataUrl){ avisar('No se pudo leer: elegí un archivo de imagen (JPG, PNG, WEBP).'); return; }
                    guardarFoto(dataUrl);
                });
            });
            async function guardarFoto(ruta){
                var nombre = String(entry.nombre || '').trim();
                if (!nombre){ avisar('Elegí primero el nombre de la persona.'); return false; }
                try{
                    var r = await fetch('/api/persona_foto', {method:'POST', headers:{'Content-Type':'application/json'},
                        body: JSON.stringify({nombre: nombre, foto: ruta})});
                    var d = await r.json();
                    if (!r.ok){ avisar(d.error || 'No se pudo guardar la foto'); return false; }
                    entry.foto = ruta;
                    if (entry.data) entry.data.foto = ruta;
                    try{ if (_clanCache[nombre]) _clanCache[nombre].foto = ruta; }catch(e){}
                    ponerFoto(ruta);
                    try{
                        if (String((S.miembros.p1 && S.miembros.p1.nombre) || '').toLowerCase() === nombre.toLowerCase())
                            pintarFotoPublicaA(fotoMostrable(ruta));
                    }catch(e){}
                    return true;
                }catch(e){ avisar('Error de red al guardar la foto'); return false; }
            }
            f.addEventListener('click', async function(ev){
                ev.stopPropagation();
                if (!String(entry.nombre || '').trim()){ avisar('Elegí primero el nombre de la persona.'); return; }
                inpFile.click();
            });
            ['dragover','dragenter'].forEach(function(evt){ f.addEventListener(evt, function(ev){ ev.preventDefault(); ev.stopPropagation(); f.classList.add('over'); }); });
            ['dragleave','drop'].forEach(function(evt){ f.addEventListener(evt, function(ev){ ev.preventDefault(); ev.stopPropagation(); f.classList.remove('over'); }); });
            f.addEventListener('drop', async function(ev){
                var file = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
                if (!file || !String(file.type||'').startsWith('image/')) return;
                var nombre = String(entry.nombre || '').trim();
                if (!nombre){ avisar('Elegí primero el nombre de la persona.'); return; }
                window.DHFotoDataUrl(file, function(dataUrl){
                    if (!dataUrl){ avisar('No se pudo leer: elegí un archivo de imagen (JPG, PNG, WEBP).'); return; }
                    guardarFoto(dataUrl);
                });
            });
            return f;
        }
        var _clanCache = {};
        function cargarPersona(nombre, cb){
            if (!nombre){ cb(null); return; }
            if (_clanCache[nombre]){ cb(_clanCache[nombre]); return; }
            fetch('/api/persona/'+encodeURIComponent(nombre)).then(function(r){ return r.json(); }).then(function(d){
                var v = (d && !d.error) ? d : null;
                if (v) _clanCache[nombre] = v;
                cb(v);
            }).catch(function(){ cb(null); });
        }
        function cargarPersonasBatch(nombres, cb){
            var faltan = (nombres||[]).filter(function(n){ return n && !_clanCache[n]; });
            faltan = Array.from(new Set(faltan));
            if (!faltan.length){ cb(_clanCache); return; }
            fetch('/api/personas_batch', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({personas: faltan})
            }).then(function(r){ return r.json(); }).then(function(d){
                (faltan||[]).forEach(function(n){
                    var v = d && d[n];
                    if (v && !v.error) _clanCache[n] = v;
                });
                cb(_clanCache);
            }).catch(function(){
                var chain = Promise.resolve();
                faltan.forEach(function(n){
                    chain = chain.then(function(){ return new Promise(function(res){
                        cargarPersona(n, function(){ res(); });
                    }); });
                });
                chain.then(function(){ cb(_clanCache); });
            });
        }
        var _lecturaTimer = null;
        function actualizarLecturaSoon(){ if (_lecturaTimer) clearTimeout(_lecturaTimer); _lecturaTimer = setTimeout(function(){ try { actualizarLectura(); } catch(e){} }, 200); }
        function refreshOverX(overx, box, entry, color){
            overx.innerHTML = '';
            (entry.overlays||[]).forEach(function(ov){
                var b = document.createElement('button');
                b.className = 'clan-ox'; b.type='button'; b.textContent='×'; b.title='Quitar '+(ov.nombre||'');
                b.style.borderColor = ov.color; b.style.color = ov.color;
                b.addEventListener('click', function(ev){
                    ev.stopPropagation();
                    entry.overlays = (entry.overlays||[]).filter(function(o){ return o.key!==ov.key; });
                    clanRepintar(box, entry, color);
                    refreshOverX(overx, box, entry, color);
                });
                overx.appendChild(b);
            });
        }
        function buildCard(opts){
            var entry = opts.entry, etiqueta = opts.etiqueta, color = opts.color;
            entry._color = color;
            if (!entry.overlays) entry.overlays = [];
            var card = document.createElement('div');
            card.className = 'clan-card' + (opts.clase ? ' ' + opts.clase : '');
            card.style.borderColor = color;
            card.draggable = true;
            card.title = opts.titulo || 'Arrastrá hacia otra gráfica del clan para mezclar puertas';
            if (opts.removable){
                var x = document.createElement('button');
                x.className = 'clan-x'; x.type = 'button'; x.textContent = '×'; x.title = 'Quitar';
                x.addEventListener('click', function(ev){ ev.stopPropagation(); opts.onRemove(); });
                card.appendChild(x);
            }
            var tit = document.createElement('div');
            tit.className = 'clan-titulo'; tit.style.color = color; tit.textContent = etiqueta;
            card.appendChild(tit);
            var combo = document.createElement('select');
            combo.className = 'clan-combo'; combo.title = etiqueta + ' — elegir persona';
            var opVacio = document.createElement('option');
            opVacio.value = ''; opVacio.textContent = '— Elegir —';
            combo.appendChild(opVacio);
            opcionesPersonas().forEach(function(o){
                if (!o.v) return;
                var op = document.createElement('option');
                op.value = o.v; op.textContent = o.t;
                combo.appendChild(op);
            });
            combo.value = entry.nombre || '';
            if (entry.nombre && combo.value !== entry.nombre){
                var opF = document.createElement('option');
                opF.value = entry.nombre; opF.textContent = entry.nombre;
                combo.appendChild(opF); combo.value = entry.nombre;
            }
            combo.addEventListener('change', function(){
                entry.nombre = combo.value;
                entry.data = null;
                entry.overlays = [];
                entry._gen = (entry._gen||0)+1;
                clanRepintar(box, entry, color); refreshOverX(overx, box, entry, color);
                if (!entry.nombre){ guardarClan(); return; }
                try { clanAutocompletarDesde(opts.key, entry.nombre); } catch(e){}
                var pedido = entry.nombre;
                var g = entry._gen;
                cargarPersona(pedido, function(d){
                    if (entry._gen !== g) return;
                    if ((entry.nombre||'') !== pedido) return;
                    if (!d) return;
                    entry.data = d;
                    clanRepintar(box, entry, color);
                    refreshOverX(overx, box, entry, color);
                    actualizarLecturaSoon();
                });
            });
            card.appendChild(combo);
            var wrap = document.createElement('div');
            wrap.className = 'clan-svgwrap';
            var box = document.createElement('div');
            box.className = 'svg-box';
            box._clanEntry = entry;
            wrap.appendChild(box);
            wrap.appendChild(fotoBox(entry, color));
            var overx = document.createElement('div');
            overx.className = 'clan-overx';
            wrap.appendChild(overx);
            card.appendChild(wrap);
            clanRepintar(box, entry, color);
            refreshOverX(overx, box, entry, color);
            if (entry.nombre && !entry.data){
                var g0 = (entry._gen||0)+1; entry._gen = g0;
                var pedido0 = entry.nombre;
                cargarPersona(pedido0, function(d){
                    if (entry._gen !== g0) return;
                    if ((entry.nombre||'') !== pedido0) return;
                    if (!entry.nombre) return;
                    if (!d) { actualizarLecturaSoon(); return; }
                    entry.data = d;
                    clanRepintar(box, entry, color);
                    refreshOverX(overx, box, entry, color);
                    actualizarLecturaSoon();
                });
            }
            card.addEventListener('dragstart', function(ev){
                try { ev.dataTransfer.setData('text/plain', 'clan:'+opts.key); ev.dataTransfer.effectAllowed='copy'; } catch(e){}
                card.classList.add('dragging');
            });
            card.addEventListener('dragend', function(){ card.classList.remove('dragging'); });
            card.addEventListener('dragover', function(ev){ ev.preventDefault(); card.classList.add('drop-hover'); });
            card.addEventListener('dragleave', function(){ card.classList.remove('drop-hover'); });
            card.addEventListener('drop', function(ev){
                ev.preventDefault(); ev.stopPropagation(); card.classList.remove('drop-hover');
                var txt = ''; try { txt = ev.dataTransfer.getData('text/plain'); } catch(e){}
                if (!txt || txt.indexOf('clan:')!==0) return;
                var srcKey = txt.slice(5);
                if (srcKey === opts.key) return;
                var src = clanEntryByKey(srcKey);
                if (!src || !src.data) return;
                if ((entry.overlays||[]).some(function(o){ return o.key===srcKey; })) return;
                entry.overlays.push({key:srcKey, nombre:src.nombre||srcKey, color:src._color||'#999999', puertas:Array.from(setPuertas(src.data))});
                clanRepintar(box, entry, color);
                refreshOverX(overx, box, entry, color);
                actualizarLectura();
            });
            if (opts.isP1){
                var fila = document.createElement('div');
                var bM = document.createElement('button');
                bM.className = 'clan-mas'; bM.type='button'; bM.title='Agregar hermano mayor (izquierda)'; bM.textContent='+ mayor';
                bM.addEventListener('click', function(){ agregarHermano('mayor'); });
                var bm = document.createElement('button');
                bm.className = 'clan-mas'; bm.type='button'; bm.title='Agregar hermano menor (derecha)'; bm.textContent='+ menor';
                bm.addEventListener('click', function(){ agregarHermano('menor'); });
                var bP = document.createElement('button');
                bP.className = 'clan-mas'; bP.type='button'; bP.title='Agregar pareja (derecha de la primera pareja)'; bP.textContent='+ pareja';
                bP.addEventListener('click', function(){ agregarPareja(); });
                var bH = document.createElement('button');
                bH.className = 'clan-mas'; bH.type='button'; bH.title='Agregar hijo/a (fila de abajo, tonos verdes)'; bH.textContent='+ hijo';
                bH.addEventListener('click', function(){ agregarHijo(); });
                var bB = document.createElement('button');
                bB.className = 'clan-mas'; bB.type='button'; bB.title='Agregar bisabuelo/a (fila de arriba, hasta 8, gris con el color de su rama)'; bB.textContent='+ bisabuelo';
                if ((S.bisabuelos||[]).length >= 8){ bB.disabled = true; bB.style.opacity = '.5'; bB.title = 'Ya están los 8 bisabuelos'; }
                bB.addEventListener('click', function(){ if ((S.bisabuelos||[]).length >= 8) return; agregarBisabuelo(); });
                fila.appendChild(bM); fila.appendChild(bm); fila.appendChild(bP); fila.appendChild(bH); fila.appendChild(bB);
                card.appendChild(fila);
            }
            return card;
        }
        function agregarHermano(lado){
            var entry = {uid:++uidN, nombre:'', data:null, foto:'', overlays:[]};
            if (lado==='mayor') S.mayores.push(entry); else S.menores.push(entry);
            renderP1();
        }
        function quitarHermano(lado, uid){
            var arr = (lado==='mayor') ? S.mayores : S.menores;
            var i = arr.findIndex(function(h){ return h.uid===uid; });
            if (i>=0) arr.splice(i,1);
            renderP1();
        }
        function agregarPareja(){
            S.parejas.push({uid:++uidN, nombre:'', data:null, foto:'', overlays:[]});
            renderP1();
        }
        function quitarPareja(uid){
            var i = S.parejas.findIndex(function(h){ return h.uid===uid; });
            if (i>=0) S.parejas.splice(i,1);
            renderP1();
        }
        function agregarHijo(){
            S.hijos.push({uid:++uidN, nombre:'', data:null, foto:'', overlays:[]});
            renderHijos();
        }
        function quitarHijo(uid){
            var i = S.hijos.findIndex(function(h){ return h.uid===uid; });
            if (i>=0) S.hijos.splice(i,1);
            renderHijos();
        }
        function siguienteSlotBisabuelo(){
            var usados = {};
            (S.bisabuelos||[]).forEach(function(h){ usados[h.slot] = 1; });
            for (var i=0;i<8;i++){ if (!usados[i]) return i; }
            return -1;
        }
        function agregarBisabuelo(){
            var slot = siguienteSlotBisabuelo();
            if (slot < 0) return;
            S.bisabuelos.push({uid:++uidN, slot:slot, nombre:'', data:null, foto:'', overlays:[]});
            renderBisabuelos();
            renderP1();
        }
        function quitarBisabuelo(uid){
            var i = (S.bisabuelos||[]).findIndex(function(h){ return h.uid===uid; });
            if (i>=0) S.bisabuelos.splice(i,1);
            renderBisabuelos();
            renderP1();
        }
        function renderBisabuelos(){
            var fila = document.getElementById('clan-fila-bisabuelos');
            if (!fila) return;
            fila.querySelectorAll('.clan-card').forEach(function(n){ n.remove(); });
            var label = fila.querySelector('.clan-fila-label');
            if (label) label.textContent = 'Bisabuelos (' + (S.bisabuelos||[]).length + '/8)';
            (S.bisabuelos||[]).slice().sort(function(a,b){ return a.slot-b.slot; }).forEach(function(h){
                var def = FIJOS_BISABUELOS[h.slot] || {etiqueta:'Bisabuelo', base:'#9E9E9E', t:0.4, titulo:'Bisabuelo'};
                var col = grisCon(def.base, def.t);
                fila.appendChild(buildCard({key:'bs'+h.uid, entry:h, etiqueta:def.etiqueta, color:col,
                    titulo:def.titulo + ' — arrastrá hacia otra gráfica del clan para mezclar puertas',
                    clase:'mini', removable:true, onRemove:function(){ quitarBisabuelo(h.uid); }}));
            });
        }
        function renderHijos(){
            var fila = document.getElementById('clan-fila-hijos');
            if (!fila) return;
            fila.querySelectorAll('.clan-card').forEach(function(n){ n.remove(); });
            (S.hijos||[]).forEach(function(h, idx){
                var col = HIJO_COLORES[idx % HIJO_COLORES.length];
                fila.appendChild(buildCard({key:'hj'+h.uid, entry:h, etiqueta:'Hijo/a '+(idx+1), color:col,
                    removable:true, onRemove:function(){ quitarHijo(h.uid); }}));
            });
        }
        function renderAbuelos(){
            var fila = document.getElementById('clan-fila-abuelos');
            fila.querySelectorAll('.clan-card').forEach(function(n){ n.remove(); });
            FIJOS_ABUELOS.forEach(function(f){
                var c = buildCard({key:f.id, entry:S.miembros[f.id], etiqueta:f.etiqueta, color:COLORES[f.id]});
                fila.appendChild(c);
            });
        }
        function renderPadres(){
            var fila = document.getElementById('clan-fila-padres');
            fila.querySelectorAll('.clan-card').forEach(function(n){ n.remove(); });
            try{ fila.appendChild(buildCrisolCard()); }catch(e){}
            FIJOS_PADRES.forEach(function(f){
                var c = buildCard({key:f.id, entry:S.miembros[f.id], etiqueta:f.etiqueta, color:COLORES[f.id]});
                fila.appendChild(c);
            });
        }
        function renderP1(){
            var fila = document.getElementById('clan-fila-p1');
            fila.querySelectorAll('.clan-card').forEach(function(n){ n.remove(); });
            S.mayores.forEach(function(h, idx){
                var col = HERMANO_COLORES[idx % HERMANO_COLORES.length];
                fila.appendChild(buildCard({key:'hM'+h.uid, entry:h, etiqueta:'Hermano mayor '+(idx+1), color:col, removable:true, onRemove:function(){ quitarHermano('mayor', h.uid); }}));
            });
            fila.appendChild(buildCard({key:'p1', entry:S.miembros.p1, etiqueta:'P1', color:COLORES.p1, isP1:true}));
            fila.appendChild(buildCard({key:'pareja', entry:S.miembros.pareja, etiqueta:'Pareja P1', color:COLORES.pareja}));
            (S.parejas||[]).forEach(function(h, idx){
                fila.appendChild(buildCard({key:'px'+h.uid, entry:h, etiqueta:'Pareja '+(idx+2), color:COLORES.pareja, removable:true, onRemove:function(){ quitarPareja(h.uid); }}));
            });
            S.menores.forEach(function(h, idx){
                var col = HERMANO_COLORES[(idx+2) % HERMANO_COLORES.length];
                fila.appendChild(buildCard({key:'hm'+h.uid, entry:h, etiqueta:'Hermano menor '+(idx+1), color:col, removable:true, onRemove:function(){ quitarHermano('menor', h.uid); }}));
            });
            actualizarLectura();
        }
        function listaCanales(setA, setB){
            var out = [];
            canalesBase().forEach(function(par){
                var a1=setA.has(par[0]), a2=setA.has(par[1]), b1=setB.has(par[0]), b2=setB.has(par[1]);
                if ((a1&&b2)||(a2&&b1)) out.push(par[0]+'-'+par[1]+' electro');
                else if (a1&&a2&&b1&&b2) out.push(par[0]+'-'+par[1]+' compañía');
                else if ((a1&&a2&&!(b1||b2))||((b1&&b2)&&!(a1||a2))) out.push(par[0]+'-'+par[1]+' dominio');
            });
            return out;
        }
        function clanEmojis(){ try{ if (typeof emojisPuerta==='function') return emojisPuerta()||{}; }catch(e){} try{ if (typeof mapaEmojis==='function') return mapaEmojis()||{}; }catch(e){} return {}; }
        function clanEmP(p){ var m=clanEmojis(); var e=m[p]||m[String(p)]; if(e) return '<span title="P'+p+'">'+esc(String(e))+'</span>'; return 'P'+p; }
        function clanEmCanal(c){ var ps=String(c||'').split('-'); if(ps.length!==2) return esc(String(c)); var a=parseInt(ps[0],10), b=parseInt(ps[1],10); if(isNaN(a)||isNaN(b)) return esc(String(c)); var m=clanEmojis(); var ea=m[a]||m[String(a)], eb=m[b]||m[String(b)]; return '<span title="'+esc(String(c))+'">'+esc(ea?String(ea):('P'+a))+esc(eb?String(eb):('P'+b))+'</span>'; }
        function clanAgruparCh(txts){ var g={}; (txts||[]).forEach(function(t){ var s=String(t||''); var i=s.lastIndexOf(' '); var c=i<0?s:s.slice(0,i), tipo=i<0?'':s.slice(i+1); (g[tipo]=g[tipo]||[]).push(c); }); var orden=['electro','compañía','dominio']; var ks=Object.keys(g); ks.sort(function(a,b){ var ia=orden.indexOf(a), ib=orden.indexOf(b); return (ia<0?99:ia)-(ib<0?99:ib); }); return ks.map(function(k){ return (k?esc(k)+': ':'')+g[k].map(clanEmCanal).join(', '); }).join(' · '); }
        function renderAnalisisClan(j){
            var el = document.getElementById('clan-analisis');
            if (!el) return;
            if (!j || j.error){ el.textContent = '-'; return; }
            function e2(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
            var out = [];
            var rep = j.repeticiones || [];
            out.push('<b>Puertas repetidas:</b><br>' + (rep.length ? rep.slice(0,12).map(function(r){ return clanEmP(r.puerta)+' ('+r.personas.map(e2).join(', ')+')'; }).join('<br>') : '—'));
            var comp = j.compensaciones || [];
            out.push('<b>Compensaciones:</b><br>' + (comp.length ? comp.slice(0,10).map(function(c){ return clanEmP(c.puerta)+' definida en '+c.definida_en.map(e2).join(', ')+'; abierta en '+c.abierta_en.map(e2).join(', '); }).join('<br>') : '—'));
            var cp = j.canales_pareja || [];
            var nomTipo = {electromagnetico:'electro', compania:'compañía', dominio:'dominio'};
            out.push('<b>Canales que se completan en pareja:</b><br>' + (cp.length ? cp.map(function(p){ var g={}; (p.canales||[]).forEach(function(c){ var t=nomTipo[c.tipo]||c.tipo; (g[t]=g[t]||[]).push(c.canal); }); var orden=['electro','compañía','dominio']; var ks=Object.keys(g); ks.sort(function(a,b){ return (orden.indexOf(a)<0?99:orden.indexOf(a))-(orden.indexOf(b)<0?99:orden.indexOf(b)); }); return e2(p.entre[0])+' + '+e2(p.entre[1])+': '+ks.map(function(k){ return e2(k)+': '+g[k].map(clanEmCanal).join(', '); }).join(' · '); }).join('<br>') : '—'));
            el.innerHTML = out.join('<br>');
        }
        var _analisisTimer = null;
        function actualizarAnalisisClan(){
            if (_analisisTimer) clearTimeout(_analisisTimer);
            _analisisTimer = setTimeout(function(){
                var p1 = (S.miembros.p1 && S.miembros.p1.nombre) || '';
                var el = document.getElementById('clan-analisis');
                if (!p1){ if (el) el.textContent = '-'; return; }
                fetch('/api/clan_analisis?p1='+encodeURIComponent(p1)).then(function(r){ return r.json(); }).then(renderAnalisisClan).catch(function(){});
            }, 400);
        }
        function actualizarLectura(){
            var lec = document.getElementById('clan-lectura');
            var alm = document.getElementById('clan-alma');
            if (!lec) return;
            var conDatos = [];
            var fijos = ['ap_abuelo','ap_abuela','am_abuela','am_abuelo','padre','madre','p1','pareja'];
            fijos.forEach(function(k){ if (S.miembros[k].data && (S.miembros[k].nombre||'').trim()) conDatos.push(k); });
            S.mayores.forEach(function(h){ if (h.data && (h.nombre||'').trim()) conDatos.push('hM'+h.uid); });
            S.menores.forEach(function(h){ if (h.data && (h.nombre||'').trim()) conDatos.push('hm'+h.uid); });
            (S.parejas||[]).forEach(function(h){ if (h.data && (h.nombre||'').trim()) conDatos.push('px'+h.uid); });
            if (!conDatos.length){ lec.textContent = 'Elegí a cada integrante del clan con su combo. Lo elegido se guarda en este navegador.'; if (alm) alm.textContent='-'; window._clanTronco = []; window._clanAbajo = []; window._clanSignificativo = {puertas:[], canales:[]}; try{ actualizarAnalisisClan(); }catch(e){} try{ window.dispatchEvent(new CustomEvent('clan-actualizado')); }catch(e){} return; }
            function setDe(k){
                if (S.miembros[k]) return setPuertas(S.miembros[k].data||{});
                var h = S.mayores.concat(S.menores).concat(S.parejas||[]).find(function(x){ return ('hM'+x.uid)===k || ('hm'+x.uid)===k || ('px'+x.uid)===k; });
                return h ? setPuertas(h.data||{}) : new Set();
            }
            function nombreDe(k){
                if (S.miembros[k]) return S.miembros[k].nombre || k;
                var h = S.mayores.concat(S.menores).concat(S.parejas||[]).find(function(x){ return ('hM'+x.uid)===k || ('hm'+x.uid)===k || ('px'+x.uid)===k; });
                return h ? (h.nombre||'hermano') : k;
            }
            // 1) Puertas repetidas en el clan: solo ancestros (abuelos+padres) con nombre
            var cuenta = {};
            ['ap_abuelo','ap_abuela','am_abuela','am_abuelo','padre','madre'].forEach(function(k){ if (S.miembros[k] && S.miembros[k].data && (S.miembros[k].nombre||'').trim()) setDe(k).forEach(function(p){ (cuenta[p]=cuenta[p]||[]).push(k); }); });
            var rep = Object.keys(cuenta).filter(function(p){ return cuenta[p].length>=2; }).sort(function(a,b){ return cuenta[b].length-cuenta[a].length || a-b; });
            // 2) Compensación: puertas de P1/hermanos ausentes en padres+abuelos
            var genArriba = new Set();
            ['ap_abuelo','ap_abuela','am_abuela','am_abuelo','padre','madre'].forEach(function(k){ setDe(k).forEach(function(p){ genArriba.add(p); }); });
            var genAbajo = new Set();
            ['p1'].concat(S.mayores.map(function(h){return 'hM'+h.uid;}), S.menores.map(function(h){return 'hm'+h.uid;}), (S.parejas||[]).map(function(h){return 'px'+h.uid;})).forEach(function(k){ setDe(k).forEach(function(p){ genAbajo.add(p); }); });
            var compensa = Array.prototype.filter.call(genAbajo, function(p){ return !genArriba.has(p); }).sort(function(a,b){return a-b;});
            // 3) Parejas que completan
            var parejas = [['ap_abuelo','ap_abuela'],['am_abuela','am_abuelo'],['padre','madre'],['p1','pareja']];
            function escH(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
            function boldP(s){ return String(s||'').replace(/\bP(\d{1,2})\b/g, '<b>P$1</b>'); }
            var lineas = [];
            var repTxt = '—';
            if (rep.length){
                var circDe = function(p){ try{ if (typeof CIRCUITO_PUERTA!=='undefined' && CIRCUITO_PUERTA[p]) return CIRCUITO_PUERTA[p]; }catch(e){} return 'colec'; };
                var grupos = {indiv:[], tribal:[], colec:[]};
                rep.forEach(function(p){ grupos[circDe(p)].push(p); });
                var nomG = {indiv:'Individual', tribal:'Tribal', colec:'Colectivo'};
                repTxt = ['indiv','tribal','colec'].map(function(g){
                    if (!grupos[g].length) return '';
                    return '<b>'+nomG[g]+'</b>:<br>'+grupos[g].map(function(p){ return clanEmP(p)+' ('+cuenta[p].map(function(k){ return escH(nombreDe(k)); }).join(', ')+')'; }).join('<br>');
                }).filter(function(x){ return !!x; }).join('<br>') || '—';
            }
            lineas.push(boldP(escH('Puertas repetidas en el clan:')) + '<br>' + repTxt);
            lineas.push('<b>La 3ª generación trae nuevo (no estaba arriba):</b>' + (compensa.length ? '<br>'+compensa.map(clanEmP).join('<br>') : ' —'));
            parejas.forEach(function(pp){
                var A=S.miembros[pp[0]], B=S.miembros[pp[1]];
                if (!A.data || !B.data) return;
                var ch = listaCanales(setPuertas(A.data), setPuertas(B.data));
                lineas.push('<b>Pareja '+escH(A.nombre||pp[0])+' + '+escH(B.nombre||pp[1])+'</b>: '+(ch.length? clanAgruparCh(ch) : 'sin canal directo'));
            });
            (S.parejas||[]).forEach(function(h, idx){
                if (!S.miembros.p1.data || !h.data) return;
                var chx = listaCanales(setPuertas(S.miembros.p1.data), setPuertas(h.data));
                lineas.push('<b>Pareja '+escH(S.miembros.p1.nombre||'P1')+' + '+escH(h.nombre||('Pareja '+(idx+2)))+'</b>: '+(chx.length? clanAgruparCh(chx) : 'sin canal directo'));
            });
            var mezclas = [];
            Object.keys(S.miembros).forEach(function(k){ var e=S.miembros[k]; if (e.overlays && e.overlays.length) mezclas.push((e.nombre||k)+' ← '+e.overlays.map(function(o){return o.nombre;}).join(', ')); });
            (S.parejas||[]).concat(S.mayores, S.menores).forEach(function(e){ if (e.overlays && e.overlays.length) mezclas.push((e.nombre||'extra')+' ← '+e.overlays.map(function(o){return o.nombre;}).join(', ')); });
            if (mezclas.length) lineas.push('Mezclas por arrastre: '+escH(mezclas.join(' · ')));
            lec.innerHTML = lineas.length > 1 ? lineas[0] + '<br>' + lineas.slice(1).map(function(l){ return l.indexOf('Pareja')>=0 ? '<br>'+l : l; }).join(' ') : lineas.join('');
            // Alma: canales por generación y los que solo salen sumando generaciones
            if (alm){
                function unionPuertas(keys){
                    var u = new Set();
                    keys.forEach(function(k){ setDe(k).forEach(function(p){ u.add(p); }); });
                    return u;
                }
                var g1 = unionPuertas(['ap_abuelo','ap_abuela','am_abuela','am_abuelo']);
                var g2 = unionPuertas(['padre','madre']);
                var g3 = unionPuertas(['p1','pareja'].concat(S.mayores.map(function(h){return 'hM'+h.uid;}), S.menores.map(function(h){return 'hm'+h.uid;}), (S.parejas||[]).map(function(h){return 'px'+h.uid;})));
                function canalesDe(union){
                    return canalesBase().filter(function(par){ return union.has(par[0])&&union.has(par[1]); }).map(function(par){return par[0]+'-'+par[1];});
                }
                function canalesCompletosIndividuo(setP){
                    return canalesBase().filter(function(par){ return setP.has(par[0])&&setP.has(par[1]); }).map(function(par){return par[0]+'-'+par[1];});
                }
                function completosDeGeneracion(keys){
                    var s = new Set();
                    keys.forEach(function(k){
                        // solo miembros con datos cargados
                        var e = (S.miembros[k] ? S.miembros[k] : clanEntryByKey(k));
                        if (e && e.data) canalesCompletosIndividuo(setDe(k)).forEach(function(c){ s.add(c); });
                    });
                    return Array.from(s).sort(function(a,b){ var pa=a.split('-').map(Number), pb=b.split('-').map(Number); return pa[0]-pb[0]||pa[1]-pb[1]; });
                }
                var K1=['ap_abuelo','ap_abuela','am_abuela','am_abuelo'];
                var K2=['padre','madre'];
                var K3=['p1','pareja'].concat(S.mayores.map(function(h){return 'hM'+h.uid;}), S.menores.map(function(h){return 'hm'+h.uid;}), (S.parejas||[]).map(function(h){return 'px'+h.uid;}));
                var c1=completosDeGeneracion(K1), c2=completosDeGeneracion(K2), c3=completosDeGeneracion(K3);
                // uniones (para detectar experiencias que solo cierra el clan mezclando puertas = electromagnetismos)
                var g1 = unionPuertas(K1), g2 = unionPuertas(K2), g3 = unionPuertas(K3);
                var todos = new Set(); g1.forEach(function(p){todos.add(p);}); g2.forEach(function(p){todos.add(p);}); g3.forEach(function(p){todos.add(p);});
                var cT = canalesDe(todos);
                var s1=new Set(c1), s2=new Set(c2), s3=new Set(c3);
                var soloClan = cT.filter(function(c){ return !s1.has(c)&&!s2.has(c)&&!s3.has(c); });
                function fmtCanales(lista, colorea){
                    if (!lista.length) return '—';
                    return lista.map(function(c){
                        var col = colorea ? colorea(c) : null;
                        if (col) return '<span style="color:'+col+';font-weight:800;">'+escH(c)+'</span>';
                        return escH(c);
                    }).join(', ');
                }
                function colorHer(c, e1, e2, e3){ if(!((e1&&e2)||(e1&&e3)||(e2&&e3))) return null; if(e1&&e2) return '#6a1b9a'; if(e1) return '#c62828'; return '#1565c0'; }
                var colG1 = function(c){ return colorHer(c, true, s2.has(c), s3.has(c)); };
                var colG2 = function(c){ return colorHer(c, s1.has(c), true, s3.has(c)); };
                var colG3 = function(c){ return colorHer(c, s1.has(c), s2.has(c), true); };
                alm.innerHTML = '<span style="font-size:11px;">Colores: <span style="color:#c62828;font-weight:800;">raíz en abuelos</span> · <span style="color:#1565c0;font-weight:800;">raíz en padres</span> · <span style="color:#6a1b9a;font-weight:800;">en ambas líneas</span></span><br><b>G1 abuelos</b>: '+fmtCanales(c1,colG1)+'<br><br><b>G2 padres</b>: '+fmtCanales(c2,colG2)+'<br><br><b>G3 P1+pareja+hermanos</b>: '+fmtCanales(c3,colG3)+'<br><br>Experiencias que ninguna generación cierra sola y el clan sí (electromagnetismos entre generaciones): '+escH(soloClan.join(', ')||'—');
                // --- Exponer tronco + significativo para P1-Condicionamientos (solo tronco, solo pie) ---
                try{
                    var TRONCO_KEYS = ['p1','padre','madre','ap_abuelo','ap_abuela','am_abuela','am_abuelo'];
                    var ROLES_TRONCO = {p1:'P1', padre:'Padre', madre:'Madre', ap_abuelo:'Abuelo paterno', ap_abuela:'Abuela paterna', am_abuelo:'Abuelo materno', am_abuela:'Abuela materna'};
                    function normKClan(s){
                        var ps = String(s||'').split('-');
                        if (ps.length !== 2) return String(s||'').trim();
                        var aa = parseInt(ps[0],10), bb = parseInt(ps[1],10);
                        if (isNaN(aa) || isNaN(bb)) return String(s||'').trim();
                        return [aa,bb].sort(function(x,y){return x-y;}).join('-');
                    }
                    var tronco = [];
                    TRONCO_KEYS.forEach(function(k){
                        var e = S.miembros[k];
                        if (e && e.data && (e.nombre||'').trim()) tronco.push({key:k, nombre:e.nombre||k, rol:ROLES_TRONCO[k]||k, puertas:Array.from(setPuertas(e.data))});
                    });
                    var abajo = [];
                    function pushAbajo(key, entry, rol){
                        if (entry && entry.data && (entry.nombre||'').trim()) abajo.push({key:key, nombre:entry.nombre||key, rol:rol, puertas:Array.from(setPuertas(entry.data))});
                    }
                    pushAbajo('p1', S.miembros.p1, 'P1');
                    S.mayores.forEach(function(h, idx){ pushAbajo('hM'+h.uid, h, 'Hermano mayor '+(idx+1)); });
                    S.menores.forEach(function(h, idx){ pushAbajo('hm'+h.uid, h, 'Hermano menor '+(idx+1)); });
                    (S.parejas||[]).forEach(function(h, idx){ pushAbajo('px'+h.uid, h, 'Pareja '+(idx+2)); });
                    if (S.miembros.pareja && S.miembros.pareja.data) pushAbajo('pareja', S.miembros.pareja, 'Pareja P1');
                    var puertasSig = {};
                    (rep||[]).forEach(function(p){ puertasSig[String(parseInt(p,10))] = 1; });
                    (compensa||[]).forEach(function(p){ puertasSig[String(parseInt(p,10))] = 1; });
                    var canalesSig = {};
                    function agregarCanalesLista(ch){
                        (ch||[]).forEach(function(txt){
                            var key = String(txt||'').split(' ')[0];
                            if (key && key.indexOf('-')>=0) canalesSig[normKClan(key)] = 1;
                        });
                    }
                    parejas.forEach(function(pp){
                        var A=S.miembros[pp[0]], B=S.miembros[pp[1]];
                        if (!A.data || !B.data) return;
                        agregarCanalesLista(listaCanales(setPuertas(A.data), setPuertas(B.data)));
                    });
                    (soloClan||[]).forEach(function(c){ canalesSig[normKClan(c)] = 1; });
                    window._clanTronco = tronco;
                    window._clanAbajo = abajo;
                    window._clanSignificativo = {puertas:Object.keys(puertasSig).map(function(x){return parseInt(x,10);}), canales:Object.keys(canalesSig)};
                    try{ window._clanHerencia = {g1:c1, g2:c2, g2repite:c2.filter(function(c){return s1.has(c);}), g3:c3, g3deG1:c3.filter(function(c){return s1.has(c);}), g3deG2:c3.filter(function(c){return s2.has(c);}), soloClan:soloClan}; }catch(eH){}
                    try{ window.dispatchEvent(new CustomEvent('clan-actualizado')); }catch(e2){}
                }catch(eSig){}
            }
            try{ actualizarAnalisisClan(); }catch(e){}
        }
        function construirPromptClan(){
            function nom(k, rol){
                try{
                    var e = S.miembros[k];
                    var n = e && e.nombre ? e.nombre : '';
                    if (!n) return rol + '=(sin elegir)';
                    return rol + '=' + n;
                }catch(e){ return rol + '=(?)'; }
            }
            var partes = [];
            partes.push(nom('p1','P1 (usuario)') + ', ' + nom('padre','padre') + ', ' + nom('madre','madre') + ', ' + nom('pareja','pareja/esposa'));
            partes.push(nom('ap_abuelo','abuelo paterno') + ', ' + nom('ap_abuela','abuela paterna') + ', ' + nom('am_abuelo','abuelo materno') + ', ' + nom('am_abuela','abuela materna'));
            var hnos = S.mayores.concat(S.menores).filter(function(h){ return h.data || h.nombre; }).map(function(h){ return h.nombre || 'hermano'; });
            var parex = (S.parejas||[]).filter(function(h){ return h.data || h.nombre; }).map(function(h){ return h.nombre || 'pareja'; });
            var encabezado = '¿Qué conclusiones se pueden sacar de estas relaciones entre ' + partes[0] + ' y su clan (' + partes[1] + (hnos.length ? ', hermanos=' + hnos.join(', ') : '') + (parex.length ? ', parejas extra=' + parex.join(', ') : '') + ') en base a Px (Puertas de diseño humano DH) y canales (x-y)? Análisis profundo de la evolución y comportamiento del alma.';
            var guiaTrans = 'Guía transgeneracional (alma del clan): G1/G2/G3 listan SOLO canales completos individuales (no electromagnetismos). Rojo=G2 repite de G1; en G3 rojo=viene de G1, azul=viene de G2, violeta=viene de G1+G2. "Solo clan" = canal que ninguna generación cierra sola (electromagnetismo entre generaciones). Memoria biogenética va en Diseño rojo: lo que fue tránsito/compromiso en padres y se vuelve canal fijo rojo en hijos = aprendizaje cristalizado. Vigilar: puerta 18 (corrección), puerta 3 + canal 3-60 (mutación), canal 18-58 (juicio/corrección), canal 27-50 (custodia), canal 13-33 (testigo), puerta 44 (memoria instintiva). Pedir al informe: 1) qué se hereda fijo, 2) qué se corrige (18), 3) qué muta (3-60), 4) propuesta concreta para mejorar el programa (qué cruce falta: tránsitos de padres en concepción vs rojo del hijo).';
            var lec = '', alm = '', ana = '';
            try{ lec = document.getElementById('clan-lectura').textContent.trim(); }catch(e){}
            try{ alm = document.getElementById('clan-alma').textContent.trim(); }catch(e){}
            try{ ana = document.getElementById('clan-analisis').textContent.trim(); }catch(e){}
            var roles = {ap_abuelo:'abuelo paterno', ap_abuela:'abuela paterna', am_abuelo:'abuelo materno', am_abuela:'abuela materna', padre:'padre', madre:'madre', p1:'P1', pareja:'pareja'};
            var puertas = [];
            Object.keys(roles).forEach(function(k){
                var e = S.miembros[k];
                if (!e || !e.data) return;
                var arr = Array.from(setPuertas(e.data)).sort(function(a,b){return a-b;});
                puertas.push((e.nombre || roles[k]) + ' (' + roles[k] + '): ' + arr.map(function(p){return 'P'+p;}).join(' '));
            });
            S.mayores.concat(S.menores).concat(S.parejas||[]).forEach(function(h){
                if (!h.data) return;
                var arr2 = Array.from(setPuertas(h.data)).sort(function(a,b){return a-b;});
                puertas.push((h.nombre || 'familiar') + ': ' + arr2.map(function(p){return 'P'+p;}).join(' '));
            });
            (S.bisabuelos||[]).forEach(function(h){
                if (!h.data) return;
                var def = FIJOS_BISABUELOS[h.slot] || {};
                var arr3 = Array.from(setPuertas(h.data)).sort(function(a,b){return a-b;});
                puertas.push((h.nombre || 'bisabuelo') + ' (' + (def.titulo || 'bisabuelo') + '): ' + arr3.map(function(p){return 'P'+p;}).join(' '));
            });
            (S.hijos||[]).forEach(function(h, idx){
                if (!h.data) return;
                var arr4 = Array.from(setPuertas(h.data)).sort(function(a,b){return a-b;});
                puertas.push((h.nombre || ('hijo '+(idx+1))) + ' (hijo/a): ' + arr4.map(function(p){return 'P'+p;}).join(' '));
            });
            return encabezado + '\n' + guiaTrans + '\nLectura del clan: repeticiones, compensaciones y parejas que completan\n' + lec + '\nExperiencias del alma en 3 generaciones\n' + alm + (ana ? '\nAnálisis avanzado del clan\n' + ana : '') + (puertas.length ? '\nPuertas de cada miembro (datos adicionales):\n' + puertas.join('\n') : '');
        }
        var btnClan = document.getElementById('btn-clan-copiar-ia');
        if (btnClan) btnClan.addEventListener('click', async function(){
            var msg = document.getElementById('clan-copiar-msg');
            var txt = construirPromptClan();
            btnClan.title = txt;
            function ok(t){ if (msg) msg.textContent = t || 'Copiado ✓ — pegalo en la IA.'; }
            try{
                await navigator.clipboard.writeText(txt);
                ok();
            }catch(e){
                try{
                    var ta = document.createElement('textarea');
                    ta.value = txt; document.body.appendChild(ta); ta.select();
                    document.execCommand('copy'); ta.remove(); ok();
                }catch(err){ if (msg) msg.textContent = 'No se pudo copiar: seleccioná manualmente.'; }
            }
            try{
                var chat = document.getElementById('ia-chat-input');
                if (chat && !chat.value.trim()) chat.value = txt;
            }catch(e){}
        });
        var btnGuardar = document.getElementById('btn-clan-guardar');
        if (btnGuardar) btnGuardar.addEventListener('click', function(){
            var msg = document.getElementById('clan-copiar-msg');
            try{ guardarClan(); }catch(e){}
            try{ actualizarLectura(); }catch(e){}
            if (msg) msg.textContent = 'Clan guardado ✓';
        });
        cargarMemoriaClan();
        renderBisabuelos(); renderAbuelos(); renderPadres(); renderP1(); renderHijos();
        try{
            var p10 = (S.miembros.p1 && S.miembros.p1.nombre) || '';
            if (p10) cargarClanDeP1(p10);
        }catch(e){}
    })();
    // Dinámica Compuesta de Contacto: texto manual por pareja P1/P2 en dinamica_compuesta.csv. Sin IA.
    // Carga diferida: solo hace fetch si la tarjeta está desplegada. Guardado: debounce en input + al cerrar/plegar/cambiar pareja (sin botón).
    (function(){
        var ta = document.getElementById('dinamica-texto');
        var lab = document.getElementById('dinamica-pareja');
        var msg = document.getElementById('dinamica-estado');
        var cardD = document.getElementById('card-dinamica-p1-p2');
        if (!ta) return;
        // Aislar eventos: el index tiene listeners globales de click que recorren el DOM
        // y colgaban el foco/teclas dentro del editor.
        ['click','focus','keydown','keyup','input'].forEach(function(ev){
            ta.addEventListener(ev, function(e){ e.stopPropagation(); }, true);
        });
        function escH(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
        function mdToHtml(t){
            // Convierte **negrita** (formato IA) a <b>; resto como texto con saltos de línea.
            var e = escH(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
            return e.replace(/\n/g, '<br>');
        }
        function getTexto(){ return ta.innerHTML || ''; }
        function setTexto(h){
            // Si viene con ** de la IA o texto plano, convertir; si ya es HTML con <b>, usar directo.
            if (/</.test(h||'') && !/\*\*/.test(h||'')) ta.innerHTML = h || '';
            else ta.innerHTML = mdToHtml(h || '');
        }
        function nombres(){
            var a = document.getElementById('selector-persona-a');
            var b = document.getElementById('selector-persona-b');
            return {p1: a && a.value ? a.value : '', p2: b && b.value ? b.value : ''};
        }
        var cargando = false;
        var parejaCargada = '';
        var sucio = false;
        var timerGuarda = null;
        function estaDesplegada(){ return cardD && !cardD.classList.contains('colapsada'); }
        function clavePareja(n){ return (n.p1 || '') + '|||' + (n.p2 || ''); }
        function actualizarVisDinamica(){
            var n = nombres();
            if (cardD) cardD.style.display = n.p2 ? '' : 'none';
            if (lab) lab.textContent = (n.p1 && n.p2) ? ('Pareja: ' + n.p1 + ' y ' + n.p2 + '.') : 'Elegí Persona 1 y Persona 2.';
            return n;
        }
        async function cargarDinamica(forzada){
            var n = actualizarVisDinamica();
            if (!estaDesplegada()) return;
            if (!n.p1 || !n.p2) return;
            if (!forzada && clavePareja(n) === parejaCargada) return;
            // Si hay edición sin guardar y cambiamos de pareja, guardar antes (fire-and-forget)
            if (sucio && clavePareja(n) !== parejaCargada && parejaCargada){ guardarAhora(true); }
            // No pisar lo que se está escribiendo salvo carga explícita
            if (!forzada && sucio && !confirm('Hay texto sin guardar. ¿Reemplazar con lo guardado?')) return;
            if (msg) msg.textContent = 'Cargando…';
            cargando = true;
            try{
                var r = await fetch('/api/dinamica_compuesta?p1=' + encodeURIComponent(n.p1) + '&p2=' + encodeURIComponent(n.p2));
                var j = await r.json();
                setTexto((j && j.texto) || '');
                parejaCargada = clavePareja(n); sucio = false;
                if (msg) msg.textContent = ta.textContent.trim() ? 'Cargado ✓' : 'Sin texto para esta pareja.';
            }catch(e){ if (msg) msg.textContent = 'No se pudo cargar.'; }
            cargando = false;
        }
        var guardando = false;
        async function guardarAhora(silente){
            var n = nombres();
            if (!n.p1 || !n.p2 || !sucio || guardando) return;
            guardando = true;
            if (msg && !silente) msg.textContent = 'Guardando…';
            try{
                var txt = getTexto();
                var r = await fetch('/api/dinamica_compuesta', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({p1:n.p1, p2:n.p2, texto:txt})});
                var j = await r.json();
                if (j && j.ok){ sucio = false; parejaCargada = clavePareja(n); if (msg) msg.textContent = 'Guardado ✓'; }
                else if (msg && !silente) msg.textContent = 'Error: ' + ((j && j.error) || 'desconocido');
            }catch(e){ if (msg && !silente) msg.textContent = 'No se pudo guardar.'; }
            guardando = false;
        }
        function marcarSucio(){
            if (cargando) return;
            sucio = true;
            if (msg) msg.textContent = 'Editando…';
            if (timerGuarda) clearTimeout(timerGuarda);
            timerGuarda = setTimeout(function(){ guardarAhora(); }, 1500);
        }
        var bB = document.getElementById('btn-dinamica-bold');
        if (bB) bB.addEventListener('click', function(e){ e.stopPropagation(); ta.focus(); try{ document.execCommand('bold'); }catch(_){} });
        ta.addEventListener('keydown', function(e){
            if ((e.ctrlKey || e.metaKey) && (e.key === 'b' || e.key === 'B')){ e.preventDefault(); try{ document.execCommand('bold'); }catch(_){} }
        }, true);
        // Pegar desde IA: convierte **negrita** en negrita real automáticamente
        ta.addEventListener('paste', function(e){
            try{
                var txt = (e.clipboardData && e.clipboardData.getData('text/plain')) || '';
                if (txt && /\*\*(.+?)\*\*/.test(txt)){
                    e.preventDefault();
                    document.execCommand('insertHTML', false, mdToHtml(txt));
                }
            }catch(_){}
        }, true);
        var sA = document.getElementById('selector-persona-a');
        var sB = document.getElementById('selector-persona-b');
        if (sA) sA.addEventListener('change', function(){ actualizarVisDinamica(); if (estaDesplegada()) setTimeout(function(){cargarDinamica(true);}, 400); });
        if (sB) sB.addEventListener('change', function(){ actualizarVisDinamica(); if (estaDesplegada()) setTimeout(function(){cargarDinamica(true);}, 400); });
        // Plegable con memoria + carga diferida al abrir + autoguardado al plegar
        try {
            var kDin = 'dhDinamicaAbierto';
            var vDin = null; try { vDin = localStorage.getItem(kDin); } catch(e){}
            // Por defecto cerrada: no carga nada hasta que se abre
            if (vDin === '1') cardD.classList.remove('colapsada'); else cardD.classList.add('colapsada');
        } catch(e){}
        if (cardD) { var hD = cardD.querySelector('h4'); if (hD) hD.addEventListener('click', function(){
            var seCierra = !cardD.classList.contains('colapsada');
            cardD.classList.toggle('colapsada');
            try { localStorage.setItem('dhDinamicaAbierto', cardD.classList.contains('colapsada') ? '0' : '1'); } catch(e){}
            if (seCierra) guardarAhora(true); // guardar al plegar
            else setTimeout(function(){ cargarDinamica(false); }, 150); // cargar al abrir (ese es el indicador)
        }); }
        ta.addEventListener('input', marcarSucio, true);
        // Guardar al salir / recargar (beacon no bloquea el cierre)
        window.addEventListener('beforeunload', function(){
            if (!sucio) return;
            var n = nombres(); if (!n.p1 || !n.p2) return;
            try {
                var blob = new Blob([JSON.stringify({p1:n.p1, p2:n.p2, texto:getTexto()})], {type:'application/json'});
                if (navigator.sendBeacon) navigator.sendBeacon('/api/dinamica_compuesta', blob);
            } catch(e){}
        });
        document.addEventListener('visibilitychange', function(){ if (document.hidden) guardarAhora(true); });
        actualizarVisDinamica();
        setTimeout(function(){ actualizarVisDinamica(); cargarDinamica(false); }, 1200);
    })();
    // Registro de visita (Fase 3): avisa entrada y duracion. No bloquea la pagina.
    (function(){
        var t0 = Date.now(), vid = null;
        function seg(){ return Math.round((Date.now() - t0) / 1000); }
        try {
            fetch('/api/visita/inicio', {method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({path: location.pathname, yo: new URLSearchParams(location.search).get('yo')})}).then(function(r){ return r.json(); })
            .then(function(j){ if (j && j.id) vid = j.id; }).catch(function(){});
        } catch(e){}
        function fin(){
            if (!vid) return;
            try {
                var dato = JSON.stringify({id: vid, segundos: seg()});
                if (navigator.sendBeacon) navigator.sendBeacon('/api/visita/fin', new Blob([dato], {type:'application/json'}));
                else fetch('/api/visita/fin', {method:'POST', headers:{'Content-Type':'application/json'}, body: dato, keepalive: true});
            } catch(e){}
        }
        window.addEventListener('pagehide', fin);
        document.addEventListener('visibilitychange', function(){ if (document.hidden) fin(); });
    })();
