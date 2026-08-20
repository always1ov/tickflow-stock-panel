// @ts-check
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import tseslint from 'typescript-eslint'

/**
 * [fork 增强] 前端 ESLint 配置。
 *
 * 仓库里 package.json 一直有 `"lint": "eslint ."`, 但既没装 eslint 也没有配置文件,
 * 这个脚本从来跑不起来。补上。
 *
 * 取舍: 这是一个已存在数万行的代码库, 一上来开满规则只会得到一屏没人看的噪音,
 * 而一个永远是红的 lint 等于没有 lint。所以基线定成"error = 0", 只有必崩的才是 error:
 *
 *   error —— react-hooks/rules-of-hooks: hook 调用位置错误。这条报出来就是真 bug,
 *            没有例外(补这个配置时就抓到一个: MiniIntraday 的 useId 写在空数据
 *            早退之后, 分时数据从无到有时 hook 数 0→1, React 直接抛
 *            "Rendered more hooks than during the previous render")。
 *            另加 no-undef 等 js 基础错误。
 *   warn  —— react-hooks/exhaustive-deps: 能抓真 bug(R31 自动挖掘的定时器被反复
 *            重建就是这条能抓到的), 但存量 60+ 处几乎全是 `const rows = q.data ?? []`
 *            喂给 useMemo 这种"多算一遍"的性能味道, 不是错误。先留成 warn 让它可见,
 *            等存量清完再提回 error。
 *   off   —— 命名、格式、any、未使用变量: tsc 已管住类型, 格式无人力整改。
 *            no-useless-escape 也关掉: 存量全是 /[、,，;；\-]/ 里那个多余的反斜杠,
 *            行为完全一致, 为它改 4 个上游文件只会白白制造合并冲突。
 */
export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', 'public/**', '*.config.js', '*.config.ts'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.es2021 },
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      // ── 必崩的: error(rules-of-hooks 来自 recommended) ──
      ...reactHooks.configs.recommended.rules,
      // 存量 60+ 处未清, 先 warn 保持可见; 清完提回 error
      'react-hooks/exhaustive-deps': 'warn',

      // ── 风格/类型噪音: 交给 tsc 与人工评审, 这里关掉 ──
      // 存量都是字符类末尾的 \- , 与不转义等价
      'no-useless-escape': 'off',
      // tsc 的 noUnusedLocals 已经在 build 时把关, 重复报没意义
      '@typescript-eslint/no-unused-vars': 'off',
      // 本仓大量与后端 dict 直接对接的地方用 any, 逐个改属于另一件事
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      // catch {} 静默忽略在本仓是刻意写法(降级不阻断)
      'no-empty': 'off',
    },
  },
)
