# skeval run — the conformance matrix over a real skill.
Output assets/run.gif

Require uv

Set Shell "bash"
Set FontSize 15
Set Width 1700
Set Height 940
Set Padding 24
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 55ms
Set WaitTimeout 300s

Hide
Type "export PS1='$ ' && export COLUMNS=150 && clear" Enter
Show

Sleep 800ms
Type "uv run skeval run examples/scaffold-service -j 9" Sleep 600ms Enter
Wait+Screen /report:/
Sleep 400ms
Sleep 2500ms
