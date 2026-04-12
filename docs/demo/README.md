# Demo Assets

This folder contains the demo GIF and the tooling to regenerate it.

## Files

| File | Purpose |
|------|---------|
| `demo.tape` | [vhs](https://github.com/charmbracelet/vhs) recording script |
| `demo.py` | Standalone CLI demo (calls live Zefix API) |
| `demo.gif` | Generated output — commit after regeneration |

## Generate the GIF

### 1. Install vhs

```bash
# macOS
brew install vhs

# Linux / Windows (Go required)
go install github.com/charmbracelet/vhs@latest
```

### 2. Run the demo script manually first (sanity check)

```bash
# From repo root
pip install httpx
python docs/demo/demo.py verify "Lehrmittelverlag Zürich AG"
python docs/demo/demo.py uid "CHE-109.741.634"
python docs/demo/demo.py search "Migros" --canton ZH
```

### 3. Record the GIF

```bash
# From repo root
vhs docs/demo/demo.tape
# → writes docs/demo/demo.gif
```

### 4. Commit the GIF

```bash
git add docs/demo/demo.gif
git commit -m "docs: update demo GIF"
```

## Embedding in README

```markdown
![register-mcp demo](docs/demo/demo.gif)
```

## Tips

- Keep GIF under **10 MB** for smooth GitHub rendering
- Set `Set Width 900` and `Set Height 550` in the tape for a 16:9 aspect ratio
- Use `Sleep 2s` before commands so viewers can follow along
- `Set Theme "Dracula"` gives good contrast for dark and light GitHub themes
