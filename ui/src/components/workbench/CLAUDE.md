# Workbench Components

## Ace Editor Autocomplete - Escape Key Handling

When adding custom keyboard handlers for the Ace editor autocomplete popup, be aware of the following:

### What Doesn't Work

1. **`editor.commands.addCommand()`** - Adding an Escape command via Ace's command system doesn't capture the event before the autocomplete popup handles it.

2. **`editor.container.addEventListener()`** - The autocomplete popup is rendered as a separate DOM element outside the editor container, so events don't bubble through it.

### What Works

Use a **document-level event listener** with capture phase and `stopImmediatePropagation()`:

```typescript
onLoad={(editor) => {
  const handleEscapeForAutocomplete = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      const completer = editor.completer;
      // Check multiple ways if autocomplete is active
      if (completer && (completer.activated || completer.popup?.isOpen)) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        completer.detach();
      }
    }
  };
  document.addEventListener('keydown', handleEscapeForAutocomplete, true);
}}
```

### Key Points

- Use `document.addEventListener` with `true` (capture phase)
- Use `stopImmediatePropagation()` to prevent other handlers from firing
- Check both `completer.activated` and `completer.popup?.isOpen` for reliability
- Call `completer.detach()` to close the popup

## jsondiffpatch Library — Viewport Issues (DO NOT USE scrollIntoView)

The `OutputRenderer` diff view uses `jsondiffpatch` to render structural diffs via its HTML formatter. This library has **recurring viewport-breaking behavior**:

### Known problems

1. **`display: inline-block` on root element** — The library's CSS sets `.jsondiffpatch-delta { display: inline-block }` and `.jsondiffpatch-delta pre { display: inline-block }`. Inline-block elements size to their content, so with large JSON payloads they grow wider than the container, pushing the entire page layout horizontally.

2. **`scrollIntoView` causes full-page scroll** — The library's HTML structure makes `element.offsetTop` unreliable (offset parent may not be the scrollable container). Any call to `scrollIntoView()` or manual scroll using `offsetTop` will scroll the **entire page viewport**, not just the diff container. This has caused the viewport to shift by 700+ pixels vertically.

3. **Nested `ul` padding compounds** — Each nesting level adds `padding-left: 20px`, which for deeply nested JSON can push content far to the right.

### Required CSS overrides (in `DIFF_DARK_STYLES`)

```css
.jsondiffpatch-delta {
  display: block;
  max-width: 100%;
  overflow-wrap: anywhere;
}
.jsondiffpatch-delta pre {
  display: inline;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.jsondiffpatch-delta ul {
  max-width: 100%;
}
```

### Rules

- **NEVER use `scrollIntoView()`** on any element inside the diff container
- **NEVER use `offsetTop`** to calculate scroll positions inside jsondiffpatch HTML
- **USE `getBoundingClientRect()`** to compute relative positions, then set `container.scrollTop` directly — this is the safe way to scroll to the first change without affecting the page viewport
- The diff container must have `min-w-0 overflow-x-hidden` to prevent flex layout breakout
- All parent containers up to the panel must also have `min-w-0` and `overflow-hidden`
- Tests in `__tests__/OutputRenderer.test.tsx` (`diff scroll behavior` section) guard these invariants — do NOT remove them

### If replacing the library

If jsondiffpatch is ever replaced, ensure the new library does NOT use `display: inline-block` on its root element and does NOT require `scrollIntoView` workarounds. Test with large JSON payloads (100+ keys, deeply nested) before shipping.

## ANSI Color Code Rendering

The `OutputRenderer` component supports ANSI escape codes for colored terminal output:

- Parses escape sequences: `\x1b[91m`, `\u001b[91m`, `\033[91m`, and bare `[91m`
- Maps ANSI codes to Tailwind CSS classes (e.g., `[91m` → `text-red-400`)
- Supports standard colors (30-37) and bright colors (90-97)
