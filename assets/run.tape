# shakedown run — the matrix over a real skill.
#
# One harness on purpose. The whole matrix is the honest picture but it
# runs at the speed of its slowest target, which makes a tedious GIF.
Output assets/run.gif

Require uv

Set Shell "bash"
Set FontSize 15
Set Width 1700
Set Height 400
Set Padding 24
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 55ms
Set WaitTimeout 900s

Hide
Type "export PS1='$ ' && export COLUMNS=150 && clear" Enter
Show

Sleep 800ms
Type "uv run shakedown run examples/scaffold-service --harness claude-code -j 3" Sleep 600ms Enter
Wait+Screen /report:/
Sleep 400ms
Sleep 2500ms
