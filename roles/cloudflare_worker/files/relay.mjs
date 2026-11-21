export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!JSON.parse(env.PATHS).some((prefix) => url.pathname.startsWith(prefix))) {
      return new Response(null, { status: 404 });
    }
    return fetch(new Request(`${env.UPSTREAM}${url.pathname}${url.search}`, request));
  },
};
