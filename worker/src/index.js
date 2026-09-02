const ALLOWED_ORIGIN = 'https://fuchiacciones.github.io';
const OWNER = 'fuchiacciones';
const REPO = 'fuchiacciones';
const WORKFLOW_FILE = 'daily.yml';

function corsHeaders(origin) {
  const allowed = origin === ALLOWED_ORIGIN ? origin : ALLOWED_ORIGIN;
  return {
    'Access-Control-Allow-Origin': allowed,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Cache-Control': 'no-store',
  };
}

function json(data, status, origin) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders(origin), 'Content-Type': 'application/json; charset=utf-8' },
  });
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    if (request.method !== 'POST') {
      return json({ ok: false, error: 'Método no permitido' }, 405, origin);
    }

    if (origin && origin !== ALLOWED_ORIGIN) {
      return json({ ok: false, error: 'Origen no autorizado' }, 403, origin);
    }

    const token = env.GITHUB_TOKEN;
    if (!token) {
      return json({ ok: false, error: 'GITHUB_TOKEN no configurado en el Worker' }, 500, origin);
    }

    const url = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
    const gh = await fetch(url, {
      method: 'POST',
      headers: {
        'Accept': 'application/vnd.github+json',
        'Authorization': `Bearer ${token}`,
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'FUCHIACCIONES-Refresh-Worker',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ref: 'main' }),
    });

    if (!gh.ok) {
      const detail = await gh.text();
      return json({ ok: false, error: 'GitHub rechazó el disparo del workflow', detail: detail.slice(0, 500) }, 502, origin);
    }

    return json({ ok: true, message: 'Análisis solicitado. GitHub Actions está ejecutando una nueva actualización.' }, 202, origin);
  },
};
