import json, re, time, os
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import quote
from html import escape, unescape

ROOT = os.path.dirname(os.path.dirname(__file__))
PUBLIC = os.path.join(ROOT, 'public')
UA = 'Mozilla/5.0 FUCHIACCIONES/3.0'


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


def yahoo_chart(ticker, range_='3mo'):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?range={range_}&interval=1d&events=div%2Csplits'
    data = get_json(url)
    try:
        res = data['chart']['result'][0]
        closes = res['indicators']['quote'][0].get('close', [])
        return [x for x in closes if x is not None]
    except Exception:
        return []


def yahoo_screener(scr_id, count=250):
    url = f'https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&lang=en-US&region=US&scrIds={scr_id}&count={count}&corsDomain=finance.yahoo.com'
    data = get_json(url, timeout=25)
    try:
        return data['finance']['result'][0].get('quotes', [])
    except Exception:
        return []


def pct(a, b):
    return ((a / b) - 1) * 100 if b else None


def us_top_30():
    # Build a broad US equity candidate pool from several Yahoo screeners, then
    # calculate the actual 30-session performance for every candidate.
    ids = ('day_gainers', 'most_actives', 'small_cap_gainers', 'growth_technology_stocks')
    candidates = {}
    for sid in ids:
        for q in yahoo_screener(sid, 250):
            ticker = q.get('symbol')
            if not ticker:
                continue
            region = str(q.get('region', 'US')).upper()
            if region and region not in ('US', 'USA'):
                continue
            if q.get('quoteType') not in (None, 'EQUITY'):
                continue
            price = q.get('regularMarketPrice') or q.get('postMarketPrice')
            if price is not None and price < 1:
                continue
            candidates[ticker] = {
                'ticker': ticker,
                'name': q.get('longName') or q.get('shortName') or ticker,
                'exchange': q.get('fullExchangeName') or q.get('exchange') or ''
            }
    ranked = []
    for ticker, item in candidates.items():
        closes = yahoo_chart(ticker, '3mo')
        if len(closes) < 31:
            continue
        r30 = pct(closes[-1], closes[-31])
        if r30 is not None:
            ranked.append({**item, 'return_30d': r30})
        time.sleep(.015)
    ranked.sort(key=lambda x: x['return_30d'], reverse=True)
    return ranked[:30]


THEMES = {
    'Resultados / balance': ('earnings', 'revenue', 'profit', 'eps', 'quarter', 'results', 'guidance', 'forecast', 'balance', 'ganancias', 'ingresos'),
    'Tecnología / IA': ('ai', 'artificial intelligence', 'technology', 'chip', 'semiconductor', 'cloud', 'software', 'robot', 'data center', 'inteligencia artificial', 'tecnología'),
    'Adquisiciones / fusiones': ('acquire', 'acquisition', 'merger', 'takeover', 'buyout', 'acuerdo de compra', 'adquisición', 'fusión'),
    'Productos / innovación': ('launch', 'launches', 'product', 'platform', 'drug', 'approval', 'patent', 'innovation', 'new model', 'nuevo producto', 'innovación', 'aprobación'),
    'Contratos / alianzas': ('contract', 'partnership', 'deal', 'agreement', 'customer', 'orders', 'alianza', 'contrato', 'acuerdo', 'pedidos'),
    'Regulación / riesgo': ('regulator', 'regulation', 'lawsuit', 'investigation', 'recall', 'antitrust', 'regulador', 'demanda', 'investigación', 'multa')
}


def classify(title):
    low = title.lower()
    for theme, words in THEMES.items():
        if any(w in low for w in words):
            return theme
    return None


def translate_es(text):
    # Best-effort public translation. If unavailable, retain the original headline.
    try:
        url = 'https://api.mymemory.translated.net/get?q=' + quote(text) + '&langpair=en|es'
        data = get_json(url, timeout=12)
        out = data.get('responseData', {}).get('translatedText') if data else None
        if out and len(out) > 8 and 'MYMEMORY WARNING' not in out.upper():
            return unescape(out)
    except Exception:
        pass
    return text


def yahoo_news(query, count=8):
    data = get_json('https://query1.finance.yahoo.com/v1/finance/search?q=' + quote(query) + f'&newsCount={count}')
    out = []
    try:
        for n in data.get('news', [])[:count]:
            title, link = n.get('title'), n.get('link')
            if title and link:
                out.append({'title': title, 'link': link, 'publisher': n.get('publisher', 'Yahoo Finance'), 'published': n.get('providerPublishTime'), 'related': n.get('relatedTickers', []) or []})
    except Exception:
        pass
    return out


def improved_news():
    queries = (
        'US stocks earnings results guidance revenue profit',
        'US stocks artificial intelligence technology product launch',
        'US stocks acquisition merger takeover deal',
        'US stocks contracts partnerships orders new products'
    )
    seen = set(); items = []
    for q in queries:
        for n in yahoo_news(q, 8):
            key = n['title'].strip().lower()
            theme = classify(n['title'])
            if not theme or key in seen:
                continue
            seen.add(key)
            n['theme'] = theme
            n['title_es'] = translate_es(n['title'])
            items.append(n)
            if len(items) >= 15:
                break
        if len(items) >= 15:
            break
    return items


def yahoo_history_url(ticker):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=365)
    p1 = int(start.timestamp())
    p2 = int(now.timestamp())
    return f'https://finance.yahoo.com/quote/{quote(ticker)}/history/?period1={p1}&period2={p2}&frequency=1d'


def link_tickers(html, tickers):
    for ticker in sorted(tickers, key=len, reverse=True):
        url = yahoo_history_url(ticker)
        pattern = rf'(?<![\w\-])({re.escape(ticker)})(?![\w\-])'
        html = re.sub(pattern, lambda m: f"<a href='{escape(url, quote=True)}' target='_blank' rel='noopener' title='Historial de {escape(ticker)} · 365 días'>{m.group(1)}</a>", html)
    return html


def main():
    data_path = os.path.join(PUBLIC, 'data.json')
    html_path = os.path.join(PUBLIC, 'index.html')
    data = json.load(open(data_path, encoding='utf-8'))
    html = open(html_path, encoding='utf-8').read()

    top30 = us_top_30()
    data['us_top_30_30d'] = top30
    data['news'] = improved_news()
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Remove the previous cross-analysis section completely.
    html = re.sub(r"<section><h2>🧠 CRUCE DE NOTICIAS \+ DATOS BURSÁTILES</h2>.*?</section>\s*", '', html, count=1, flags=re.S)

    # Remove old news section; a company-focused version is inserted below.
    html = re.sub(r"<section><h2>📰 NOTICIAS BURSÁTILES</h2>.*?</section>\s*", '', html, count=1, flags=re.S)

    gainers = ''.join(
        f"<tr><td><b>{escape(x['ticker'])}</b></td><td>{escape(x['name'])}</td><td class='up'><b>{x['return_30d']:+.1f}%</b></td><td><a href='{escape(yahoo_history_url(x['ticker']), quote=True)}' target='_blank' rel='noopener'>Yahoo · 365 días</a></td></tr>"
        for x in top30
    ) or '<tr><td colspan=4>No se pudieron obtener datos suficientes.</td></tr>'
    gainer_section = f"""<section><h2>🚀 30 ACCIONES DE EE.UU. QUE MÁS SUBIERON EN 30 DÍAS</h2><p>Ranking independiente del universo de FUCHIACCIONES. Se calcula con rendimiento de las últimas 30 ruedas disponibles y una muestra amplia de acciones estadounidenses obtenida de los screeners públicos de Yahoo Finance.</p><div class='scroll'><table><thead><tr><th>#</th><th>Acción</th><th>Empresa</th><th>30 días</th><th>Historial</th></tr></thead><tbody>{''.join(f'<tr><td>{i+1}</td>'+row.replace('<tr>','').replace('</tr>','') for i,row in enumerate(gainers.split('<tr>')[1:]) )}</tbody></table></div></section>"""
    # The construction above is intentionally replaced with a clean table body.
    rows = ''.join(f"<tr><td>{i+1}</td><td><b>{escape(x['ticker'])}</b></td><td>{escape(x['name'])}</td><td class='up'><b>{x['return_30d']:+.1f}%</b></td><td><a href='{escape(yahoo_history_url(x['ticker']), quote=True)}' target='_blank' rel='noopener'>Yahoo · 365 días</a></td></tr>" for i,x in enumerate(top30))
    gainer_section = f"<section><h2>🚀 30 ACCIONES DE EE.UU. QUE MÁS SUBIERON EN 30 DÍAS</h2><p>Ranking independiente del universo de FUCHIACCIONES. Se calcula sobre las últimas 30 ruedas disponibles.</p><div class='scroll'><table><thead><tr><th>#</th><th>Ticker</th><th>Empresa</th><th>30 días</th><th>Historial</th></tr></thead><tbody>{rows or '<tr><td colspan=5>No se pudieron obtener datos suficientes.</td></tr>'}</tbody></table></div></section>"

    news = data.get('news', [])
    news_cards = ''.join(f"<article class='card'><span class='pill hold'>{escape(n.get('theme','Empresa'))}</span><h3>{escape(n.get('title_es') or n['title'])}</h3><p><small>{escape(n.get('publisher',''))}</small></p><p><a href='{escape(n['link'], quote=True)}' target='_blank' rel='noopener'>Leer fuente original</a></p></article>" for n in news)
    news_section = f"<section><h2>📰 NOTICIAS DE EMPRESAS</h2><p>Selección enfocada en hechos corporativos con impacto potencial en valuación: balances, resultados, guidance, inteligencia artificial y tecnología, nuevos productos, adquisiciones, contratos, alianzas y asuntos regulatorios. Los titulares se presentan en castellano cuando la traducción automática está disponible.</p><div class='cards'>{news_cards or '<p>Sin noticias disponibles.</p>'}</div></section>"

    # Replace the old alerts section with up to 15 US stocks.
    alerts = sorted(data.get('results', []), key=lambda x: x.get('cross', {}).get('score', 0))
    alerts = alerts[:15]
    alert_items = ''.join(f"<li><b>{escape(x['ticker'])} — {escape(x['name'])}</b> · 30d {x['returns'].get('30'):+.1f}% · 60d {x['returns'].get('60'):+.1f}% · 90d {x['returns'].get('90'):+.1f}% · 120d {x['returns'].get('120'):+.1f}% · 365d {x['returns'].get('365'):+.1f}% · <span class='pill {('sell' if 'EVITAR' in x['cross']['action'] or 'REDUCIR' in x['cross']['action'] else 'hold')}'>{escape(x['cross']['action'])}</span></li>" for x in alerts if x.get('ticker') and x.get('returns'))
    html = re.sub(r"<section><h2>⚠️ ALERTAS</h2>.*?</section>\s*", f"<section><h2>⚠️ ALERTAS — ACCIONES DE EE.UU.</h2><div class='notice'><p>Hasta 15 acciones estadounidenses que requieren atención por debilidad, deterioro de tendencia o señales técnicas relevantes.</p><ul>{alert_items or '<li>Sin alertas calculadas.</li>'}</ul></div></section>\n", html, count=1, flags=re.S)

    # Insert the new sections immediately before the global market section.
    html = html.replace("<section><h2>📈 MERCADO GLOBAL</h2>", gainer_section + '\n' + news_section + "\n<section><h2>📈 MERCADO GLOBAL</h2>", 1)

    # Make every configured ticker in the report open its 365-day Yahoo history.
    tickers = {x.get('ticker') for x in data.get('results', []) if x.get('ticker')}
    html = link_tickers(html, tickers)

    open(html_path, 'w', encoding='utf-8').write(html)

if __name__ == '__main__':
    main()
