# register-mcp Demo — VHS Tape
# Requires: vhs (https://github.com/charmbracelet/vhs)
# Usage:    vhs docs/demo/demo.tape
# Output:   docs/demo/demo.gif

Output docs/demo/demo.gif

Set FontSize 14
Set Width 900
Set Height 550
Set Theme "Dracula"
Set Padding 20

# Show what we're doing
Type "# register-mcp: Swiss Commercial Register via MCP"
Enter
Sleep 500ms

Type "# Query 1 — Verify a company (quick due-diligence check)"
Enter
Sleep 300ms

Type "python docs/demo/demo.py verify 'Lehrmittelverlag Zürich AG'"
Sleep 500ms
Enter
Sleep 3s

Type ""
Enter
Sleep 300ms

Type "# Query 2 — Company profile by UID"
Enter
Sleep 300ms

Type "python docs/demo/demo.py uid 'CHE-109.741.634'"
Sleep 500ms
Enter
Sleep 3s

Type ""
Enter
Sleep 300ms

Type "# Query 3 — Search by name and canton"
Enter
Sleep 300ms

Type "python docs/demo/demo.py search 'Migros' --canton ZH"
Sleep 500ms
Enter
Sleep 3s

Sleep 1s
