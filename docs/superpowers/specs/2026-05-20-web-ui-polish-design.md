# Web UI Polish Design

Date: 2026-05-20

## Scope

Targeted visual and functional improvements to the web GUI, covering markdown math rendering, color/contrast optimization, and layout fixes. Light theme with teal (#14b8a6) accent preserved.

## 1. KaTeX Math Formula Rendering

### Problem
No math rendering support. LaTeX notation (`$x^2$`, `$$\sum$$`) renders as plain text or gets mangled by markdown.

### Solution
Integrate KaTeX 0.16.x for synchronous math rendering inside the existing marked.js pipeline.

### Implementation

**base.html** — Add KaTeX CDN:
- `katex@0.16.x/dist/katex.min.css`
- `katex@0.16.x/dist/katex.min.js`

**app.js** — Add `_extractMath(text)` method called before `marked.parse()`:
1. Extract and protect code blocks (``` and ``) → placeholders
2. Extract `$$...$$` (block) → `%%MATH_BLOCK_n%%`
3. Extract `$...$` (inline) → `%%MATH_INLINE_n%%`
4. Run `marked.parse()`
5. Replace math placeholders with `katex.renderToString()` output
   - Block: `displayMode: true`, wrapped in centered div
   - Inline: `displayMode: false`
6. Restore code block placeholders

**Edge cases**:
- `$` inside code blocks is protected and not processed
- Escaped `\$` is not treated as math delimiter
- Empty `$...$` is left as-is

## 2. Color and Contrast Optimization

### Problem A: Session list hover invisible
- **Current**: `hover:bg-stone-50` (#fafaf9) ≈ sidebar background (#fafaf9 → #f5f5f4 gradient)
- **Fix**: Change to `hover:bg-brand-50/70` (teal tint at 70% opacity) for clear visual feedback

### Problem B: Modules too uniform
- **Current**: sidebar, main area, top bar all near stone-50
- **Fix**: Differentiate layers:
  - Sidebar panel: deepen gradient to `stone-100 → stone-50`
  - Main area: keep `stone-50`
  - Top bar: frosted glass with slightly warmer tint
  - Add subtle box-shadow separators between panels

### Problem C: User message text selection invisible
- **Current**: Global `::selection` is `rgba(13, 148, 136, 0.2)` — nearly invisible on teal gradient bubble
- **Fix**: Add `.user-bubble ::selection` with white/light background for high contrast against teal

### Problem D: Tech feel enhancement
- Add subtle gradient overlays on sidebar header
- Add fine border-glow effect on active session item
- Enhance shadow depth on cards (task panel, artifacts)
- Add micro-gradient on sidebar border separators

## 3. Session Title Truncation

### Problem
Long session titles push right-side elements ("本地执行" badge) to wrap.

### Fix
- Add `max-w-[140px]` constraint on session title spans within the top bar
- Existing `truncate` class handles ellipsis
- Verify project-grouped session titles also have width constraint

## 4. Button Vertical Centering

### Problem
Compact context and rewind buttons in top bar not vertically centered.

### Fix
- Verify header uses `items-center` (it does on line 132)
- Check if the SVG icon wrapper `kratos-icon` has explicit height causing misalignment
- Adjust icon sizing or add `self-center` if needed

## Files Changed

| File | Changes |
|------|---------|
| `src/data_agent/web/templates/base.html` | Add KaTeX CDN links |
| `src/data_agent/web/static/js/app.js` | Add math extraction and rendering logic |
| `src/data_agent/web/static/css/app.css` | Color fixes, selection styles, tech enhancements |
| `src/data_agent/web/templates/index.html` | Tailwind class updates for hover, truncation, centering |

## Not Changed
- Tilde/strikethrough handling (risk assessed as minimal, deferred)
- Dark mode receives parallel fixes where `.dark` rules exist
- No structural or architectural changes
