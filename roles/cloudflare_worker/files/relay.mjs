// ROUTES: {upstream host: [path prefixes]}; the first path segment names the host, as in /<host>/<path>.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const routes = JSON.parse(env.ROUTES);
    const [, host, path = "/"] = url.pathname.match(/^\/([^/]+)(\/.*)?$/) ?? [];
    if (!host || !Object.hasOwn(routes, host) || !routes[host].some((prefix) => path.startsWith(prefix))) {
      return new Response(null, { status: 404 });
    }
    return fetch(new Request(`https://${host}${path}${url.search}`, request));
  },
};
