/**
 * [fork R366] Service Worker —— **只为「装成主屏 app」这一件事存在**。
 *
 * 用户: 「有没有办法做个 app 手机也能用」→「手机端我只需要模拟盘页面和模拟盘
 * 里面的那两个弹窗, 只看这三个」。
 *
 * 装到主屏需要 manifest + 一个注册成功的 service worker(浏览器的安装条件),
 * 这个文件的全部职责就是满足它, 外加让壳子在网络抖一下时还能开起来。
 *
 * ## 铁律: **API 一个字节都不缓存**
 *
 * 这一页的数字 5 分钟一刷, 盘中更是实时叠加层。把 `/api/**` 缓存下来, 手机上
 * 就会看到几小时前的价格与信号 —— 而**它长得和新的一模一样**, 没有任何东西会
 * 告诉你它是旧的。这正是自检条(R343)一直在防的事, 不能让 SW 从背后把它绕过去。
 *
 * 所以这里只做两件事:
 *
 *   静态资源  /assets/** 的 js/css/字体 —— 文件名带内容哈希, **改了就是新名字**,
 *             所以「缓存优先」永远不会给出过期的东西。
 *   页面外壳  index.html —— **网络优先**, 拿不到才回落到缓存。
 *             它的名字不带哈希, 缓存优先会把人钉死在旧版本上。
 *
 * 其余一律不管: `fetch` 事件里直接 return, 让请求按浏览器原本的样子走。
 */
const VERSION = 'v1'
const STATIC = `tf-static-${VERSION}`
const SHELL = `tf-shell-${VERSION}`

self.addEventListener('install', () => {
  // 不预缓存任何东西 —— 构建产物的哈希名这里拿不到, 而运行时缓存已经够用。
  // 立刻接管, 免得装完还要等下一次打开才生效。
  self.skipWaiting()
})

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    // 换版本时把旧缓存清掉, 否则一直堆着
    const keys = await caches.keys()
    await Promise.all(keys
      .filter((k) => k.startsWith('tf-') && k !== STATIC && k !== SHELL)
      .map((k) => caches.delete(k)))
    await self.clients.claim()
  })())
})

/** 带内容哈希的构建产物 —— 改了就是新文件名, 缓存优先不会给出过期的东西 */
function isHashedAsset(url) {
  return url.origin === self.location.origin
    && url.pathname.startsWith('/assets/')
    && /\.(js|css|woff2?|ttf|png|svg)$/.test(url.pathname)
}

self.addEventListener('fetch', (e) => {
  const req = e.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)

  // **API 一律不碰。** 连"网络优先带回落"都不做 —— 回落就是在给旧数字。
  if (url.pathname.startsWith('/api/')) return
  // 跨域的也不碰(行情源、字体 CDN 之类)
  if (url.origin !== self.location.origin) return

  if (isHashedAsset(url)) {
    e.respondWith((async () => {
      const hit = await caches.match(req)
      if (hit) return hit
      const res = await fetch(req)
      if (res.ok) (await caches.open(STATIC)).put(req, res.clone())
      return res
    })())
    return
  }

  // 页面导航: 网络优先, 断网才回落到上一次的外壳。
  // 回落给的是 HTML 外壳, 里面一个数字都没有 —— 数据仍然要等 API,
  // 所以离线时看到的是"正在算"而不是一份假装是今天的旧数据。
  if (req.mode === 'navigate') {
    e.respondWith((async () => {
      try {
        const res = await fetch(req)
        if (res.ok) (await caches.open(SHELL)).put('/index.html', res.clone())
        return res
      } catch {
        return (await caches.match('/index.html')) ?? Response.error()
      }
    })())
  }
})
