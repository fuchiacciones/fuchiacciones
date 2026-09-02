import json, math, os, time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote

ROOT=os.path.dirname(os.path.dirname(__file__))
with open(os.path.join(ROOT,'data','instruments.json'),encoding='utf-8') as f: instruments=json.load(f)

UA='Mozilla/5.0 FUCHIACCIONES/1.0'
def yahoo(ticker):
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?range=5y&interval=1d&events=div%2Csplits'
    req=Request(url,headers={'User-Agent':UA})
    try:
        with urlopen(req,timeout=20) as r: data=json.load(r)
        res=data['chart']['result'][0]
        ts=res.get('timestamp',[]); q=res['indicators']['quote'][0]; closes=q.get('close',[]); vols=q.get('volume',[])
        rows=[(t,c,v or 0) for t,c,v in zip(ts,closes,vols) if c is not None]
        return rows
    except Exception as e:
        return []

def pct(a,b): return ((a/b)-1)*100 if b else None
def avg(xs): return sum(xs)/len(xs) if xs else 0
def stdev(xs):
    if len(xs)<2:return 0
    m=avg(xs); return math.sqrt(sum((x-m)**2 for x in xs)/(len(xs)-1))

def analyze(rows):
    if len(rows)<65:return None
    closes=[r[1] for r in rows]; vols=[r[2] for r in rows]
    last=closes[-1]
    p30=closes[-31] if len(closes)>=31 else closes[0]
    p60=closes[-61] if len(closes)>=61 else closes[0]
    ret30=pct(last,p30); prev30=pct(p30,p60)
    returns=[pct(closes[i],closes[i-1]) for i in range(1,len(closes))]
    ret_hist=[x for x in returns if x is not None]
    vol30=avg(vols[-30:]); vol_prev=avg(vols[-60:-30])
    ma20=avg(closes[-20:]); ma50=avg(closes[-50:]); ma200=avg(closes[-200:]) if len(closes)>=200 else avg(closes)
    hist800=closes[-800:]
    hi=max(hist800); lo=min(hist800)
    z=(ret30-avg([pct(hist800[i],hist800[i-30]) for i in range(30,len(hist800))]))/(stdev([pct(hist800[i],hist800[i-30]) for i in range(30,len(hist800))]) or 1) if len(hist800)>60 else 0
    vol_ratio=vol30/(vol_prev or 1)
    score=0
    score += 2 if ret30>0 else -2
    score += 1 if ret30>prev30 else -1
    score += 1 if last>ma20 else -1
    score += 1 if last>ma50 else -1
    score += 1 if last>ma200 else -1
    score += 1 if vol_ratio>1.25 and ret30>0 else 0
    score -= 1 if vol_ratio>1.5 and ret30<0 else 0
    if score>=4: action='COMPRAR / ACUMULAR'
    elif score>=2: action='POSITIVO'
    elif score<=-4: action='EVITAR / VENDER'
    elif score<=-2: action='NEGATIVO'
    else: action='MANTENER / ESPERAR'
    return {'last':last,'ret30':ret30,'prev30':prev30,'delta':ret30-prev30,'vol_ratio':vol_ratio,'ma20':ma20,'ma50':ma50,'ma200':ma200,'high800':hi,'low800':lo,'distance_high':pct(last,hi),'distance_low':pct(last,lo),'z30':z,'score':score,'action':action,'observations':len(rows)}

results=[]
for inst in instruments:
    rows=yahoo(inst['ticker']); a=analyze(rows)
    if a:
        results.append({**inst,**a})
    time.sleep(.08)
results.sort(key=lambda x:x['score'],reverse=True)
now=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
positive=[x for x in results if x['score']>=2][:8]
negative=sorted(results,key=lambda x:x['score'])[:8]

os.makedirs(os.path.join(ROOT,'public'),exist_ok=True)
with open(os.path.join(ROOT,'public','data.json'),'w',encoding='utf-8') as f: json.dump({'generated_at':now,'universe_count':len(instruments),'available_count':len(results),'results':results},f,ensure_ascii=False,indent=2)

def money(x): return f'{x:,.2f}' if x is not None else '—'
def pctf(x): return f'{x:+.1f}%' if x is not None else '—'
def row(x):
    cls='up' if x['ret30']>=0 else 'down'
    return f"<tr><td><b>{x['ticker']}</b><br><small>{x['name']}</small></td><td class='{cls}'>{pctf(x['ret30'])}</td><td>{pctf(x['prev30'])}</td><td>{pctf(x['delta'])}</td><td>{x['action']}</td><td>{money(x['last'])}</td></tr>"

cards=''.join([f"<article class='card'><div class='rank'>#{i+1}</div><h3>{x['ticker']}</h3><p>{x['name']}</p><strong>{x['action']}</strong><div class='big {('up' if x['ret30']>=0 else 'down')}'>{pctf(x['ret30'])}</div><p>30 días vs. anteriores: <b>{pctf(x['delta'])}</b></p><p>Histórico 800 ruedas: {pctf(x['distance_high'])} del máximo · {pctf(x['distance_low'])} sobre mínimo.</p></article>" for i,x in enumerate(positive)])
alerts=''.join([f"<li><b>{x['ticker']}</b> — {x['action']} · 30d {pctf(x['ret30'])} · cambio vs período previo {pctf(x['delta'])}</li>" for x in negative])
table=''.join(row(x) for x in results)
html=f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FUCHIACCIONES — Informe diario</title><style>body{{font-family:Inter,Arial,sans-serif;background:#f5f6f8;color:#15171a;margin:0}}header{{background:#111827;color:white;padding:28px calc((100% - 1180px)/2)}}main{{max-width:1180px;margin:0 auto;padding:24px}}h1{{margin:0 0 6px;font-size:32px}}h2{{margin-top:34px}}.muted{{color:#aab2c0}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}.card{{background:white;border-radius:14px;padding:18px;box-shadow:0 2px 10px #0000000b;border:1px solid #e5e7eb}}.rank{{font-size:12px;color:#6b7280}}.big{{font-size:28px;font-weight:800;margin:12px 0}}.up{{color:#087f5b}}.down{{color:#c92a2a}}table{{width:100%;border-collapse:collapse;background:white;border-radius:12px;overflow:hidden}}th,td{{padding:10px;border-bottom:1px solid #eee;text-align:left}}th{{background:#eef0f3;font-size:12px}}small{{color:#6b7280}}.notice{{background:#fff8e6;border:1px solid #f1d58a;padding:16px;border-radius:12px}}footer{{padding:30px;color:#6b7280;font-size:12px}}</style></head><body><header><h1>FUCHIACCIONES</h1><div class="muted">Informe automático · {now}</div></header><main><section><h2>🔥 RECOMENDACIONES DEL DÍA</h2><p>Ranking preliminar generado con momentum, medias móviles, volumen y contexto histórico de hasta 800 ruedas. No constituye asesoramiento financiero personalizado.</p><div class="cards">{cards or '<p>Sin datos disponibles.</p>'}</div></section><section><h2>⚠️ ALERTAS</h2><ul>{alerts or '<li>Sin alertas calculadas.</li>'}</ul></section><section><h2>🇺🇸 MACRO / FED / NOTICIAS</h2><div class="notice"><b>Integración de fuentes en curso.</b><br>La V1 deja preparada esta sección para incorporar calendario FOMC, indicadores económicos, earnings, guidance, noticias y recomendaciones de analistas. Los precios históricos se obtienen de Yahoo Finance cuando están disponibles.</div></section><section><h2>📊 UNIVERSO — 30 DÍAS VS. 30 ANTERIORES</h2><table><thead><tr><th>Instrumento</th><th>30d</th><th>30d prev.</th><th>Aceleración</th><th>Señal</th><th>Último</th></tr></thead><tbody>{table}</tbody></table></section><footer>FUCHIACCIONES · {len(instruments)} instrumentos configurados · {len(results)} con datos históricos disponibles. El análisis histórico usa hasta 800 ruedas para detectar movimientos anómalos.</footer></main></body></html>'''
with open(os.path.join(ROOT,'public','index.html'),'w',encoding='utf-8') as f:f.write(html)
