/**
 * [R550] 弹窗「点开 / 关闭时一闪」—— framer-motion 11 的 WAAPI 交接缺一帧。
 *
 * framer-motion 把 opacity / transform 交给浏览器原生动画(WAAPI, fill: both)跑。跑完时它在
 * onfinish 里做两件事: ① `motionValue.set(终值)` —— 只是**排队**到下一帧才写进行内样式;
 * ② 立刻 `animation.cancel()` —— 原生动画当场撤掉。两步之间元素回落到行内样式里那个**起始值**
 * (入场是 opacity 0, 退场是 opacity 1), 浏览器正好画出一帧:
 *   · 入场: 遮罩 0.77 → 0.00 → 1.00, 面板 1 → 0 → 1 —— 整块黑一下;
 *   · 退场: 淡到 0 之后又整块亮回 1 一帧才被卸掉。
 * 逐帧采样(每个 rAF 读 computed opacity + getAnimations().length)抓到的那一帧正是
 * 「原生动画已撤、行内还是 0」。全站四十来处 AnimatePresence 弹窗 / 浮层走的都是这条路。
 *
 * 修法: 撤掉一个**已经跑完**的原生动画之前, 先 `commitStyles()` 把终值写进行内样式 ——
 * 这正是 WAAPI 给「保留终态再撤动画」准备的标准做法。framer 下一帧写进来的是同一个值,
 * 不冲突。只动 playState === 'finished' 的那一种: 中途打断(还在 running)时 framer 自己会
 * 按采样值接上, 不碰。元素已不在渲染树里时 commitStyles 会抛错, 吞掉即可(反正看不见)。
 *
 * 没有升级 framer-motion(12 起换了交接写法, 但那是大版本依赖升级, 另议)。
 */
export function installWaapiHandoff(proto: Animation | undefined = globalThis.Animation?.prototype): void {
  if (!proto || typeof proto.commitStyles !== 'function') return
  const marked = proto as Animation & { __r550?: true }
  if (marked.__r550) return
  const cancel = proto.cancel
  proto.cancel = function (this: Animation) {
    if (this.playState === 'finished') {
      try {
        this.commitStyles()
      } catch {
        // 目标已脱离渲染树: 不可见, 无需保留终态
      }
    }
    return cancel.call(this)
  }
  marked.__r550 = true
}
