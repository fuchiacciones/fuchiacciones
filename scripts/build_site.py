import json, math, os, time, re
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import quote
from html import unescape, escape

ROOT = os.path.dirname(os.path.dirname(__file__))
with open(os.path.join(ROOT, 'data', 'instruments.json'), encoding='utf-8') as f:
    instruments = json.load(f)

UA = 'Mozilla/5.0 FUCHIACCIONES/2.0'
PERIODS = (30, 60, 90, 120, 365)


def get_json(url, timeout=20):
    try:
        req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/plain,*/*'})
        with urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def get_text(url, timeout=20):
    try:
        req = Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,*/*'})
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8', 'ignore')
    except Exception:
        return ''


def yahoo(ticker, range_='5y', interval='1d'):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?range={range_}&interval={interval}&events=div%2Csplits'
    data = get_json(url)
    try:
        res = data['chart']['result'][0]
        ts = res.get('timestamp', [])
        q = res['indicators']['quote'][0]
        closes = q.get('close', [])
        vols = q.get('volume', [])
        return [(t, c, v or 0) for t, c, v in zip(ts, closes, vols) if c is not None]
    except Exception:
        return []


def yahoo_news(query, count=6):
    data = get_json('https://query1.finance.yahoo.com/v1/finance/search?q=' + quote(query) + f'&newsCount={count}')
    out = []
    try:
        for n in data.get('news', [])[:count]:
            title = n.get('title')
            link = n.get('link')
            if title and link:
                out.append({
                    'title': title,
                    'link': link,
                    'publisher': n.get('publisher', 'Yahoo Finance'),
                    'published': n.get('providerPublishTime'),
                    'related': n.get('relatedTickers', []) or []
                })
    except Exception:
        pass
    return out


def pct(a, b):
    return ((a / b) - 1) * 100 if b else None


def avg(xs):
    return sum(xs) / len(xs) if xs else 0


def stdev(xs):
    if len(xs) < 2:
        return 0
    m = avg(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def period_returns(closes):
    out = {}
    for days in PERIODS:
        out[str(days)] = pct(closes[-1], closes[-1-days]) if len(closes) > days else None
    return out


def analyze(rows):
    if len(rows) < 366:
        return None
    closes = [r[1] for r in rows]
    vols = [r[2] for r in rows]
    last = closes[-1]
    returns = period_returns(closes)

    # Long history is retained only as an internal statistical reference.
    hist800 = closes[-800:]
    hist30 = [pct(hist800[i], hist800[i-30]) for i in range(30, len(hist800))]
    z30 = (returns['30'] - avg(hist30)) / (stdev(hist30) or 1) if len(hist30) > 30 and returns['30'] is not None else 0

    vol30 = avg(vols[-30:])
    vol_prev = avg(vols[-60:-30])
    vol_ratio = vol30 / (vol_prev or 1)
    ma20 = avg(closes[-20:])
    ma50 = avg(closes[-50:])
    ma200 = avg(closes[-200:])

    technical_score = 0.0
    r30, r60, r90, r120, r365 = [returns[str(x)] for x in PERIODS]
    if r30 is not None: technical_score += 2 if r30 > 0 else -2
    if r60 is not None: technical_score += 1 if r60 > 0 else -1
    if r90 is not None: technical_score += 1 if r90 > 0 else -1
    if r120 is not None: technical_score += 1 if r120 > 0 else -1
    if r365 is not None: technical_score += 1 if r365 > 0 else -1
    technical_score += 1 if last > ma20 else -1
    technical_score += 1 if last > ma50 else -1
    technical_score += 1 if last > ma200 else -1
    if vol_ratio > 1.25 and r30 is not None and r30 > 0:
        technical_score += 1
    if vol_ratio > 1.5 and r30 is not None and r30 < 0:
        technical_score -= 1

    return {
        'last': last,
        'returns': returns,
        'ret30': r30,
        'vol_ratio': vol_ratio,
        'ma20': ma20,
        'ma50': ma50,
        'ma200': ma200,
        'z30': z30,
        'technical_score': technical_score,
        'observations': len(rows)
    }


POSITIVE_WORDS = {
    'beat': 1.2, 'beats': 1.2, 'surge': 1.2, 'surges': 1.2, 'jump': 0.9, 'jumps': 0.9,
    'rally': 1.0, 'rallies': 1.0, 'growth': 0.8, 'grow': 0.6, 'profit': 0.8,
    'profits': 0.8, 'record': 0.8, 'upgrade': 1.2, 'upgraded': 1.2, 'bullish': 1.2,
    'outperform': 1.0, 'strong': 0.7, 'raises': 0.9, 'raised': 0.9, 'forecast': 0.3,
    'guidance': 0.2, 'expands': 0.6, 'deal': 0.5, 'partnership': 0.5,
    'supera': 1.2, 'crece': 0.8, 'crecimiento': 0.8, 'ganancias': 0.8,
    'récord': 0.8, 'sube': 0.8, 'alcista': 1.1, 'mejora': 0.7, 'mejoró': 0.7,
    'eleva': 0.8, 'acuerdo': 0.5, 'expande': 0.6
}
NEGATIVE_WORDS = {
    'miss': -1.2, 'misses': -1.2, 'fall': -0.9, 'falls': -0.9, 'drop': -1.0,
    'drops': -1.0, 'plunge': -1.4, 'plunges': -1.4, 'loss': -1.0, 'losses': -1.0,
    'downgrade': -1.2, 'downgraded': -1.2, 'bearish': -1.2, 'underperform': -1.0,
    'weak': -0.7, 'cuts': -0.9, 'cut': -0.8, 'warning': -1.0, 'lawsuit': -0.8,
    'recall': -0.7, 'investigation': -0.8, 'probe': -0.8, 'debt': -0.3,
    'decline': -0.8, 'slump': -1.0, 'crisis': -1.2, 'risk': -0.3,
    'pierde': -0.9, 'cae': -0.9, 'caída': -0.9, 'pérdida': -1.0,
    'rebaja': -1.2, 'bajista': -1.1, 'débil': -0.7, 'recorte': -0.8,
    'advertencia': -1.0, 'demanda': -0.6, 'investigación': -0.8, 'riesgo': -0.3
}


def news_sentiment(items, ticker, company):
    score = 0.0
    used = []
    now_ts = datetime.now(timezone.utc).timestamp()
    company_words = [w.lower() for w in re.findall(r'[A-Za-zÁÉÍÓÚáéíóúÑñ]{4,}', company)
                     if w.lower() not in {'class', 'holding', 'group', 'energy', 'fund'}]
    for n in items:
        title = n['title']
        low = title.lower()
        related = [str(x).upper() for x in n.get('related', [])]
        relevant = (ticker.upper() in related) or ticker.lower() in low or any(w in low for w in company_words[:3])
        if not relevant:
            continue
        s = 0.0
        for w, v in POSITIVE_WORDS.items():
            if re.search(r'\b' + re.escape(w) + r'\b', low): s += v
        for w, v in NEGATIVE_WORDS.items():
            if re.search(r'\b' + re.escape(w) + r'\b', low): s += v
        if s == 0:
            continue
        if n.get('published'):
            age_days = max(0, (now_ts - float(n['published'])) / 86400)
            weight = 1.0 if age_days <= 2 else (0.65 if age_days <= 7 else 0.35)
        else:
            weight = 0.5
        score += s * weight
        used.append({**n, 'sentiment': round(s * weight, 2)})
    return max(-3.0, min(3.0, score)), used[:5]


def final_action(score):
    if score >= 6: return 'COMPRAR'
    if score >= 3: return 'ACUMULAR'
    if score >= 0.5: return 'MANTENER'
    if score > -2.5: return 'ESPERAR'
    return 'REDUCIR / EVITAR'


def cross_recommendation(item, news_score, news_items, market_bias=0):
    score = item['technical_score'] + news_score + market_bias
    action = final_action(score)
    r = item['returns']
    reasons = []
    if r['30'] is not None: reasons.append(f"30d {r['30']:+.1f}%")
    if r['365'] is not None: reasons.append(f"365d {r['365']:+.1f}%")
    reasons.append('sobre MM50' if item['last'] > item['ma50'] else 'bajo MM50')
    if news_score > 0.4: reasons.append('noticias favorables')
    elif news_score < -0.4: reasons.append('noticias desfavorables')
    else: reasons.append('sin sesgo noticioso fuerte')
    return {
        'score': round(score, 2), 'action': action, 'news_score': round(news_score, 2),
        'news_count': len(news_items), 'reasons': reasons[:4], 'news': news_items
    }


def market_period_snapshot():
    tickers = {
        'S&P 500': '^GSPC', 'Nasdaq': '^IXIC', 'Dow Jones': '^DJI', 'Russell 2000': '^RUT',
        'VIX': '^VIX', 'Oro': 'GC=F', 'WTI': 'CL=F', 'DXY': 'DX-Y.NYB',
        'Treasury 10Y': '^TNX', 'Bitcoin': 'BTC-USD'
    }
    out = []
    for name, ticker in tickers.items():
        rows = yahoo(ticker, range_='2y', interval='1d')
        a = analyze(rows)
        if a: out.append({'name': name, 'ticker': ticker, **a})
    return out


def forex_factory_calendar():
    data = get_json('https://nfs.faireconomy.media/ff_calendar_thisweek.json', timeout=25)
    if not isinstance(data, list): return []
    now = datetime.now(timezone.utc); end = now + timedelta(days=3); events = []
    for e in data:
        try: dt = datetime.fromisoformat(str(e.get('date', '')).replace('Z', '+00:00'))
        except Exception: continue
        country = e.get('country', ''); impact = e.get('impact', '')
        if country in ('USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CAD') and impact in ('High', 'Medium') and now-timedelta(hours=12) <= dt <= end:
            events.append({'date': dt.strftime('%d/%m %H:%M UTC'), 'country': country, 'impact': impact,
                           'title': e.get('title', ''), 'forecast': e.get('forecast', ''), 'previous': e.get('previous', '')})
    return sorted(events, key=lambda x: x['date'])[:18]


def investing_news():
    html = get_text('https://es.investing.com/news', timeout=20)
    if not html: return []
    titles = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S):
        title = re.sub('<[^>]+>', ' ', m.group(2)); title = ' '.join(unescape(title).split()); href = m.group(1)
        if len(title) >= 35:
            if href.startswith('/'): href = 'https://es.investing.com' + href
            if href.startswith('http') and not any(x['title'] == title for x in titles):
                titles.append({'title': title, 'link': href, 'publisher': 'Investing.com'})
        if len(titles) >= 10: break
    return titles


results = []
for inst in instruments:
    rows = yahoo(inst['ticker'])
    a = analyze(rows)
    if a: results.append({**inst, **a})
    time.sleep(.04)

market = market_period_snapshot()
calendar = forex_factory_calendar()
market_map = {x['ticker']: x for x in market}
spy30 = market_map.get('^GSPC', {}).get('returns', {}).get('30')
qqq30 = market_map.get('^IXIC', {}).get('returns', {}).get('30')
market_bias = 0.5 if (spy30 is not None and qqq30 is not None and spy30 > 0 and qqq30 > 0) else (-0.5 if (spy30 is not None and qqq30 is not None and spy30 < 0 and qqq30 < 0) else 0)

for x in results:
    news = yahoo_news(f"{x['ticker']} {x['name']} stock", count=6)
    ns, used = news_sentiment(news, x['ticker'], x['name'])
    x['news_score'] = ns
    x['news_count'] = len(used)
    x['cross'] = cross_recommendation(x, ns, used, market_bias)
    time.sleep(.04)

results.sort(key=lambda x: x['cross']['score'], reverse=True)
positive = [x for x in results if x['cross']['score'] >= 3][:8]
negative = sorted(results, key=lambda x: x['cross']['score'])[:8]
all_news = (yahoo_news('stock market', 6)[:5] + investing_news()[:5])[:10]

now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
os.makedirs(os.path.join(ROOT, 'public'), exist_ok=True)
payload = {'generated_at': now, 'universe_count': len(instruments), 'available_count': len(results),
           'periods': list(PERIODS), 'market_bias': market_bias, 'market': market,
           'calendar': calendar, 'news': all_news, 'results': results}
with open(os.path.join(ROOT, 'public', 'data.json'), 'w', encoding='utf-8') as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)


def money(x): return f'{x:,.2f}' if x is not None else '—'
def pctf(x): return f'{x:+.1f}%' if x is not None else '—'
def action_cls(a): return 'buy' if a in ('COMPRAR', 'ACUMULAR') else ('sell' if 'EVITAR' in a or 'REDUCIR' in a else 'hold')

def period_grid(x, mini=False):
    return ''.join(f"<div><small>{d}d</small><b>{pctf(x['returns'][str(d)])}</b></div>" for d in PERIODS)

def period_cells(x):
    r = x['returns']
    return ''.join(f"<td class='{('up' if (r[str(d)] or 0) >= 0 else 'down')}'>{pctf(r[str(d)])}</td>" for d in PERIODS)

def table_row(x):
    a = x['cross']['action']
    return f"<tr><td><b>{escape(x['ticker'])}</b><br><small>{escape(x['name'])}</small></td>{period_cells(x)}<td><span class='pill {action_cls(a)}'>{a}</span></td><td>{x['cross']['score']:+.1f}</td></tr>"

cards = ''.join([
    f"<article class='card'><div class='rank'>#{i+1}</div><h3>{escape(x['ticker'])} — {escape(x['name'])}</h3>"
    f"<span class='pill {action_cls(x['cross']['action'])}'>{x['cross']['action']}</span>"
    f"<div class='big'>{pctf(x['returns']['30'])}</div>"
    f"<div class='period-grid'>{period_grid(x)}</div>"
    f"<p><b>Señal combinada:</b> {escape(', '.join(x['cross']['reasons']))}.</p>"
    f"<p>Noticias analizadas: {x['news_count']} · score {x['cross']['score']:+.1f}</p></article>"
    for i, x in enumerate(positive)
])

alerts = ''.join([
    f"<li><b>{escape(x['ticker'])} — {escape(x['name'])}</b> — <span class='pill {action_cls(x['cross']['action'])}'>{x['cross']['action']}</span> "
    f"· 30d {pctf(x['returns']['30'])} · 60d {pctf(x['returns']['60'])} · 90d {pctf(x['returns']['90'])} · "
    f"120d {pctf(x['returns']['120'])} · 365d {pctf(x['returns']['365'])}</li>"
    for x in negative
])

def market_html():
    return ''.join([
        f"<article class='metric'><b>{escape(x['name'])}</b><span>{money(x['last'])}</span>"
        f"<div class='period-grid mini'>{period_grid(x, True)}</div></article>"
        for x in market
    ])

cal = ''.join([f"<li><b>{escape(x['date'])} · {escape(x['country'])}</b> · {escape(x['impact'])} · {escape(x['title'])} · prev. {escape(x['previous'] or '—')} · est. {escape(x['forecast'] or '—')}</li>" for x in calendar])
news_html = ''.join([f"<li><a href='{escape(x['link'], quote=True)}' target='_blank' rel='noopener'>{escape(x['title'])}</a> <small>({escape(x['publisher'])})</small></li>" for x in all_news])

arg_tickers = {'LOMA','CRESY','GGAL','YPF','BMA','PAM','TEO','ARGT'}
argentina = [x for x in results if x['ticker'] in arg_tickers]
argentina.sort(key=lambda x: x['cross']['score'], reverse=True)
arg_table = ''.join(table_row(x) for x in argentina)
table = ''.join(table_row(x) for x in results)

cross_cards = ''.join([
    f"<article class='card'><h3>{escape(x['ticker'])} — {escape(x['name'])}</h3>"
    f"<span class='pill {action_cls(x['cross']['action'])}'>{x['cross']['action']}</span>"
    f"<p><b>Score combinado:</b> {x['cross']['score']:+.1f} · técnico {x['technical_score']:+.1f} · noticias {x['news_score']:+.1f}</p>"
    f"<p>{escape('; '.join(x['cross']['reasons']))}.</p>"
    f"<p><small>{x['news_count']} noticia(s) relevante(s) incorporada(s) al cruce.</small></p></article>"
    for x in results[:10]
])

sources = [
    ('Yahoo Finanzas','Precios, históricos y noticias por instrumento','https://es.finance.yahoo.com/'),
    ('Investing.com','Noticias y contexto de mercado públicamente accesibles','https://es.investing.com/'),
    ('Nasdaq','Market activity, earnings calendar y actividad pre/after market','https://www.nasdaq.com/market-activity'),
    ('Forex Factory','Calendario macroeconómico y eventos de impacto','https://www.forexfactory.com/calendar'),
    ('BYMA / BYMADATA','Mercado argentino, Merval, CCL, dólar BYMA y volúmenes','https://www.byma.com.ar/'),
    ('InvertirOnline','Cotizaciones argentinas, CEDEARs, bonos y volumen','https://iol.invertironline.com/mercado/cotizaciones'),
    ('Bloomberg','Contexto y titulares financieros cuando sean públicamente accesibles','https://www.bloomberg.com/'),
    ('Charles Schwab','Research, ratings y contexto; no se accede a cuentas privadas','https://www.schwab.com/investment-research'),
    ('Earn2Trade','Referencia educativa/operativa; no se usa como fuente primaria de precios','https://www.earn2trade.com/')
]
sources_html = ''.join([f"<li><a href='{u}' target='_blank' rel='noopener'><b>{escape(n)}</b></a> — {escape(d)}</li>" for n,d,u in sources])

html = f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>FUCHIACCIONES — Informe diario</title><style>
body{{font-family:Inter,Arial,sans-serif;background:#f5f6f8;color:#15171a;margin:0}}header{{background:#111827;color:white;padding:28px calc((100% - 1180px)/2)}}main{{max-width:1180px;margin:0 auto;padding:24px}}h1{{margin:0 0 6px;font-size:32px}}h2{{margin-top:34px}}.muted{{color:#aab2c0}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px}}.card,.notice{{background:white;border-radius:14px;padding:18px;box-shadow:0 2px 10px #0000000b;border:1px solid #e5e7eb}}.rank{{font-size:12px;color:#6b7280}}.big{{font-size:28px;font-weight:800;margin:10px 0}}.up{{color:#087f5b}}.down{{color:#c92a2a}}table{{width:100%;border-collapse:collapse;background:white;border-radius:12px;overflow:hidden}}th,td{{padding:9px;border-bottom:1px solid #eee;text-align:left;font-size:13px}}th{{background:#eef0f3;font-size:12px;position:sticky;top:0}}small{{color:#6b7280}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}}.metric{{background:white;border:1px solid #e5e7eb;border-radius:12px;padding:12px}}.metric span{{display:block;font-size:20px;font-weight:800;margin:6px 0}}.period-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin:10px 0}}.period-grid div{{background:#f3f4f6;border-radius:8px;padding:7px;text-align:center}}.period-grid b,.period-grid small{{display:block}}.mini{{margin:0}}.mini div{{padding:5px}}.pill{{display:inline-block;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:800;background:#e5e7eb}}.pill.buy{{background:#d8f3e6;color:#087f5b}}.pill.sell{{background:#fde2e2;color:#b42318}}.pill.hold{{background:#fff0c2;color:#8a5a00}}.notice{{line-height:1.5}}a{{color:#1857a4;text-decoration:none}}footer{{padding:30px;color:#6b7280;font-size:12px}}.scroll{{overflow:auto}}</style></head><body>
<header><h1>FUCHIACCIONES</h1><div class='muted'>Informe automático · {now}</div></header><main>
<section><h2>🔥 RECOMENDACIONES DEL DÍA</h2><p>Las recomendaciones combinan comportamiento de precio y volumen con el cruce de noticias relevantes por empresa. La comparación visible es exclusivamente <b>30, 60, 90, 120 y 365 días</b>. No constituye asesoramiento financiero personalizado.</p><div class='cards'>{cards or '<p>Sin datos disponibles.</p>'}</div></section>
<section><h2>🧠 CRUCE DE NOTICIAS + DATOS BURSÁTILES</h2><div class='notice'><p><b>Cómo se genera:</b> el motor toma el score técnico, las variaciones de 30/60/90/120/365 días, tendencia respecto de MM20/MM50/MM200, volumen y titulares recientes específicos del instrumento. Luego pondera el sesgo de las noticias y el régimen general del S&P 500/Nasdaq.</p><div class='cards'>{cross_cards or '<p>Sin datos.</p>'}</div></div></section>
<section><h2>⚠️ ALERTAS</h2><div class='notice'><ul>{alerts or '<li>Sin alertas calculadas.</li>'}</ul></div></section>
<section><h2>📈 MERCADO GLOBAL</h2><p>Todos los indicadores muestran rendimiento acumulado a 30, 60, 90, 120 y 365 días.</p><div class='metrics'>{market_html() or '<p>Sin datos.</p>'}</div></section>
<section><h2>📰 NOTICIAS BURSÁTILES</h2><div class='notice'><ul>{news_html or '<li>Sin noticias disponibles.</li>'}</ul></div></section>
<section><h2>📅 CALENDARIO MACRO</h2><div class='notice'><p>Eventos relevantes próximos, con foco en USD y principales economías.</p><ul>{cal or '<li>Sin eventos disponibles.</li>'}</ul></div></section>
<section><h2>🇦🇷 MERCADO ARGENTINO</h2><p>Instrumentos argentinos/Argentina-focused del universo, con la misma matriz de comparación 30/60/90/120/365 días.</p><div class='scroll'><table><thead><tr><th>Instrumento</th><th>30d</th><th>60d</th><th>90d</th><th>120d</th><th>365d</th><th>Señal</th><th>Score</th></tr></thead><tbody>{arg_table or '<tr><td colspan=8>Sin datos.</td></tr>'}</tbody></table></div></section>
<section><h2>🌐 FUENTES BURSÁTILES</h2><div class='notice'><ul>{sources_html}</ul></div></section>
<section><h2>📊 UNIVERSO — 30 / 60 / 90 / 120 / 365 DÍAS</h2><div class='scroll'><table><thead><tr><th>Instrumento</th><th>30d</th><th>60d</th><th>90d</th><th>120d</th><th>365d</th><th>Señal</th><th>Score</th></tr></thead><tbody>{table}</tbody></table></div></section>
<footer>FUCHIACCIONES · {len(instruments)} instrumentos configurados · {len(results)} con datos suficientes. Precios históricos: Yahoo Finance. Noticias: Yahoo Finance e Investing.com cuando están públicamente disponibles. Macro: Forex Factory. Mercado argentino: BYMA/BYMADATA e InvertirOnline.</footer>
</main></body></html>"""
with open(os.path.join(ROOT, 'public', 'index.html'), 'w', encoding='utf-8') as f:
    f.write(html)
