export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const bot = url.pathname.match(/^\/(?:file\/)?bot(\d+):/);
    if (!bot || !JSON.parse(env.BOT_IDS).includes(bot[1])) {
      return new Response(null, { status: 404 });
    }
    return fetch(new Request(`https://api.telegram.org${url.pathname}${url.search}`, request));
  },
};
