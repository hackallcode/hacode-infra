// ROUTES: {upstream host: [path prefixes]}. HOST fixes the upstream; without it the first path segment names it, as
// in /<host>/<path>.
const route = (env, pathname) => {
  if (env.HOST) return [env.HOST, pathname];
  const match = pathname.match(/^\/([^/]+)(\/.*)?$/);
  return match ? [match[1], match[2] ?? "/"] : [];
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const routes = JSON.parse(env.ROUTES);
    const [host, path] = route(env, url.pathname);
    if (!host || !Object.hasOwn(routes, host) || !routes[host].some((prefix) => path.startsWith(prefix))) {
      return new Response(null, { status: 404 });
    }
    return fetch(new Request(`https://${host}${path}${url.search}`, request));
  },
};
