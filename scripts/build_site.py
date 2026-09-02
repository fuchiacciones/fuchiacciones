import json, math, os, time, re
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import quote
from html import unescape

ROOT=os.path.dirname(os.path.dirname(__file__))
with open(os.path.join(ROOT,'data','instruments.json'),encoding='utf-8') as f:
    instruments=json.load(f)

UA='Mozilla/5.0 FUCHIACCIONES/1.1'

def get_json(url, timeout=20):
    try:
        req=Request(url,headers={'User-Agent':UA,'Accept':'application/json,text/plain,*/*'})
        with urlopen(req,timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None

def get_text(url, timeout=20):
    try:
        req=Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml,*/*'})
        with urlopen(req,timeout=timeout) as r:
            return r.read().decode('utf-8','ignore')
    except Exception:
        return ''

def yahoo(ticker, range_='5y', interval='1d'):
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?range={range_}&interval={interval}&events=div%2Csplits'
    data=get_json(url)
    try:
        res=data['chart']['result'][0]
        ts=res.get('timestamp',[])
        q=res['indicators']['quote'][0]
        closes=q.get('close',[]); vols=q.get('volume',[])
        return [(t,c,v or 0) for t,c,v in zip(ts,closes,vols) if c is not None]
    except Exception:
        return []

def yahoo_news(query):
    data=get_json('https://query1.finance.yahoo.com/v1/finance/search?q='+quote(query)+'&newsCount=6')
    out=[]
    try:
        for n in data.get('news',[])[:6]:
            title=n.get('title'); link=n.get('link')
            if title and link:
                out.append({'title':title,'link':link,'publisher':n.get('publisher','Yahoo Finance')})
    except Exception:
        pass
    return out

def pct(a,b): return ((a/b)-1)*100 if b else None
def avg(xs): return sum(xs)/len(xs) if xs else 0
def stdev(xs):
    if len(xs)<2:return 0
    m=avg(xs); return math.sqrt(sum((x-m)**2 for x in xs)/(len(xs)-1))

def analyze(rows):
    if len(rows)<65:return None
    closes=[r[1] for r in rows]; vols=[r[2] for r in rows]
    last=closes[-1]; p30=closes[-31]; p60=closes[-61]
    ret30=pct(last,p30); prev30=pct(p30,p60)
    hist800=closes[-800:]
    hist30=[pct(hist800[i],hist800[i-30]) for i in range(30,len(hist800))]
    z=(ret30-avg(hist30))/(stdev(hist30) or 1) if len(hist30)>30 else 0
    vol30=avg(vols[-30:]); vol_prev=avg(vols[-60:-30])
    ma20=avg(closes[-20:]); ma50=avg(closes[-50:]); ma200=avg(closes[-200:]) if len(closes)>=200 else avg(closes)
    hi=max(hist800); lo=min(hist800); vol_ratio=vol30/(vol_prev or 1)
    score=2 if ret30>0 else -2
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
    return {'last':last,'ret30':ret30,'prev30':prev30,'delta':ret30-prev30,'vol_ratio':vol_ratio,
            'ma20':ma20,'ma50':ma50,'ma200':ma200,'high800':hi,'low800':lo,
            'distance_high':pct(last,hi),'distance_low':pct(last,lo),'z30':z,
            'score':score,'action':action,'observations':len(rows)}

def market_snapshot():
    tickers={'S&P 500':'^GSPC','Nasdaq':'^IXIC','Dow Jones':'^DJI','Russell 2000':'^RUT',
             'VIX':'^VIX','Oro':'GC=F','WTI':'CL=F','DXY':'DX-Y.NYB','Treasury 10Y':'^TNX','Bitcoin':'BTC-USD'}
    out=[]
    for name,t in tickers.items():
        rows=yahoo(t,range_='10d',interval='1d')
        if len(rows)>=2:
            last=rows[-1][1]; prev=rows[-2][1]
            out.append({'name':name,'ticker':t,'last':last,'change':pct(last,prev)})
    return out

def forex_factory_calendar():
    data=get_json('https://nfs.faireconomy.media/ff_calendar_thisweek.json',timeout=25)
    if not isinstance(data,list): return []
    now=datetime.now(timezone.utc); end=now+timedelta(days=3); events=[]
    for e in data:
        try:
            dt=datetime.fromisoformat(str(e.get('date','')).replace('Z','+00:00'))
        except Exception:
            continue
        country=e.get('country',''); impact=e.get('impact','')
        if country in ('USD','EUR','GBP','JPY','CNY','CAD') and impact in ('High','Medium'):
            if now-timedelta(hours=12) <= dt <= end:
                events.append({'date':dt.strftime('%d/%m %H:%M UTC'),'country':country,'impact':impact,
                               'title':e.get('title',''),'forecast':e.get('forecast',''),'previous':e.get('previous','')})
    return sorted(events,key=lambda x:x['date'])[:18]

def investing_news():
    html=get_text('https://es.investing.com/news',timeout=20)
    if not html:return []
    titles=[]
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',html,re.I|re.S):
        title=re.sub('<[^>]+>',' ',m.group(2)); title=' '.join(unescape(title).split()); href=m.group(1)
        if len(title)>=35:
            if href.startswith('/'): href='https://es.investing.com'+href
            if href.startswith('http') and not any(x['title']==title for x in titles):
                titles.append({'title':title,'link':href,'publisher':'Investing.com'})
        if len(titles)>=8: break
    return titles

results=[]
for inst in instruments:
    rows=yahoo(inst['ticker']); a=analyze(rows)
    if a: results.append({**inst,**a})
    time.sleep(.05)
results.sort(key=lambda x:x['score'],reverse=True)
now=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
positive=[x for x in results if x['score']>=2][:8]
negative=sorted(results,key=lambda x:x['score'])[:8]
market=market_snapshot(); calendar=forex_factory_calendar()
all_news=(yahoo_news('stock market')[:5]+investing_news()[:5])[:10]

os.makedirs(os.path.join(ROOT,'public'),exist_ok=True)
payload={'generated_at':now,'universe_count':len(instruments),'available_count':len(results),
         'market':market,'calendar':calendar,'news':all_news,'results':results}
with open(os.path.join(ROOT,'public','data.json'),'w',encoding='utf-8') as f:
    json.dump(payload,f,ensure_ascii=False,indent=2)

def money(x): return f'{x:,.2f}' if x is not None else '—'
def pctf(x): return f'{x:+.1f}%' if x is not None else '—'
def row(x):
    cls='up' if x['ret30']>=0 else 'down'
    return f"<tr><td><b>{x['ticker']}</b><br><small>{x['name']}</small></td><td class='{cls}'>{pctf(x['ret30'])}</td><td>{pctf(x['prev30'])}</td><td>{pctf(x['delta'])}</td><td>{x['action']}</td><td>{money(x['last'])}</td></tr>"

cards=''.join([f"<article class='card'><div class='rank'>#{i+1}</div><h3>{x['ticker']} — {x['name']}</h3><strong>{x['action']}</strong><div class='big {('up' if x['ret30']>=0 else 'down')}'>{pctf(x['ret30'])}</div><p>30 días vs. anteriores: <b>{pctf(x['delta'])}</b></p><p>800 ruedas: {pctf(x['distance_high'])} del máximo · {pctf(x['distance_low'])} sobre mínimo.</p></article>" for i,x in enumerate(positive)])
alerts=''.join([f"<li><b>{x['ticker']} — {x['name']}</b> — {x['action']} · 30d {pctf(x['ret30'])} · cambio vs período previo {pctf(x['delta'])}</li>" for x in negative])
mkt=''.join([f"<div class='metric'><b>{x['name']}</b><span>{money(x['last'])}</span><small class='{('up' if (x['change'] or 0)>=0 else 'down')}'>{pctf(x['change'])}</small></div>" for x in market])
cal=''.join([f"<li><b>{x['date']} · {x['country']}</b> · {x['impact']} · {x['title']} · prev. {x['previous'] or '—'} · est. {x['forecast'] or '—'}</li>" for x in calendar])
news_html=''.join([f"<li><a href='{x['link']}' target='_blank' rel='noopener'>{x['title']}</a> <small>({x['publisher']})</small></li>" for x in all_news])
sources=[
('Yahoo Finanzas','Precios, históricos, noticias y mercado global','https://es.finance.yahoo.com/'),
('Investing.com','Cotizaciones, rendimiento, análisis, fundamentales y noticias','https://es.investing.com/'),
('Nasdaq','Market activity, earnings calendar y actividad pre/after market','https://www.nasdaq.com/market-activity'),
('Forex Factory','Calendario macroeconómico y eventos de impacto','https://www.forexfactory.com/calendar'),
('BYMA / BYMADATA','Mercado argentino, Merval, CCL, dólar BYMA y volúmenes','https://www.byma.com.ar/'),
('InvertirOnline','Cotizaciones argentinas, CEDEARs, bonos y volumen','https://iol.invertironline.com/mercado/cotizaciones'),
('Bloomberg','Contexto y titulares financieros cuando sean públicamente accesibles','https://www.bloomberg.com/'),
('Charles Schwab','Research, ratings y contexto; no se accede a cuentas privadas','https://www.schwab.com/investment-research'),
('Earn2Trade','Referencia educativa/operativa; no se usa como fuente primaria de precios','https://www.earn2trade.com/')
]
sources_html=''.join([f"<li><a href='{u}' target='_blank' rel='noopener'><b>{n}</b></a> — {d}</li>" for n,d,u in sources])
table=''.join(row(x) for x in results)

html=f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FUCHIACCIONES — Informe diario</title><style>
body{{font-family:Inter,Arial,sans-serif;background:#f5f6f8;color:#15171a;margin:0}}header{{background:#111827;color:white;padding:28px calc((100% - 1180px)/2)}}main{{max-width:1180px;margin:0 auto;padding:24px}}h1{{margin:0 0 6px;font-size:32px}}h2{{margin-top:34px}}.muted{{color:#aab2c0}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}}.card,.notice{{background:white;border-radius:14px;padding:18px;box-shadow:0 2px 10px #0000000b;border:1px solid #e5e7eb}}.rank{{font-size:12px;color:#6b7280}}.big{{font-size:28px;font-weight:800;margin:12px 0}}.up{{color:#087f5b}}.down{{color:#c92a2a}}table{{width:100%;border-collapse:collapse;background:white;border-radius:12px;overflow:hidden}}th,td{{padding:10px;border-bottom:1px solid #eee;text-align:left}}th{{background:#eef0f3;font-size:12px}}small{{color:#6b7280}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}}.metric{{background:white;border:1px solid #e5e7eb;border-radius:12px;padding:12px}}.metric span{{display:block;font-size:20px;font-weight:800;margin:6px 0}}.metric small{{font-weight:700}}a{{color:#1857a4;text-decoration:none}}footer{{padding:30px;color:#6b7280;font-size:12px}}</style></head><body>
<header><h1>FUCHIACCIONES</h1><div class="muted">Informe automático · {now}</div></header><main>
<section><h2>🔥 RECOMENDACIONES DEL DÍA</h2><p>Ranking generado con momentum, medias móviles, volumen y contexto histórico de hasta 800 ruedas. No constituye asesoramiento financiero personalizado.</p><div class="cards">{cards or '<p>Sin datos disponibles.</p>'}</div></section>
<section><h2>⚠️ ALERTAS</h2><ul>{alerts or '<li>Sin alertas calculadas.</li>'}</ul></section>
<section><h2>📈 MERCADO GLOBAL</h2><div class="metrics">{mkt or '<p>Sin datos.</p>'}</div></section>
<section><h2>📰 NOTICIAS BURSÁTILES</h2><div class="notice"><ul>{news_html or '<li>Sin noticias disponibles.</li>'}</ul></div></section>
<section><h2>📅 CALENDARIO MACRO</h2><div class="notice"><p>Eventos relevantes próximos, con foco en USD y principales economías.</p><ul>{cal or '<li>Sin eventos disponibles.</li>'}</ul></div></section>
<section><h2>🇦🇷 MERCADO ARGENTINO</h2><div class="notice">BYMA/BYMADATA e InvertirOnline quedan incorporados como fuentes prioritarias para acciones, CEDEARs, Merval, CCL, dólar BYMA, volúmenes y datos locales. La información de BYMA está sujeta a las condiciones de acceso/licencia de su Market Data.</div></section>
<section><h2>🌐 FUENTES BURSÁTILES</h2><div class="notice"><ul>{sources_html}</ul></div></section>
<section><h2>📊 UNIVERSO — 30 DÍAS VS. 30 ANTERIORES</h2><table><thead><tr><th>Instrumento</th><th>30d</th><th>30d prev.</th><th>Aceleración</th><th>Señal</th><th>Último</th></tr></thead><tbody>{table}</tbody></table></section>
<footer>FUCHIACCIONES · {len(instruments)} instrumentos configurados · {len(results)} con datos históricos disponibles. Precios históricos: Yahoo Finance. Macro: Forex Factory. Mercado argentino: BYMA/BYMADATA e InvertirOnline. Noticias: Yahoo Finance e Investing.com cuando están públicamente disponibles.</footer>
</main></body></html>"""
with open(os.path.join(ROOT,'public','index.html'),'w',encoding='utf-8') as f:f.write(html)
